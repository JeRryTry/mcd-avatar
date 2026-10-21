"""产品清洗辅助：名称归一化、营养表解析、品类归类、营养匹配。

`merge_full.py` 依赖本模块。历史版本中本文件缺失导致数据清洗链路不可运行，
此处按现有快照（mcp/data/catalog.json）的行为重建，并补充了容错与注释。

对外函数：
- ``norm(name)``                名称归一化（去商标符/空白，统一全角括号）
- ``parse_nutrition()``         解析 data/raw/nutrition.json → {归一化名: 营养字典}
- ``classify(name)``            品类归类（burger/chicken/fries/drink/dessert/breakfast/side/other）
- ``match_nutrition(name, t)``  在产品名与营养表之间做匹配，返回营养字典或 None
- ``is_combo(name)``            是否为套餐/组合装（不适合作为头像里的「今日那口」）
- ``suggest_keep(products)``    按「只留单品、同名去重」给出建议上架清单
"""
from __future__ import annotations

import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")

# 营养表列名 → 输出字段名
_NUTRITION_FIELDS = {
    "energyKj": "energy_kj",
    "energyKcal": "kcal",
    "protein": "protein_g",
    "fat": "fat_g",
    "carbohydrate": "carb_g",
    "sodium": "sodium_mg",
    "calcium": "calcium_mg",
}

_TRADEMARK = re.compile(r"[™®©℠★☆]")
_WHITESPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# 名称归一化
# --------------------------------------------------------------------------- #
def norm(name: str) -> str:
    """归一化产品名：去商标符号、去空白、统一全角括号，便于跨源对齐。"""
    s = str(name or "")
    s = s.replace("\u3000", " ")
    s = _TRADEMARK.sub("", s)
    s = _WHITESPACE.sub("", s)
    s = s.replace("（", "(").replace("）", ")")
    return s.strip()

