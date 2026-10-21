# MCP 集成说明（MCP_INTEGRATION.md）

本项目「今天什麦人」真实接入并调用了 **麦当劳中国 MCP Server**（`https://mcp.mcd.cn`，Streamable HTTP 协议）。

MCP 在本项目里不是开发期的一次性抓数脚本，而是 **`mcp/` 这个目录的立身之本**：
它既是头像数据的唯一来源，也是「更新麦当劳菜单」这个可以反复运行的功能。

```
mcp/      数据源：拉最新菜单 + 管理菜品         ← 消费 MCP 的地方
avatar/   纯静态头像生成器，只读 mcp 导出的清单  ← 消费数据的地方
```

## 使用的 MCP Server

| 项 | 值 |
| --- | --- |
| Server | `mcd-mcp` v1.0.0 |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（JSON-RPC 2.0） |
| 鉴权 | `Authorization: Bearer ${MCDONALD_TOKEN}`（环境变量占位，仓库不含真实 Token） |

## 实际调用的 Tool

全部为只读查询类，无下单/领券等副作用：

| Tool | 用途 | 关键返回 |
| --- | --- | --- |
| `now-time-info` | 获取服务器时间，作为「今日之麦」确定性种子 | 时间戳、日期 |
| `query-nearby-stores` | 遍历 30 个城市门店，拿到 `storeCode` | 门店列表 |
| `query-meals` | 拉取每个门店完整菜单 | 产品名称/价格/**图片 URL**/分类/tag |
| `query-meal-detail` | 拆套餐子单品、补查单品详情 | `rounds.choices`、`modification`、官方图 |
| `list-nutrition-foods` | 全量餐品营养数据 | `kcal`/蛋白/脂肪/碳水/钠/钙 |
| `campaign-calendar` | 当月营销活动日历 | 活动信息（用于后续扩展） |

其中 **产品图片** 直接来自 `query-meals` 返回的 `image` 字段（`menu-img.mcd.cn` CDN），
这是本项目「插画化头像」创意的原始素材来源。

## 调用流程

```
python3 mcp/update_menu.py               ← 一条命令串起下面四步
        │
[1] 采集  mcp/fetch_full.py
        query-nearby-stores(30 城) ──→ storeCode[]
        query-meals(storeCode)     ──→ 菜单 + 图片URL + 价格 + 分类     ┐
        query-meal-detail          ──→ 拆套餐子单品 + 补单品详情        ├→ mcp/data/raw/
        list-nutrition-foods()     ──→ 营养表(kcal 等)                 ┘
        │
[2] 清洗  mcp/merge_full.py + clean_products.py
        按 code 去重 + 名称归一化 + 营养对齐
        ──→ mcp/data/catalog.json（全量 250 款；继承上次的人工上下架状态）
        │
[3] 图片  mcp/fetch_images.py
        image_url ──→ mcp/assets/img/（默认只下已上架单品）
        │
[4] 导出  mcp/export_avatar.py
        只取 in_catalog + 有本地图的单品 ──→ avatar/manifest.json + avatar/assets/foods/
        │
        ├─→ avatar/index.html   单页应用（浏览器里实时合成）
        └─→ avatar/mc-avatar.js 引擎（可嵌入他人项目）
```

**菜品管理**（`mcp/manage.py` 或 `mcp/manage.html`）决定哪些单品能上头像：
250 款里官方图已落本地 227 款，再按「不要套餐/组合装、不要非餐品（玩具/酱料包等）、同名只留一条」
筛出 148 款。状态写在 `catalog.json` 的 `in_catalog` 字段里，**下架不删数据、不删图**。

所以「MCP 数据」在项目里有两次消费：

1. **构建期**：`mcp/` 把 MCP 的菜单变成 `avatar/manifest.json`；
2. **运行时**：`avatar/` 把这份清单变成一张可以发出去的头像。

客户端封装见 `mcp/mcp_client.py`，处理了三个实测发现的协议级细节：

1. **无会话**：服务端不返回 `mcp-session-id`，每次 `tools/call` 前需重新 `initialize`；
2. **双格式响应**：可能是纯 JSON 或 SSE（`data:` 行），需兼容解析；
3. **混合文本**：`content[].text` 是「字段说明 + 嵌入 JSON」，需用 `raw_decode` 抽取业务 JSON。

## 业务价值

- 麦当劳 MCP 提供了**真实、全量、带官方图片**的产品数据，是本创意的数据底座；
- 项目把 MCP 的结构化数据（名称/价格/营养/图片）转化为**可传播的视觉内容**（麦当劳头像），
  拓展了 MCP 能力的使用场景 —— 从「查菜单」变成「拿菜单做内容」；
- 菜单会变（新品、下架、季节限定），所以「更新菜单」是可反复执行的功能，
  而不是一次性爬虫：跑完会直接报告本次新增/下线的单品；
- 全流程离线可复现：采集一次后，清洗、策展、合成都不再联网，低配机器也能跑。
