"""全量增强采集 —— 目标:尽可能穷尽麦当劳所有产品资料(含套餐子单品)。

要点:
1. 城市覆盖多地域差异菜单；
2. 阶段二「拆套餐」：对每个套餐 code 调 query-meal-detail，收集其 rounds.choices
   与 modification 里的全部子单品 code；
3. 阶段三「补子单品」：对尚未收录的子单品 code 逐个 query-meal-detail 拿名称+官方图。

产物落 data/raw/：
- meals_by_store_v2.json  各店顶层菜单
- meal_details.json       套餐/单品详情原始响应(code -> detail)
- stores_index_v2.json    门店索引
运行时间较长，全程只读、无副作用；带限速与断点续跑(已存在则跳过)。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from mcp_client import McdMcpClient  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")

CITIES = [
    "上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "重庆",
    "苏州", "天津", "长沙", "郑州", "青岛", "宁波", "东莞", "佛山", "合肥", "福州",
    "厦门", "昆明", "沈阳", "大连", "济南", "无锡", "常州", "哈尔滨", "石家庄", "南宁",
]


def load_json(name, default):
    p = os.path.join(RAW, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default
    return default


def save_json(name, obj):
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    c = McdMcpClient()

    # ---------- 阶段一：多城门店 + 顶层菜单 ----------
    stores_index = load_json("stores_index_v2.json", {})
    meals_by_store = load_json("meals_by_store_v2.json", {})
    print("[阶段1] 门店+顶层菜单")
    for city in CITIES:
        if city in stores_index and stores_index[city]:
            continue
        try:
            r = c.call("query-nearby-stores", {
                "beType": 1, "searchType": 2, "city": city, "keyword": "麦当劳"})
        except Exception as e:  # noqa: BLE001
            print(f"  {city} 门店失败: {str(e)[:60]}"); continue
        stores = r.get("data", []) or []
        stores_index[city] = stores
        print(f"  {city}: {len(stores)} 门店")
        for st in stores:
            code = st.get("storeCode")
            if not code or code in meals_by_store:
                continue
            try:
                m = c.call("query-meals", {"storeCode": code, "orderType": 1, "beType": 1})
                meals_by_store[code] = {
                    "storeCode": code, "storeName": st.get("storeName"), "city": city,
                    "categories": (m.get("data") or {}).get("categories") or [],
                    "meals": (m.get("data") or {}).get("meals") or {},
                }
            except Exception as e:  # noqa: BLE001
                print(f"    店{code}菜单失败:{str(e)[:50]}")
            time.sleep(0.25)
        save_json("stores_index_v2.json", stores_index)
        save_json("meals_by_store_v2.json", meals_by_store)
    print(f"  顶层菜单门店数: {len(meals_by_store)}")

    # 收集一个 storeCode 作为后续详情查询锚点(详情需带 storeCode)
    anchor = next(iter(meals_by_store), None)
    if not anchor:
        print("!! 无门店数据，终止"); return
    store_codes = list(meals_by_store.keys())

    # 汇总所有已知 code(顶层)
    known = {}
    for sc, sd in meals_by_store.items():
        for code, item in sd["meals"].items():
            known.setdefault(code, item)
    print(f"  顶层去重 code: {len(known)}")

    # ---------- 阶段二：拆套餐，收集子单品 code ----------
    print("[阶段2] 拆解套餐子单品")
    details = load_json("meal_details.json", {})
    sub_codes = set()
    combo_codes = [cd for cd in known if str(cd).startswith("99")]  # 套餐多为 99 开头
    # 也把所有顶层 code 纳入详情采集(拿权威 image/name)
    todo_detail = [cd for cd in known if cd not in details]
    print(f"  待查详情 code: {len(todo_detail)} (其中疑似套餐 {len(combo_codes)})")

    def pick_store_for(code):
        # 找一个卖该 code 的门店作为查询锚点
        for sc, sd in meals_by_store.items():
            if code in sd["meals"]:
                return sc
        return anchor

    processed = 0
    for code in todo_detail:
        sc = pick_store_for(code)
        try:
            d = c.call("query-meal-detail", {
                "storeCode": sc, "orderType": 1, "beType": 1, "code": str(code)})
            det = d.get("data") or {}
            details[str(code)] = {"storeCode": sc, "detail": det}
            # 抽子单品
            for rd in det.get("rounds", []) or []:
                for ch in rd.get("choices", []) or []:
                    cc = ch.get("code")
                    if cc and str(cc) not in known:
                        sub_codes.add(str(cc))
                    # modification 内层
                    mod = ch.get("modification") or {}
                    for mi in mod.get("items", []) or []:
                        for mv in mi.get("values", []) or []:
                            mc = mv.get("code")
                            if mc and str(mc) not in known:
                                sub_codes.add(str(mc))
        except Exception as e:  # noqa: BLE001
            if processed % 20 == 0:
                print(f"    detail {code} 失败: {str(e)[:50]}")
        processed += 1
        if processed % 20 == 0:
            save_json("meal_details.json", details)
            print(f"    详情进度 {processed}/{len(todo_detail)}, 新发现子单品 {len(sub_codes)}")
        time.sleep(0.2)
    save_json("meal_details.json", details)
    print(f"  阶段2完成: 详情{len(details)}条, 新子单品code {len(sub_codes)}")

    # ---------- 阶段三：补查子单品详情(拿名称+图) ----------
    print("[阶段3] 补查子单品详情")
    subs_done = 0
    sub_list = sorted(sub_codes - set(details.keys()))
    print(f"  待补子单品: {len(sub_list)}")
    for code in sub_list:
        try:
            d = c.call("query-meal-detail", {
                "storeCode": anchor, "orderType": 1, "beType": 1, "code": str(code)})
            det = d.get("data") or {}
            if det.get("name") or det.get("image"):
                details[str(code)] = {"storeCode": anchor, "detail": det, "is_sub": True}
                subs_done += 1
        except Exception:  # noqa: BLE001
            pass
        if (subs_done) % 20 == 0 and subs_done:
            save_json("meal_details.json", details)
        time.sleep(0.15)
    save_json("meal_details.json", details)
    print(f"  阶段3完成: 新增子单品详情 {subs_done}")
    print(f"\n总计 meal_details: {len(details)} 条 code(顶层+子单品)")


if __name__ == "__main__":
    main()
