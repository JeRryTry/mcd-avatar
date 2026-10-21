"""把 mcp/data/catalog.json 导出成 avatar/ 可以直接托管的静态数据（菜单更新的第 4 步）。

产物：
- ``avatar/manifest.json``         人物 + 帽子 + 聊天框 + 上架产品清单
- ``avatar/assets/foods/*.png``    只复制上架单品的官方图（清空重建，避免残留）

设计约束：
- avatar/ 是**纯静态**站点，不依赖 mcp/ 就能单独部署；本脚本是两者之间唯一的桥。
- manifest 里只出现「上架且图已落盘」的单品，前端不需要再判断上下架。
- 人物与帽子属于 avatar 自己的静态素材（``avatar/assets/persons|hats``），这里只补算
  头顶锚点 ``head_top_ratio``，不做复制，避免同一张图存两份。

策展规则见 ``clean_products.suggest_keep``；上下架请用 ``mcp/manage.py`` 或
``mcp/manage.html``，不要手改本脚本的产物。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from datetime import date

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))          # mcp/
ROOT = os.path.dirname(BASE)
CATALOG = os.path.join(BASE, "data", "catalog.json")
AVATAR = os.path.join(ROOT, "avatar")
PERSONS_DIR = os.path.join(AVATAR, "assets", "persons")
HATS_DIR = os.path.join(AVATAR, "assets", "hats")
FOODS_DIR = os.path.join(AVATAR, "assets", "foods")
MANIFEST = os.path.join(AVATAR, "manifest.json")


def detect_head_top(path: str) -> float:
    """与 mc-avatar.js / tools/preview.py 一致：中央列最高像素行，返回归一化比值。"""
    im = Image.open(path).convert("RGBA")
    alpha = im.split()[3]
    w, h = alpha.size
    x0, x1 = int(w * 0.35), int(w * 0.65)
    for y in range(h):
        if alpha.crop((x0, y, x1, y + 1)).getbbox() is not None:
            return round(y / h, 4)
    return 0.2


def export_persons() -> list[dict]:
    persons = []
    for f in sorted(glob.glob(os.path.join(PERSONS_DIR, "*.png"))):
        base = os.path.basename(f)
        stem = os.path.splitext(base)[0]
        if not (stem.lower().startswith("a") and stem[1:2].isdigit()):
            continue
        persons.append({
            "id": stem,
            "src": f"assets/persons/{base}",
            "head_top_ratio": detect_head_top(f),
        })
    return persons


def export_hats() -> tuple[dict, dict | None]:
    hats, bubble = {}, None
    for key, stem in (("plain", "h1"), ("food", "h2")):
        f = os.path.join(HATS_DIR, f"{stem}.png")
        if os.path.exists(f):
            hats[key] = {"src": f"assets/hats/{stem}.png"}
    chat = os.path.join(HATS_DIR, "chat2.png")
    if os.path.exists(chat):
        bubble = {"src": "assets/hats/chat2.png"}
    return hats, bubble


def main() -> None:
    if not os.path.exists(CATALOG):
        raise SystemExit("找不到 mcp/data/catalog.json，请先跑 python3 mcp/update_menu.py")
    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    all_products = catalog["products"]
    meta = catalog.get("meta") or {}

    for d in (PERSONS_DIR, HATS_DIR, FOODS_DIR):
        os.makedirs(d, exist_ok=True)

    # ---- 产品图：清空重建，只保留当前上架 ----
    for old in glob.glob(os.path.join(FOODS_DIR, "*")):
        if os.path.isfile(old):
            os.remove(old)

    products = []
    for p in all_products:
        if not p.get("in_catalog"):
            continue
        rel = p.get("local_image")
        src = os.path.join(BASE, rel) if rel else None
        if not src or not os.path.exists(src):
            continue
        dst_name = os.path.basename(src)
        shutil.copy(src, os.path.join(FOODS_DIR, dst_name))
        products.append({
            "code": p.get("code"),
            "name": p.get("name"),
            "shape_type": p.get("shape_type"),
            "price": p.get("price"),
            "kcal": (p.get("nutrition") or {}).get("kcal"),
            "src": f"assets/foods/{dst_name}",
        })

    persons = export_persons()
    hats, bubble = export_hats()

    manifest = {
        "generated_at": date.today().isoformat(),
        "source": "McDonald's China MCP (https://mcp.mcd.cn)",
        "canvas": 1000,
        "meta": {
            "menu_total": meta.get("total_products"),
            "with_local_image": meta.get("with_local_image"),
            "listed": len(products),
            "snapshot": meta.get("snapshot"),
        },
        "persons": persons,
        "hats": hats,
        "bubble": bubble,
        "products": products,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"人物 {len(persons)} | 帽子 {list(hats.keys()) or '缺失'} | 气泡 {'有' if bubble else '无'}")
    print(f"菜单全量 {meta.get('total_products')} | 本地图 {meta.get('with_local_image')}"
          f" | 导出上架 {len(products)}")
    missing = (meta.get("total_products") or 0) - len(products)
    if missing:
        print(f"未导出 {missing} 款：未上架 / 缺本地图（跑 python3 mcp/manage.py --list 查看原因）")
    print(f"已写 {os.path.relpath(MANIFEST, ROOT)}")


if __name__ == "__main__":
    main()
