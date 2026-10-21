"""菜品管理：决定 MCP 菜单里哪些单品进入头像候选（mcp 端的「管菜品」）。

上架状态直接写在 ``mcp/data/catalog.json`` 的 ``in_catalog`` 字段里，**没有单独的清单文件**：
catalog.json 既是数据源快照，也承载策展结果。下架不删数据、不删图，随时可加回。

常用：
    python3 mcp/manage.py --list                 # 看全量菜单与当前上下架
    python3 mcp/manage.py --suggest              # 按建议规则重置（只留适合做头像的）
    python3 mcp/manage.py --off 9900004835,514850
    python3 mcp/manage.py --on 1401
    python3 mcp/manage.py --reset                # 全部上架

改完重跑导出，头像端才会看到变化：
    python3 mcp/export_avatar.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean_products as cp  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(BASE, "data", "catalog.json")

CAT_ORDER = ("burger", "chicken", "fries", "side", "dessert", "drink", "breakfast", "other")


def load() -> dict:
    if not os.path.exists(CATALOG):
        raise SystemExit("找不到 mcp/data/catalog.json，请先跑 python3 mcp/update_menu.py")
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def save(catalog: dict) -> None:
    products = catalog["products"]
    catalog["meta"]["listed"] = sum(
        1 for p in products if p.get("in_catalog") and p.get("local_image"))
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def cmd_list(catalog: dict) -> None:
    products = catalog["products"]
    listed = [p for p in products if p.get("in_catalog")]
    ready = [p for p in listed if p.get("local_image")]
    print(f"菜单全量 {len(products)} 款 | 上架 {len(listed)} 款（其中可就绪出图 {len(ready)} 款）"
          f" | 下架 {len(products) - len(listed)} 款\n")
    print(f"{'状态':<4}{'code':<12}{'品类':<10}{'图':<3}{'名称':<30}建议")
    print("-" * 80)
    cats: dict[str, list[dict]] = {}
    for p in products:
        cats.setdefault(p.get("shape_type") or "other", []).append(p)
    for cat in CAT_ORDER:
        for p in cats.get(cat, []):
            mark = "✓" if p.get("in_catalog") else "·"
            has = "有" if p.get("local_image") else "-"
            print(f"{mark:<4}{str(p.get('code')):<12}{cat:<10}{has:<3}"
                  f"{(p.get('name') or '')[:28]:<30}{p.get('hint') or ''}")
    print("\n✓ = 上架　· = 下架　建议 = 规则给出的排除原因（仅供参考，不影响实际状态）")


def main() -> int:
    ap = argparse.ArgumentParser(description="菜品管理：哪些单品进入头像候选")
    ap.add_argument("--list", action="store_true", help="打印全量菜单与上下架状态")
    ap.add_argument("--suggest", action="store_true", help="按建议规则重置上架状态")
    ap.add_argument("--reset", action="store_true", help="全部上架")
    ap.add_argument("--on", help="逗号分隔，加回上架")
    ap.add_argument("--off", help="逗号分隔，下架")
    args = ap.parse_args()

    catalog = load()
    products = catalog["products"]

    if args.list:
        cmd_list(catalog)
        return 0

    if args.suggest:
        suggest, reasons = cp.suggest_keep(
            products, has_image=lambda p: p.get("local_image") is not None)
        keep = {str(c) for c in suggest}
        for p in products:
            p["in_catalog"] = str(p["code"]) in keep
            p["hint"] = reasons.get(str(p["code"]))
        save(catalog)
        combo = sum(1 for r in reasons.values() if r == "套餐/组合")
        junk = sum(1 for r in reasons.values() if r == "非餐品")
        dup = sum(1 for r in reasons.values() if r == "重名")
        print(f"按建议重置：上架 {len(keep)} 款 | 排除 套餐/组合 {combo}、非餐品 {junk}、重名 {dup}")
        print("下一步：python3 mcp/export_avatar.py")
        return 0

    if args.reset:
        for p in products:
            p["in_catalog"] = True
            p["hint"] = None
        save(catalog)
        print(f"全部上架：{len(products)} 款")
        print("下一步：python3 mcp/export_avatar.py")
        return 0

    if not (args.on or args.off):
        ap.print_help()
        return 1

    by_code = {str(p["code"]): p for p in products}
    changed = 0
    if args.on:
        for code in [c.strip() for c in args.on.split(",") if c.strip()]:
            if code in by_code:
                by_code[code]["in_catalog"] = True
                changed += 1
            else:
                print(f"⚠️  菜单里没有 code {code}，已忽略")
    if args.off:
        for code in [c.strip() for c in args.off.split(",") if c.strip()]:
            if code in by_code:
                by_code[code]["in_catalog"] = False
                changed += 1
            else:
                print(f"⚠️  菜单里没有 code {code}，已忽略")

    save(catalog)
    listed = sum(1 for p in products if p.get("in_catalog"))
    print(f"已更新 {changed} 款 | 当前上架 {listed} / {len(products)}")
    print("下一步：python3 mcp/export_avatar.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
