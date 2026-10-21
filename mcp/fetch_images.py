"""把 MCP 返回的官方产品图下载到 mcp/assets/img/（菜单更新的第 3 步）。

`merge_full.py` 只整理出 `image_url`，图片本身要落到本地才能参与合成。
本脚本默认**只下载已上架的单品**（catalog.json 里 `in_catalog: true`），
避免把套餐/组合图也拖进仓库；`--all` 可下载全量菜单。

下载完成后会回写 catalog.json 的 `local_image` / `meta.with_local_image` / `meta.listed`，
这样数据源自己就能说明「哪些图已经就位」，不需要再维护额外的清单文件。

用法：
    python3 mcp/fetch_images.py              # 补齐上架单品的图（已存在则跳过）
    python3 mcp/fetch_images.py --all        # 全量菜单都下
    python3 mcp/fetch_images.py --dry-run    # 只看会下多少
    python3 mcp/fetch_images.py --force      # 覆盖已有文件
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(BASE, "data", "catalog.json")
IMG_DIR = os.path.join(BASE, "assets", "img")
IMG_EXTS = (".png", ".gif", ".jpg", ".jpeg")
UA = "Mozilla/5.0 (compatible; mcd-avatar/1.0)"


def local_image(code) -> str | None:
    """本地图相对路径（assets/img/xxx.png），没有则 None。"""
    for ext in IMG_EXTS:
        f = f"{code}{ext}"
        if os.path.exists(os.path.join(IMG_DIR, f)):
            return f"assets/img/{f}"
    return None


def ext_of(url: str) -> str:
    suffix = os.path.splitext(urlparse(url).path)[1].lower()
    return suffix if suffix in IMG_EXTS else ".png"


def download(url: str, dst: str, retries: int = 2) -> int:
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if len(data) < 500:                     # 明显不是图，别写脏文件
                raise RuntimeError(f"响应过小 {len(data)}B")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            return len(data)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(str(last))


def refresh_catalog() -> dict:
    """按磁盘实际文件回写 local_image 与计数，保证数据源自洽。"""
    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    with_local = listed = 0
    for p in catalog["products"]:
        p["local_image"] = local_image(p.get("code"))
        if p["local_image"]:
            with_local += 1
            if p.get("in_catalog"):
                listed += 1
    catalog["meta"]["with_local_image"] = with_local
    catalog["meta"]["listed"] = listed
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    return {"with_local_image": with_local, "listed": listed}


def main() -> int:
    ap = argparse.ArgumentParser(description="下载 MCP 官方产品图到 mcp/assets/img/")
    ap.add_argument("--all", action="store_true", help="全量菜单都下载（默认只下已上架的）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的本地图")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不下载")
    args = ap.parse_args()

    if not os.path.exists(CATALOG):
        raise SystemExit("找不到 mcp/data/catalog.json，请先跑 python3 mcp/update_menu.py")

    with open(CATALOG, encoding="utf-8") as f:
        items = json.load(f)["products"]

    todo, skipped, no_url = [], 0, 0
    for p in items:
        code = str(p.get("code"))
        if not args.all and not p.get("in_catalog"):
            continue                       # 未上架的不下，省仓库体积
        if not p.get("image_url"):
            no_url += 1
            continue
        if local_image(code) and not args.force:
            skipped += 1
            continue
        todo.append(p)

    print(f"菜单 {len(items)} 款 | 待下载 {len(todo)} | 已有跳过 {skipped} | 无图URL {no_url}")
    if args.dry_run:
        for p in todo[:20]:
            print(f"  - {p.get('code')}  {p.get('name')}")
        if len(todo) > 20:
            print(f"  ... 其余 {len(todo) - 20} 款")
        print("[dry-run] 未下载任何文件。")
        return 0

    ok, fail, total = 0, [], 0
    for p in todo:
        code = str(p.get("code"))
        dst = os.path.join(IMG_DIR, f"{code}{ext_of(p['image_url'])}")
        try:
            total += download(p["image_url"], dst)
            ok += 1
            if ok % 20 == 0:
                print(f"  进度 {ok}/{len(todo)}")
        except Exception as exc:  # noqa: BLE001
            fail.append((code, p.get("name"), str(exc)[:60]))
        time.sleep(0.05)                   # 轻微限速，别打 CDN

    print(f"下载完成 {ok} 张，共 {total / 1024:.0f} KB")
    if fail:
        print(f"失败 {len(fail)} 张：")
        for code, name, err in fail[:10]:
            print(f"  - {code} {name}: {err}")
        print("这些单品会因缺图而无法合成，可稍后重跑本脚本补齐。")

    if ok:
        counts = refresh_catalog()
        print(f"catalog 已更新：本地图 {counts['with_local_image']} 张"
              f" | 上架可合成 {counts['listed']} 款")
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
