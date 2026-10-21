"""清洗 MCP 原始响应 → mcp/data/catalog.json（唯一数据源）。

数据源优先级（取权威字段）：
- 名称/价格/分类：meals_by_store_v2.json（顶层菜单，带 currentPrice）
- 图片：优先顶层菜单 image；缺失时取 meal_details.json 的 detail.image
- 营养：名称归一化对齐 nutrition.json
- 额外收录 meal_details 里仅作为套餐子单品出现、不在任何顶层菜单中的 code

输出 ``catalog.json`` = 全量菜单 + 每条的上架状态：

    {"meta": {...}, "products": [
        {..., "in_catalog": true, "hint": null, "local_image": "assets/img/1401.png"}
    ]}

``in_catalog`` 是**人工策展结果**，重跑本脚本时按 code 继承旧值，所以更新菜单不会
把你手工调过的上下架冲掉；新出现的单品才套用 ``clean_products.suggest_keep`` 的建议值。

注：本脚本依赖同目录 clean_products.py 提供分类/营养匹配/策展规则。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RAW = os.path.join(DATA, "raw")
IMG_DIR = os.path.join(BASE, "assets", "img")
CATALOG = os.path.join(DATA, "catalog.json")

sys.path.insert(0, BASE)
from clean_products import (  # noqa: E402
    parse_nutrition, norm, classify, match_nutrition, suggest_keep,
)

IMG_EXTS = (".png", ".gif", ".jpg", ".jpeg")


def load(name):
    p = os.path.join(RAW, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def local_image(code) -> str | None:
    """本地已落盘的官方图（相对 mcp/ 的路径），没有则 None。"""
    for ext in IMG_EXTS:
        f = f"{code}{ext}"
        if os.path.exists(os.path.join(IMG_DIR, f)):
            return f"assets/img/{f}"
    return None


def load_old_state() -> dict[str, bool]:
    """读旧 catalog 的上架状态，用于重跑时继承人工策展结果。"""
    if not os.path.exists(CATALOG):
        return {}
    try:
        with open(CATALOG, encoding="utf-8") as f:
            old = json.load(f)
        return {str(p["code"]): bool(p.get("in_catalog"))
                for p in old.get("products") or [] if p.get("code") is not None}
    except Exception:
        return {}


def main():
    nutr = parse_nutrition()

    stores = load("meals_by_store_v2.json") or load("meals_by_store.json")
    details = load("meal_details.json")

    agg = {}

    # ---- 顶层菜单聚合 ----
    for sc, sd in stores.items():
        code2cat = {}
        for c in sd.get("categories") or []:
            cname = (c.get("name") or "").replace("\n", "")
            for m in c.get("meals", []) or []:
                code2cat[m.get("code")] = cname
        for code, item in (sd.get("meals") or {}).items():
            a = agg.setdefault(code, {
                "code": code, "name": item.get("name"), "image": item.get("image"),
                "prices": Counter(), "orig": Counter(), "cats": Counter(), "stores": 0,
                "is_combo_sub_only": False,
            })
            if item.get("currentPrice"):
                a["prices"][item["currentPrice"]] += 1
            if item.get("originalPrice"):
                a["orig"][item["originalPrice"]] += 1
            cat = code2cat.get(code)
            if cat:
                a["cats"][cat] += 1
            a["stores"] += 1

    top_count = len(agg)

    # ---- 补充仅出现在套餐子单品里的 code ----
    for code, rec in details.items():
        det = rec.get("detail") or {}
        if code not in agg and (det.get("name") or det.get("image")):
            agg[code] = {
                "code": code, "name": det.get("name"), "image": det.get("image"),
                "prices": Counter(), "orig": Counter(), "cats": Counter(),
                "stores": 0, "is_combo_sub_only": True,
            }

    # ---- 从 details 回填缺失的图片 ----
    for code, a in agg.items():
        if not a.get("image") and code in details:
            a["image"] = (details[code].get("detail") or {}).get("image")

    # ---- 生成产品记录 ----
    products = []
    matched = with_img = 0
    for code, a in agg.items():
        price = _f(a["prices"].most_common(1)[0][0]) if a["prices"] else None
        orig = _f(a["orig"].most_common(1)[0][0]) if a["orig"] else None
        cat = a["cats"].most_common(1)[0][0] if a["cats"] else None
        nutrition = match_nutrition(a["name"] or "", nutr)
        if nutrition:
            matched += 1
        if a.get("image"):
            with_img += 1
        products.append({
            "code": code,
            "name": a["name"],
            "name_norm": norm(a["name"] or ""),
            "shape_type": classify(a["name"] or ""),
            "price": price,
            "original_price": orig,
            "category": cat,
            "image_url": a.get("image"),
            "nutrition": nutrition,
            "store_count": a["stores"],
            "combo_sub_only": a["is_combo_sub_only"],
        })

    products.sort(key=lambda p: (-p["store_count"], str(p["code"])))

    # ---- 策展状态：人工结果优先，新品套用建议 ----
    suggest, reasons = suggest_keep(
        products, has_image=lambda p: local_image(p.get("code")) is not None)
    suggest_set = {str(c) for c in suggest}
    old_state = load_old_state()

    listed = 0
    with_local = 0
    for p in products:
        code = str(p["code"])
        p["local_image"] = local_image(code)
        p["hint"] = reasons.get(code)
        p["in_catalog"] = old_state.get(code, code in suggest_set)
        if p["local_image"]:
            with_local += 1
            if p["in_catalog"]:
                listed += 1

    out = {
        "meta": {
            "total_products": len(products),
            "top_level_products": top_count,
            "combo_sub_products": len(products) - top_count,
            "with_nutrition": matched,
            "with_image": with_img,
            "with_local_image": with_local,
            "listed": listed,
            "stores_scanned": len(stores),
            "snapshot": date.today().isoformat(),
            "source": "mcd MCP query-meals + query-meal-detail(拆套餐) + list-nutrition-foods",
        },
        "products": products,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    dist = Counter(p["shape_type"] for p in products)
    print(f"顶层产品: {top_count} | 套餐子单品: {len(products)-top_count} | 合计: {len(products)}")
    print(f"带图片 URL: {with_img} | 本地已落图: {with_local} | 对齐营养: {matched}")
    print(f"上架（有图可合成）: {listed}")
    if old_state:
        kept = sum(1 for c, v in old_state.items() if v)
        print(f"继承上次策展状态: {len(old_state)} 条（其中上架 {kept} 条）")
    print("形状分布:", dict(dist))
    print("已写 mcp/data/catalog.json")


def _f(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    main()
