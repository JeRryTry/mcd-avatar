"""项目自检：MCP 数据源、素材、avatar 静态产物与出图链路是否一致。

用法（在项目根目录执行）：
    .venv/bin/python tools/check.py

任一检查失败则退出码为 1，便于提交前跑一遍。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(BASE, "mcp", "data", "catalog.json")
IMG_DIR = os.path.join(BASE, "mcp", "assets", "img")
AVATAR = os.path.join(BASE, "avatar")
MANIFEST = os.path.join(AVATAR, "manifest.json")
IMG_EXTS = (".png", ".gif", ".jpg", ".jpeg")

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ✓ " if ok else "  ✗ ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def has_image(code) -> bool:
    return any(os.path.exists(os.path.join(IMG_DIR, f"{code}{ext}")) for ext in IMG_EXTS)


def check_catalog() -> tuple[list[dict], set[str], set[str]]:
    print("[1] MCP 数据源 mcp/data/catalog.json")
    check("文件存在", os.path.exists(CATALOG))
    if not os.path.exists(CATALOG):
        return [], set(), set()

    data = load_json(CATALOG)
    items = data.get("products") or []
    meta = data.get("meta") or {}
    codes = [str(p.get("code")) for p in items]

    check("产品数 > 0", len(items) > 0, str(len(items)))
    check("code 无重复", len(codes) == len(set(codes)))
    check("meta.total_products 与实际一致", meta.get("total_products") == len(items),
          f"{meta.get('total_products')} vs {len(items)}")
    check("meta.listed 与实际上架一致",
          meta.get("listed") == sum(1 for p in items if p.get("in_catalog") and p.get("local_image")),
          str(meta.get("listed")))
    check("meta.with_local_image 与实际落图一致",
          meta.get("with_local_image") == sum(1 for p in items if p.get("local_image")),
          str(meta.get("with_local_image")))
    check("local_image 指向的文件都存在",
          all(os.path.exists(os.path.join(BASE, "mcp", p["local_image"]))
              for p in items if p.get("local_image")))

    listed = {str(p["code"]) for p in items if p.get("in_catalog")}
    with_image = {str(p["code"]) for p in items if has_image(p.get("code"))}
    ready = listed & with_image

    check("上架集合非空", bool(listed), str(len(listed)))
    check("上架集合是菜单真子集（套餐/非餐品/重名已排除）", len(listed) < len(codes),
          f"{len(listed)} vs {len(codes)}")
    check("上架且有图的产品 > 0", bool(ready), str(len(ready)))
    return items, listed, ready


def check_manifest(listed: set[str], ready: set[str]) -> None:
    print("[2] avatar 导出产物 avatar/manifest.json")
    check("文件存在", os.path.exists(MANIFEST))
    if not os.path.exists(MANIFEST):
        return
    manifest = load_json(MANIFEST)
    items = manifest.get("products") or []
    meta = manifest.get("meta") or {}
    codes = {str(p["code"]) for p in items}

    check("导出集合 = 上架且有图", codes == ready,
          f"manifest {len(codes)} vs catalog {len(ready)}")
    check("每条产品都有图字段", all(p.get("src") for p in items))
    check("meta.listed 与产品数一致", meta.get("listed") == len(items), str(meta.get("listed")))
    check("meta.menu_total 与数据源一致",
          meta.get("menu_total") == (load_json(CATALOG).get("meta") or {}).get("total_products"))
    check("人物 7 个", len(manifest.get("persons") or []) == 7,
          str(len(manifest.get("persons") or [])))
    check("帽子含普通帽与顶食帽",
          {"plain", "food"} <= set((manifest.get("hats") or {}).keys()))
    check("气泡图已配置", bool(manifest.get("bubble")))


def check_assets() -> None:
    print("[3] avatar 静态资源")
    for name in ("index.html", "app.js", "mc-avatar.js", "style.css",
                 "wall.html", "use-cases.html", "promo.js", "promo.css"):
        check(f"{name} 存在", os.path.exists(os.path.join(AVATAR, name)))

    manifest = load_json(MANIFEST) if os.path.exists(MANIFEST) else {}
    missing = [p.get("src") for p in manifest.get("products") or []
               if not os.path.exists(os.path.join(AVATAR, p.get("src", "")))]
    check("产品图均已导出", not missing, f"缺失 {missing[:5]}")

    for key, v in (manifest.get("hats") or {}).items():
        check(f"帽子图 {key} 已导出", os.path.exists(os.path.join(AVATAR, v.get("src", ""))))
    for p in manifest.get("persons") or []:
        check(f"人物图 {p.get('id')} 已导出", os.path.exists(os.path.join(AVATAR, p.get("src", ""))))


def check_frontend() -> None:
    print("[4] 前端 JS 语法")
    node = shutil.which("node")
    if not node:
        print("  · 未找到 node，跳过 JS 语法检查")
        return
    targets = [
        os.path.join(AVATAR, "app.js"),
        os.path.join(AVATAR, "mc-avatar.js"),
        os.path.join(AVATAR, "promo.js"),
        os.path.join(BASE, "mcp", "manage.js"),
    ]
    for fp in targets:
        if not os.path.exists(fp):
            continue
        proc = subprocess.run([node, "--check", fp], capture_output=True, text=True)
        check(f"{os.path.basename(fp)} 语法通过", proc.returncode == 0,
              (proc.stderr or "").strip()[:200])


def check_compose(ready: set[str]) -> None:
    print("[5] 出图链路（tools/preview.py 参照实现）")
    try:
        import preview as pv
    except Exception as exc:  # 多为缺少 Pillow
        check("导入 preview", False, repr(exc))
        return
    try:
        check("有可出图的单品", bool(ready), str(len(ready)))
        code = sorted(ready)[0]
        meta = pv.compose(mode="with_food", code=code, seed=1, bubble_text="自检")
        out = os.path.join(BASE, meta["image"])
        size = os.path.getsize(out) if os.path.exists(out) else 0
        check("生成 PNG 且非空", size > 1000, f"{size} bytes")
        check("输出元信息完整", bool(meta.get("product")))
        for ext in (".png", ".json"):
            fp = os.path.splitext(out)[0] + ext
            if os.path.exists(fp):
                os.remove(fp)
    except Exception as exc:
        check("compose 执行", False, repr(exc))


def main() -> int:
    print("=== 今天什麦人 · 自检 ===\n")
    items, listed, ready = check_catalog()
    check_manifest(listed, ready)
    check_assets()
    check_frontend()
    check_compose(ready)
    print("\n" + ("全部通过 ✓" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