def _num(value) -> float | None:
    """把营养表里的字符串数值转 float；空值 / null / '-' 统一返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "null", "None", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# 营养表解析
# --------------------------------------------------------------------------- #
def _parse_table(text: str) -> dict:
    """解析 MCP 返回的类 CSV 文本表：
    ``[160]{productName,...,calcium}:`` 换行后逐行逗号分隔。
    """
    text = str(text or "")
    header = re.search(r"\{([^}]*)\}\s*:", text)
    if not header:
        return {}

    columns = [c.strip() for c in header.group(1).split(",")]
    result = {}
    for line in text[header.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(columns):
            continue
        row = dict(zip(columns, parts))
        name = row.get("productName")
        if not name:
            continue
        result[norm(name)] = {
            dst: _num(row.get(src)) for src, dst in _NUTRITION_FIELDS.items()
        }
    return result


def parse_nutrition() -> dict:
    """读取 data/raw/nutrition.json 并返回 {归一化产品名: 营养字典}。

    兼容三种形态：``data`` 为原始文本表（当前实际）、为结构化列表、或整份即映射。
    """
    path = os.path.join(RAW, "nutrition.json")
    if not os.path.exists(path):
        return {}

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict):
        payload = payload.get("data", payload)

    if isinstance(payload, str):
        return _parse_table(payload)

    if isinstance(payload, list):
        result = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            name = row.get("productName") or row.get("name")
            if not name:
                continue
            result[norm(name)] = {
                dst: _num(row.get(src)) for src, dst in _NUTRITION_FIELDS.items()
            }
        return result

    return {}


# --------------------------------------------------------------------------- #
# 品类归类
# --------------------------------------------------------------------------- #
# 关键词按优先级排列，先命中者决定品类。顺序经过与现有快照逐条比对校准。
_BREAKFAST = ("吉士汉堡",)
_DRINK = (
    "新地", "冰淇淋", "麦旋风", "奶昔", "酸奶", "奶铁", "美式", "咖啡", "冰咖",
    "可乐", "麦炫酷", "怡泉", "鲜萃", "牛奶", "燕麦奶", "豆浆", "红茶", "雪冰",
    "玛奇朵", "卡布奇诺", "果汁", "苹果汁", "纯悦", "柠檬红茶", "朱古力",
)
_DESSERT = ("派", "拉明顿", "糍粑", "小圆子", "阿芙佳朵", "奶冻")
_FRIES = ("薯条", "薯格", "薯饼", "扭扭薯", "脆薯")
_CHICKEN = ("鸡腿", "鸡翅", "麦乐鸡", "V翅", "肉骨鸡", "芝士条", "炸鸡")
_SIDE = ("蘸酱", "鸡块", "鸡柳", "风味酱")
_BURGER = ("堡", "巨无霸", "汉堡", "卷")


def classify(name: str) -> str:
    """按名称关键词归类，返回 8 类之一。

    优先级：早餐 → 饮品 → 甜品 → 薯类 → 炸鸡 → 小食 → 汉堡 → 其他。
    该顺序刻意让「酸奶派」归饮品、「鸡腿堡」归炸鸡、「炸鸡块」归小食等边界成立。
    """
    key = norm(name)
    for keywords, label in (
        (_BREAKFAST, "breakfast"),
        (_DRINK, "drink"),
        (_DESSERT, "dessert"),
        (_FRIES, "fries"),
        (_CHICKEN, "chicken"),
        (_SIDE, "side"),
        (_BURGER, "burger"),
    ):
        if any(k in key for k in keywords):
            return label
    return "other"


# --------------------------------------------------------------------------- #
# 营养匹配
# --------------------------------------------------------------------------- #
def match_nutrition(name: str, nutrition: dict) -> dict | None:
    """在产品名与营养表之间匹配营养数据。

    匹配优先级：
    1. 归一化名精确命中；
    2. 营养表条目名是产品名的子串（如「板烧鸡腿堡三件套」→「板烧鸡腿堡」）；
    3. 产品名是营养表条目名的子串（如「麦乐鸡」→「麦乐鸡5块」）。
    营养表按原始行顺序迭代，命中第一条即返回，保证结果确定性。
    """
    if not nutrition:
        return None
    key = norm(name)
    if not key:
        return None
    if key in nutrition:
        return nutrition[key]
    for entry in nutrition:
        if entry and entry in key:
            return nutrition[entry]
    for entry in nutrition:
        if key in entry:
            return nutrition[entry]
    return None


# --------------------------------------------------------------------------- #
# 策展：套餐识别与建议上架清单
# --------------------------------------------------------------------------- #
# 这类名字对应的是「一份套餐 / 一托盘组合」，图片往往是托盘或多件摆盘，
# 摆在头像顶上既看不清主体、也不符合「今天想吃的那一口」的设定，故建议不上架。
_COMBO = re.compile(r"套餐|件套|随心选|随心配|乐园餐|双人餐|分享餐|买一送一|四宫格|单人餐|组合装")

# 非餐品：周边、玩具、酱料包、袋子、盒子。它们能查到、图也有，但摆头顶上完全不对味。
# 注意「酱$」只匹配以「酱」结尾的独立酱料包；「蘸酱脆皮鸡块」「薯饼+风味酱」这类仍是餐品。
_NON_FOOD = re.compile(
    r"玩具|周边|贴纸|星愿贴|徽章|棒球帽|水手帽|毛绒|玩偶|公仔|按摩捶|痒痒挠"
    r"|盲盒|礼盒|礼品|优惠券|购物袋|餐具|吸管|纸巾|湿巾|袋$|盒$|酱$"
)


def is_combo(name: str) -> bool:
    """套餐/组合装判定（只看名字，纯规则，无副作用）。"""
    return bool(_COMBO.search(norm(name)))


# 出现这些词说明名字里带着真正的餐品主体（如「5块心形薯饼+韩式辣椒黄油风味酱」），
# 只是顺带配了酱，仍算餐品。
_FOOD_HINT = ("薯饼", "薯条", "薯格", "鸡块", "鸡柳", "鸡翅", "麦乐鸡", "堡", "卷", "派", "玉米", "冰淇淋")


def is_non_food(name: str) -> bool:
    """非餐品判定：周边/玩具/酱料包/袋盒等，不适合作为头像里的「今日那口」。"""
    key = norm(name)
    if not _NON_FOOD.search(key):
        return False
    if key.endswith("酱") and any(hint in key for hint in _FOOD_HINT):
        return False
    return True


def suggest_keep(products, has_image=None) -> tuple[list[str], dict[str, str]]:
    """给出建议上架清单。

    规则：
    1. 套餐/组合装 → 建议不上架（原因「套餐/组合」）；
    2. 非餐品（周边/玩具/酱料包/袋盒）→ 建议不上架（原因「非餐品」）；
    3. 同名多 code（不同门店/新旧 SKU 的重复条目）→ 只留一条，
       优先级：有官方图 > 有价格 > code 较短（通常是基础 SKU），其余标记「重名」。

    ``has_image`` 是可选判定函数 ``f(product) -> bool``；不传时视为全部有图。

    返回 ``(keep_codes, reasons)``：keep_codes 为建议上架 code，reasons 为 {code: 原因}。
    """
    has_image = has_image or (lambda _p: True)

    groups: dict[str, list[dict]] = {}
    for p in products:
        groups.setdefault(norm(p.get("name")), []).append(p)

    keep: list[str] = []
    reasons: dict[str, str] = {}
    for name, items in groups.items():
        if is_combo(name):
            for p in items:
                reasons[str(p["code"])] = "套餐/组合"
            continue
        if is_non_food(name):
            for p in items:
                reasons[str(p["code"])] = "非餐品"
            continue
        ranked = sorted(
            items,
            key=lambda p: (
                not has_image(p),
                p.get("price") is None,
                len(str(p["code"])),
                str(p["code"]),
            ),
        )
        keep.append(str(ranked[0]["code"]))
        for p in ranked[1:]:
            reasons[str(p["code"])] = "重名"
    return keep, reasons
