"""「今天什麦人 · 麦当劳头像」合成引擎 v2.

素材约定(avatar/assets/):
- persons/a* = 人物底图(a1..a7),1000x1000 RGBA,透明背景
- hats/h1   = 普通帽子(单独戴帽时使用)
- hats/h2   = 顶食帽子(帽子+食物时使用,帽型为托住食物做了调整)

合成逻辑:
- mode=hat_only : 人物 + h1
- mode=with_food: 人物 + H2 + 麦当劳食物【原图】(mcp/assets/img/{code}),食物放在帽子正上方,营造头顶感
- mode=random   : 随机决定 hat_only / with_food

食物摆放基于内容包围盒(自动裁掉素材四周透明边),坐标针对 1000x1000 画布标定.
支持 seed 复现(同一天同一 seed → 同一结果).

CLI:
  python3 tools/preview.py --seed 20261020            # 随机模式
  python3 tools/preview.py --mode with_food --code 1401
  python3 tools/preview.py --mode hat_only --person a3
产物: output/avatar_<tag>.png + 同名 .json 元信息
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根
PERSON_DIR = os.path.join(BASE, "avatar", "assets", "persons")        # 人物素材
HAT_DIR = os.path.join(BASE, "avatar", "assets", "hats")              # 帽子 + 聊天框
IMG_DIR = os.path.join(BASE, "mcp", "assets", "img")                 # 食物官方原图
CATALOG = os.path.join(BASE, "mcp", "data", "catalog.json")          # MCP 数据源
OUT_DIR = os.path.join(BASE, "output")

CANVAS = 1000
HAT_W = 530            # 帽子基准宽
HAT_DY = -30           # 帽子水平偏移(相对画布中心)
FOOD_W = 480           # 食物基准宽
HAT_OVERLAP = 190      # 帽底压到头顶下方的距离(戴帽位置)
MARGIN_TOP = 20        # 顶部安全边距
TARGET_HEAD_TOP = 400  # 统一把人物头顶对齐到画布此高度，上方留给帽+食物
FOOD_DX_RATIO = 0.24   # 食物相对帽子中心的水平偏移比例(×帽宽)
FOOD_DY = -120         # 食物上下偏移(相对帽顶,-=上移 +=下压)
FOOD_ROT = 16          # 食物旋转角度(度,视觉顺时针)
AUTO_SHRINK = 1        # 竖高食物自动缩小防出界(1开/0关)
BUBBLE_TEXTS = ["就这个", "你懂的", "你请客", "加班狗", ""]   # 可选聊天框文字(空=不显示)


def _load_font(size: int):
    """加载支持中文的字体(macOS 常见路径逐个尝试)."""
    for fp in ("/System/Library/Fonts/PingFang.ttc",
               "/System/Library/Fonts/STHeiti Medium.ttc",
               "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_bubble(canvas: Image.Image, text: str, seed: int = 0,
                fig_left_x: int = 200) -> None:
    """在人物左侧贴聊天框背景素材(assets/avatar/chat2.png),文字居中叠在上面.

    fig_left_x: 人物内容最左边缘(画布坐标),气泡右缘自动让开它 10px.
    """
    if not text:
        return
    path = os.path.join(HAT_DIR, "chat2.png")
    if not os.path.exists(path):
        return
    W = canvas.size[0]
    bub = Image.open(path).convert("RGBA")
    bub = bub.crop(bub.split()[3].getbbox() or (0, 0, bub.width, bub.height))
    # 宽度自适应:右缘紧贴人物左侧留缝,最小保底 0.18W
    bw = max(int(W * 0.01) + int(W * 0.18), fig_left_x - 10 - int(W * 0.01))
    bw = min(bw, int(W * 0.34))
    bub = scale_to_width(bub, bw)
    bx, by = int(W * 0.01), int(W * 0.34)
    canvas.alpha_composite(bub, (bx, by))

    # 文字固定三个字,一字一行竖排居中(与 mc-avatar.js 的 drawBubble 一致)
    d2 = ImageDraw.Draw(canvas)
    chars = "".join(text.split())[:3]
    fsize = int(min(max(bw * 0.30, 44), 88))
    font = _load_font(fsize)
    lh = int(fsize * 1.16)
    total_h = lh * len(chars)
    y0 = by + bub.height / 2 - total_h / 2 + (lh - fsize) / 2
    for i, ch in enumerate(chars):
        tw = d2.textlength(ch, font=font)
        d2.text((bx + (bw - tw) / 2, y0 + i * lh), ch, font=font,
                fill=(20, 20, 20, 255), stroke_width=2, stroke_fill=(20, 20, 20, 255))


# ---------- 素材加载 ----------

def list_persons() -> list:
    """返回所有 a 开头的人物图路径."""
    out = []
    for f in sorted(glob.glob(os.path.join(PERSON_DIR, "*"))):
        name = os.path.basename(f).lower()
        if name.startswith("a") and name[1:2].isdigit():
            out.append(f)
    return out


def find_hat(prefix: str):
    """大小写不敏感地找帽子文件,prefix 例如 'h1' / 'h2'."""
    for f in glob.glob(os.path.join(HAT_DIR, "*")):
        if os.path.basename(f).lower().startswith(prefix.lower()):
            return f
    return None


def load_products() -> list:
    """返回可用于合成的产品列表：MCP catalog 里已上架、且本地图已落盘的.

    与 avatar/manifest.json 的导出范围一致，保证命令行 / 网页「随机那口」
    永远出自同一批单品。
    """
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    prods = []
    for p in data["products"]:
        if not p.get("in_catalog"):
            continue
        img = _food_path(p.get("code"))
        if img:
            p["_local_img"] = img
            prods.append(p)
    return prods


def _food_path(code) -> str | None:
    for ext in (".png", ".gif"):
        fp = os.path.join(IMG_DIR, f"{code}{ext}")
        if os.path.exists(fp):
            return fp
    return None


# ---------- 几何工具 ----------

def content_bbox(im: Image.Image):
    """基于 alpha 求实际内容包围盒 (left, top, right, bottom)."""
    alpha = im.split()[3]
    return alpha.getbbox() or (0, 0, im.width, im.height)


def paste_center(canvas: Image.Image, layer: Image.Image, cx: int, cy: int):
    """把 layer 中心对齐到画布 (cx, cy)."""
    x = int(cx - layer.width / 2)
    y = int(cy - layer.height / 2)
    canvas.alpha_composite(layer, (x, y))


def scale_to_width(im: Image.Image, w: int) -> Image.Image:
    ratio = w / im.width
    return im.resize((w, int(im.height * ratio)), Image.LANCZOS)


# ---------- 合成 ----------

def detect_head_top(fig: Image.Image) -> int:
    """扫描人物图,返回中央区域内容最高点(y),即头顶.

    只看横向中间 30%~70%(避开两侧垂下的头发),取从上往下第一个有像素的行.
    """
    alpha = fig.split()[3]
    w, h = alpha.size
    x0, x1 = int(w * 0.35), int(w * 0.65)
    for y in range(h):
        row = alpha.crop((x0, y, x1, y + 1)).getbbox()
        if row is not None:
            return y
    return int(h * 0.2)


def compose(mode: str = "random", seed: int | None = None,
            person: str | None = None, code: str | None = None,
            bubble_text: str | None = None) -> dict:
    rng = random.Random(seed)

    persons = list_persons()
    if not persons:
        raise RuntimeError("assets/avatar 下未找到 a 开头的人物素材")

    # 选人物
    if person:
        ppath = next((p for p in persons if os.path.basename(p).lower() == person.lower()),
                     os.path.join(PERSON_DIR, person))
    else:
        ppath = rng.choice(persons)

    # 决定模式
    if mode == "random":
        mode = rng.choice(["hat_only", "with_food"])

    # 聊天框文字(未指定时随机,""=不显示)
    bubble = bubble_text if bubble_text is not None else rng.choice(BUBBLE_TEXTS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))

    # 1. 人物底：等比缩放+平移，把头顶对齐到画布 TARGET_HEAD_TOP，
    #    给上方腾出戴帽+放食物的空间（底部允许裁切，头像聚焦上半身）
    fig = Image.open(ppath).convert("RGBA")
    raw_head = detect_head_top(fig)
    scale = CANVAS / fig.width               # 统一到 1000 基准
    fig = fig.resize((CANVAS, int(fig.height * scale)), Image.LANCZOS)
    head_top = raw_head * scale
    dy = int(TARGET_HEAD_TOP - head_top)     # 人物垂直平移量(可正可负)
    canvas.alpha_composite(fig, (0, dy))
    head_top = TARGET_HEAD_TOP               # 对齐后统一以此为基准
    cx = CANVAS // 2
    # 人物内容最左边缘(供聊天框避让)
    fb = fig.split()[3].getbbox() or (0, 0, fig.width, fig.height)
    fig_left_x = int(fb[0] * scale)

    product_meta = None
    hat_path = None

    if mode == "hat_only":
        hat_path = find_hat("h1")
        if not hat_path:
            raise RuntimeError("未找到普通帽素材 h1(assets/avatar/h1.png)")
        hat = Image.open(hat_path).convert("RGBA")
        hat = hat.crop(content_bbox(hat))
        hat = scale_to_width(hat, HAT_W)
        # 帽子正常戴在头顶：帽底落在头顶下方,可水平偏移
        hat_bottom = head_top + HAT_OVERLAP
        paste_center(canvas, hat, cx + HAT_DY, hat_bottom - hat.height // 2)
    else:  # with_food
        hat_path = find_hat("h2")
        if not hat_path:
            raise RuntimeError("未找到顶食帽素材 H2(assets/avatar/H2.png)")
        hat = Image.open(hat_path).convert("RGBA")
        hat = hat.crop(content_bbox(hat))
        hat = scale_to_width(hat, HAT_W)
        hat_cx = cx + HAT_DY                             # 帽子中心(含水平偏移)
        hat_bottom = head_top + HAT_OVERLAP          # 与 hat_only 戴帽位置一致
        hat_cy = hat_bottom - hat.height // 2
        hat_top = hat_cy - hat.height // 2

        # 选食物
        prods = load_products()
        if code:
            prod = next((p for p in prods if str(p["code"]) == str(code)), rng.choice(prods))
        else:
            prod = rng.choice(prods)
        food = Image.open(prod["_local_img"]).convert("RGBA")
        food = food.crop(content_bbox(food))
        food = scale_to_width(food, FOOD_W)

        # 以帽顶为基准向上放食物：AUTO_SHRINK 开启时,食物高度自适应
        # 「帽顶到画布顶」的可用空间,竖高食物(如杯子)自动缩小不超出顶部
        avail = max(hat_top - MARGIN_TOP + 40, 80)
        if AUTO_SHRINK and food.height > avail:
            k = avail / food.height
            food = food.resize((int(food.width * k), int(food.height * k)), Image.LANCZOS)

        # 旋转(视觉顺时针):PIL rotate 为逆时针,取负角;expand 保留全图
        # 注:Python 端先缩放后旋转(expand 撞大包围),Web 端旋转绘制不撑大,
        #    两者食物中心位置一致,旋转角度较大时视觉尺寸略有差异
        if FOOD_ROT:
            food = food.rotate(-FOOD_ROT, expand=True, resample=Image.BICUBIC)

        food_cy = hat_top - food.height // 2 - FOOD_DY   # 相对帽顶的上下偏移
        food_cx = hat_cx + int(HAT_W * FOOD_DX_RATIO)    # 相对帽子中心的左右偏移
        # Z 轴:食物在帽子下层 → 先画食物,再画帽子盖在其上
        paste_center(canvas, food, food_cx, food_cy)
        paste_center(canvas, hat, hat_cx, hat_cy)

        product_meta = {
            "product_code": prod["code"],
            "product_name": prod["name"],
            "shape_type": prod["shape_type"],
            "price": prod.get("price"),
            "kcal": (prod.get("nutrition") or {}).get("kcal"),
        }

    # 4. 人物左侧漫画聊天框(最上层;文字为空则不画)
    draw_bubble(canvas, bubble, seed or 0, fig_left_x)

    # 输出
    os.makedirs(OUT_DIR, exist_ok=True)
    tag = str(seed) if seed is not None else f"rand{rng.randint(1000, 9999)}"
    out_png = os.path.join(OUT_DIR, f"avatar_{tag}.png")
    canvas.convert("RGB").save(out_png)

    meta = {
        "seed": seed,
        "mode": mode,
        "person": os.path.basename(ppath),
        "hat": os.path.basename(hat_path),
        "bubble": bubble,
        **({"product": product_meta} if product_meta else {}),
        "image": os.path.relpath(out_png, BASE),
    }
    with open(os.path.join(OUT_DIR, f"avatar_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="random", choices=["random", "hat_only", "with_food"])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--person", default=None, help="指定人物文件名,如 a3.png")
    ap.add_argument("--code", default=None, help="指定食物产品 code")
    ap.add_argument("--bubble", default=None,
                    help=f"聊天框文字,可选: {'/'.join(t or '空' for t in BUBBLE_TEXTS)}; 不传则随机")
    args = ap.parse_args()
    meta = compose(args.mode, args.seed, args.person, args.code,
                   args.bubble if args.bubble is not None else None)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
