"""麦当劳 MCP Server 客户端封装。

处理三个已实测的协议级坑：
1. 服务端不返回 mcp-session-id —— 每次 tools/call 前都要重新 initialize（无状态）。
2. 响应可能是纯 JSON，也可能是 SSE（data: 行）—— 需双格式解析。
3. tools/call 返回的 text 是「说明文字 + 嵌入 JSON」混合格式 —— 需抽取真正的 JSON body。

Token 从环境变量 MCDONALD_TOKEN 读取，禁止硬编码。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

MCP_URL = "https://mcp.mcd.cn"


class McdMcpError(RuntimeError):
    pass


def _get_token() -> str:
    token = os.environ.get("MCDONALD_TOKEN")
    if not token:
        # 兜底：mcp/.env 优先，其次项目根 .env
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = (os.path.join(here, ".env"),
                      os.path.join(os.path.dirname(here), ".env"))
        env_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("MCDONALD_TOKEN"):
                        token = line.split("=", 1)[1].strip().rstrip("%")
                        break
    if not token:
        raise McdMcpError("未找到 MCDONALD_TOKEN，请在环境变量或 .env 中配置")
    return token


def _post(payload: dict, token: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        MCP_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8").strip()
    # 双格式解析：优先 JSON，失败则按 SSE data: 行拆
    if raw.startswith("{"):
        return json.loads(raw)
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise McdMcpError(f"无法解析响应: {raw[:200]}")


class McdMcpClient:
    def __init__(self):
        self.token = _get_token()
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _initialize(self):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "shimaimairen-client", "version": "1.0"},
            },
        }
        _post(payload, self.token)

    def list_tools(self) -> list:
        self._initialize()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        data = _post(payload, self.token)
        return data["result"]["tools"]

    def call(self, tool: str, arguments: dict) -> dict:
        """调用工具，返回抽取后的业务 JSON（success/code/data 结构）。"""
        # 无会话：每次调用前重新握手
        self._initialize()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        data = _post(payload, self.token)
        result = data.get("result", {})
        if result.get("isError"):
            raise McdMcpError(f"{tool} 调用出错: {result}")
        content = result.get("content", [])
        text = ""
        for c in content:
            if c.get("type") == "text":
                text += c.get("text", "")
        return _extract_business_json(tool, text)


def _extract_business_json(tool: str, text: str) -> dict:
    """从「说明文字 + 嵌入 JSON」混合文本中抽取业务 JSON。

    部分工具（如 list-nutrition-foods）的 data 字段本身是字符串（类 CSV），
    部分工具返回多个拼接的 JSON —— 用 raw_decode 取第一个完整对象。
    """
    if not text:
        return {}
    m = re.search(r'\{"success"', text)
    idx = m.start() if m else text.find("{")
    if idx == -1:
        return {"_raw": text}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[idx:])
        return obj
    except json.JSONDecodeError:
        # 回退：整体尝试
        try:
            return json.loads(text[idx:])
        except json.JSONDecodeError:
            return {"_raw": text}
