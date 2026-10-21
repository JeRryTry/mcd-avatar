#!/usr/bin/env python3
"""本地开发服务：静态文件 + 一个保存接口，让管理页直接写回 catalog.json 并重新导出头像。

零依赖（仅标准库）。它替换 `python -m http.server` 的唯一原因：静态服务器无法接收并保存
页面提交的数据。本脚本在静态服务之外只多了一个 POST 接口，不做任何「远程服务」性质的事。

用法：
    python3 mcp/serve.py                 # 默认项目根 + 8777
    python3 mcp/serve.py --port 9000     # 换端口
    python3 mcp/serve.py --directory /abs/project/root

访问：
    头像页   http://localhost:8777/avatar/index.html
    管理页   http://localhost:8777/mcp/manage.html
保存接口   POST /api/save-catalog  body: {"selected": ["code1","code2",...]}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))            # mcp/
ROOT = os.path.dirname(BASE)                                  # 项目根
CATALOG = os.path.join(BASE, "data", "catalog.json")
EXPORT = os.path.join(BASE, "export_avatar.py")

if BASE not in sys.path:
    sys.path.insert(0, BASE)
import manage  # noqa: E402  写盘只走 manage.save 这一处，保证 meta 同步


def _export_interpreter() -> str:
    """优先用装了 Pillow 的项目 venv，退回当前解释器。"""
    cand = os.path.join(ROOT, ".venv", "bin", "python")
    return cand if os.path.exists(cand) else sys.executable


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = self.server.root  # 静态根 = 项目根

    def end_headers(self) -> None:
        # 开发期禁止浏览器缓存，避免保存后头像页仍读旧的 manifest/catalog
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # 浏览器跨域/预检请求：明确放行，避免被 501 掐断后续 POST
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/save-catalog":
            self._send_json({"ok": False, "error": "未知接口"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
        except Exception as exc:  # noqa: BLE001
            print(f"[save] 请求体解析失败: {exc}", file=sys.stderr, flush=True)
            self._send_json({"ok": False, "error": "请求体解析失败: " + str(exc)}, 400)
            return

        selected = {str(c) for c in (payload.get("selected") or [])}
        print(f"[save] 收到 POST，selected {len(selected)} 款", file=sys.stderr, flush=True)
        try:
            with open(CATALOG, "r", encoding="utf-8") as f:
                catalog = json.load(f)
            for p in catalog.get("products", []):
                p["in_catalog"] = str(p.get("code")) in selected
            manage.save(catalog)   # 顺带刷新 meta.listed，避免与实际上架数不一致
        except Exception as exc:  # noqa: BLE001
            print(f"[save] 写 catalog 失败: {exc}", file=sys.stderr, flush=True)
            self._send_json({"ok": False, "error": "写 catalog 失败: " + str(exc)}, 500)
            return

        products = catalog.get("products", [])
        listed = sum(1 for p in products if p.get("in_catalog"))
        ready = sum(1 for p in products if p.get("in_catalog") and p.get("local_image"))
        export_msg = ""
        try:
            r = subprocess.run(
                [_export_interpreter(), EXPORT],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                export_msg = "（但导出失败：" + (r.stderr or r.stdout).strip()[:200] + "）"
        except Exception as exc:  # noqa: BLE001
            export_msg = "（但导出异常：" + str(exc) + "）"

        print(f"[save] 已写 catalog，上架 {listed} 款（可就绪出图 {ready} 款）；导出{export_msg or '成功'}",
              file=sys.stderr, flush=True)
        self._send_json({"ok": True, "listed": listed, "ready": ready, "export": export_msg})

    def log_message(self, *args):  # 静默静态请求日志
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="MDC 本地开发服务（静态 + 保存接口）")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--directory", default=ROOT, help="静态根目录，默认项目根")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    httpd.root = os.path.abspath(args.directory)
    print(f"本地服务已启动：http://localhost:{args.port}")
    print(f"  静态根   {httpd.root}")
    print(f"  头像页   http://localhost:{args.port}/avatar/index.html")
    print(f"  管理页   http://localhost:{args.port}/mcp/manage.html")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
