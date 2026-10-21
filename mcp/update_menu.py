"""更新麦当劳菜单 —— 一条命令把 MCP 上的真实菜单同步到项目里。

这是本项目**唯一需要联网**的环节，也是麦当劳 MCP 的消费点：

    [1] 采集  query-nearby-stores → query-meals → query-meal-detail → list-nutrition-foods
              ↓ 落盘 mcp/data/raw/（原始响应，可离线重算）
    [2] 清洗  按 code 去重 + 名称归一化 + 营养对齐   → mcp/data/catalog.json
    [3] 图片  官方产品图 → mcp/assets/img/           → 已上架单品（--all 可全量）
    [4] 导出  上架单品 + 素材 → avatar/manifest.json（纯静态站点直接可跑）

用法（在项目根目录执行）：
    python3 mcp/update_menu.py                 # 全流程（需要 MCDONALD_TOKEN）
    python3 mcp/update_menu.py --skip-fetch    # 跳过联网，用已有原始响应重算并导出
    python3 mcp/update_menu.py --check         # 只检查 Token / 原始数据是否就绪
    python3 mcp/update_menu.py --no-images     # 跳过图片下载（只用已有本地图）

采集一次约数分钟（30 城门店 + 套餐拆解，带限速与断点续跑）。
avatar/ 不依赖本脚本运行——它只读已经导出的 manifest.json，可以单独部署。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))          # mcp/
ROOT = os.path.dirname(BASE)
RAW = os.path.join(BASE, "data", "raw")
CATALOG = os.path.join(BASE, "data", "catalog.json")
MANIFEST = os.path.join(ROOT, "avatar", "manifest.json")
ENV_CANDIDATES = (os.path.join(BASE, ".env"), os.path.join(ROOT, ".env"))


def step(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}", flush=True)


def run(script: str, label: str, allow_fail: bool = False) -> int:
    print(f"→ {label}（mcp/{script}）", flush=True)
    proc = subprocess.run([sys.executable, os.path.join(BASE, script)], cwd=ROOT)
    if proc.returncode != 0:
        if allow_fail:
            print(f"⚠️ {label}有失败项（退出码 {proc.returncode}），继续执行后续步骤", flush=True)
            return proc.returncode
        raise SystemExit(f"✗ {label}失败，退出码 {proc.returncode}")
    return 0


def has_token() -> bool:
    if os.environ.get("MCDONALD_TOKEN"):
        return True
    for path in ENV_CANDIDATES:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if any(line.strip().startswith("MCDONALD_TOKEN=") for line in f):
                    return True
    return False


def catalog_codes() -> set[str]:
    """当前 catalog 里已上架的 code。"""
    if not os.path.exists(CATALOG):
        return set()
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    return {str(p["code"]) for p in data.get("products", []) if p.get("in_catalog")}


def manifest_listed() -> int:
    if not os.path.exists(MANIFEST):
        return 0
    with open(MANIFEST, encoding="utf-8") as f:
        return len(json.load(f).get("products") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description="更新麦当劳菜单（MCP 采集 → 清洗 → 下图 → 导出）")
    ap.add_argument("--skip-fetch", action="store_true", help="跳过 MCP 采集，用 data/raw/ 已有响应重算")
    ap.add_argument("--no-images", action="store_true", help="跳过官方图下载")
    ap.add_argument("--check", action="store_true", help="只做前置检查，不执行")
    args = ap.parse_args()

    raw_ready = os.path.exists(os.path.join(RAW, "meals_by_store_v2.json"))
    token_ready = has_token()
    print(f"Token：{'已配置' if token_ready else '未配置（见 .env.example）'}", flush=True)
    print(f"原始响应：{'已就绪 mcp/data/raw/' if raw_ready else '缺失'}", flush=True)
    print(f"头像端：{'已导出 ' + str(manifest_listed()) + ' 款' if os.path.exists(MANIFEST) else '尚未导出'}",
          flush=True)

    if args.check:
        if not args.skip_fetch and not token_ready:
            print("\n提示：没有 Token 也能跑 --skip-fetch，用仓库里已有的原始响应重算。")
        return 0

    if not args.skip_fetch:
        if not token_ready:
            raise SystemExit(
                "✗ 未找到 MCDONALD_TOKEN。\n"
                "  · 申请：https://mcp.mcd.cn\n"
                "  · 配置：cp .env.example .env 后填入 Token，或 export MCDONALD_TOKEN=...\n"
                "  · 只想重算已有数据：python3 mcp/update_menu.py --skip-fetch"
            )
        step("[1/4] 采集：麦当劳 MCP → mcp/data/raw/")
        run("fetch_full.py", "MCP 采集")
    else:
        if not raw_ready:
            raise SystemExit("✗ mcp/data/raw/ 里没有采集结果，无法跳过采集。")
        print("\n已跳过 MCP 采集，使用现有原始响应。")

    before = catalog_codes()

    step("[2/4] 清洗：合并去重 + 营养对齐 → data/catalog.json")
    run("merge_full.py", "清洗合并")

    if args.no_images:
        print("\n已跳过官方图下载（--no-images）。")
    else:
        step("[3/4] 官方图落盘：image_url → mcp/assets/img/")
        run("fetch_images.py", "下载官方产品图", allow_fail=True)

    step("[4/4] 导出：上架单品 → avatar/")
    run("export_avatar.py", "导出头像数据")

    after = catalog_codes()
    added, removed = sorted(after - before), sorted(before - after)
    print(f"\n菜单已更新：头像候选 {len(after)} 款，avatar 实际导出 {manifest_listed()} 款")
    if before:
        print(f"  新增 {len(added)} 款" + (f"：{', '.join(added[:8])}" if added else ""))
        print(f"  下线 {len(removed)} 款" + (f"：{', '.join(removed[:8])}" if removed else ""))
    print("\n新品的上下架沿用建议规则；要手工调整：")
    print("  python3 mcp/manage.py --list                  # 看清单")
    print("  python3 mcp/manage.py --off 123,456           # 下架")
    print("  或起 mcp/ 静态服务打开 manage.html 点选")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
