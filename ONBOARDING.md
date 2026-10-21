# 维护与数据手册 · 今天什麦人

> 文档分工（避免重复）：
> - `README.md` —— 对外介绍、玩法、嵌入方式（**权威使用文档**）
> - 本文件 —— 环境细节、数据流水线、菜品管理、排错（**只写 README 没有的**）
> - `MCP_INTEGRATION.md` —— 麦当劳 MCP 接入细节
> - `PROJECT_NOTES.md` —— 作者开发日志与进度

## 1. 架构：一条单向数据链

```
麦当劳 MCP Server
      │  ① 采集（需要 Token）
      ▼
mcp/data/raw/           原始响应，可离线重算
      │  ② 清洗
      ▼
mcp/data/catalog.json   ★ 唯一数据源：全量菜单 + 上下架 + 本地图
      │  ③ 官方图落盘 / ④ 导出（只导上架）
      ▼
avatar/manifest.json  +  avatar/assets/foods/     ★ 纯静态产物
      │
      ▼
浏览器：单页应用 / 嵌入方调用 mc-avatar.js
```

两条硬边界：

1. **数据只从 `mcp/` 流向 `avatar/`**。`avatar/manifest.json` 是产物，不要手改；
   想改菜品就改 `catalog.json`（通过 `manage.py` 命令行或 `mcp/serve.py` 图形界面），
   保存时会自动重跑导出。
2. **`avatar/` 不依赖 Python**。它可以单独部署、单独分发；Python 只在更新菜单时出现。

## 2. 环境准备

- Python 3.9+（开发用 3.13）；Python 端唯一第三方依赖 **Pillow**。
- `avatar/` 纯原生 HTML/JS，**零依赖、零构建**。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # 仅 Pillow
```

> 项目内已有 `.venv/`，直接 `source .venv/bin/activate` 即可。
> 未激活 / 未装 Pillow 时，`export_avatar.py`、`tools/preview.py`、`tools/check.py`
> 会报 `ModuleNotFoundError: No module named 'PIL'`。

**MCP Token 只有「更新菜单」需要**，看页面、出图、导出都不需要。

```bash
cp .env.example mcp/.env      # 编辑填入 MCDONALD_TOKEN=...
# 放项目根 .env 也可以，脚本会先找 mcp/.env，再回退根目录
```

## 3. 数据职责（先理解这个，后面才不会乱）

| 文件 | 是什么 | 会不会被覆盖 |
| --- | --- | --- |
| `mcp/data/raw/*.json` | MCP 原始响应（已 gitignore，可重新采集） | 采集时覆盖 |
| `mcp/data/catalog.json` | **唯一数据源**：250 款全量菜单，每条带 `in_catalog`(上下架)、`local_image`(本地图)、`hint`(建议原因) | `merge_full.py` 重写，**但会继承旧的人工上下架状态** |
| `mcp/assets/img/` | 227 张官方产品原图 | `fetch_images.py` 增量补齐，不删 |
| `avatar/manifest.json` | 导出产物：只含「上架且有图」的单品 | 每次导出重写 |
| `avatar/assets/foods/` | 上架单品的图（清空重建） | 每次导出重写 |

关键点：**上架 / 下架不删数据**。状态只是 `catalog.json` 里的一个布尔字段，
条目和图片都保留，`--on` 加回来重跑导出就恢复。

## 4. 更新菜单（消费 MCP 的唯一入口）

```bash
python3 mcp/update_menu.py               # 采集 → 清洗 → 下图 → 导出，一条命令
python3 mcp/update_menu.py --check       # 只看 Token / 原始数据是否就绪
python3 mcp/update_menu.py --skip-fetch  # 不调 MCP，用已有原始响应重算
python3 mcp/update_menu.py --no-images   # 不下载官方图（只用已有本地图）
```

内部就是四步，也可以单独跑：

```bash
python3 mcp/fetch_full.py        # ① MCP 采集 → mcp/data/raw/
python3 mcp/merge_full.py        # ② 清洗合并 → mcp/data/catalog.json（继承旧上下架）
python3 mcp/fetch_images.py      # ③ 官方图 → mcp/assets/img/（默认只下已上架单品）
python3 mcp/export_avatar.py     # ④ 只导上架单品 → avatar/manifest.json
```

> 第 ③ 步容易漏：`merge_full.py` 只整理出 `image_url`，图不落地就没法合成。
> 默认只下载已上架单品的图；`--all` 才下全量（仓库会大不少）。

采集较慢（30 城门店 + 套餐拆解 + 营养表，带限速与断点续跑），跑完
`update_menu.py` 会打印**本次新增 / 下线的单品**。

## 5. 菜品管理（决定哪些单品能上头像）

两种入口，改的都是 `mcp/data/catalog.json` 的 `in_catalog`：

**A. 页面点选（推荐，直接保存）**

```bash
python3 mcp/serve.py            # 项目根目录起服务（默认 8777，可 --port 改端口）
# 打开 http://localhost:8777/mcp/manage.html
```

在页面里勾选 / 取消勾选单品，点「保存更改」即可：请求直接写回
`mcp/data/catalog.json` 的 `in_catalog`，并**自动重跑 `export_avatar.py`** 让头像端生效。
`serve.py` 是零依赖的本地服务（标准库），只在 `python -m http.server` 之外多了一个保存接口；
只读浏览用 `python -m http.server` 也行，但管理页的「保存」需要 `serve.py` 的写接口。

**B. 命令行**

```bash
python3 mcp/manage.py --list                 # 全量菜单 + 上下架 + 建议
python3 mcp/manage.py --suggest              # 按规则重置
python3 mcp/manage.py --off 9900004835       # 下架
python3 mcp/manage.py --on 1401              # 加回
python3 mcp/manage.py --reset                # 全部上架
python3 mcp/export_avatar.py                 # 生效
```

**默认策展规则**（`clean_products.suggest_keep`，页面和 CLI 同源）：

1. **套餐/组合装不上架**（69 款）—— 一托盘多件，摆头顶看不出主体，也不符合「今天那口」；
2. **非餐品不上架**（15 款）—— 玩具、联名帽、贴纸徽章、酱料包、盲盒袋，摆头顶上完全不对味；
3. **同名重复条目只留一条**（18 款）—— 不同门店的近义 SKU，优先留「有官方图 > 有价格 > code 较短」。

规则只给**建议**，`hint` 字段记录原因，最终状态以 `in_catalog` 为准。

## 6. 一键自检（改完数据/前端后跑）

```bash
.venv/bin/python tools/check.py
```

覆盖 5 组：数据源自洽 → manifest 与数据源一致 → avatar 静态资源齐 →
JS 语法（有 node 时） → Python 出图链路。全部通过退出码为 0。

## 7. 参赛提交清单（给 Owner）

- [ ] 仓库设为 **Public**
- [ ] 必须文件：`README.md` / `CONTEST_DECLARATION.md`（内容一字不改）/ `MCP_INTEGRATION.md` / `mcp-config.example.json` / `workbuddy.md`（WorkBuddy 专项奖需要）
- [ ] `.env` 与 `mcp/.env` 已被 `.gitignore` 排除，**切勿提交真实 Token**
- [ ] 在官方仓库发报名 Issue（标题自定义；正文【参赛申请】填项目名称/地址/简介；正文内别用换行、链接别用 Markdown）
- [ ] 截止：2026-10-25 23:59（北京时间）

### 7.1 上传与更新（已完成首次推送）

远端：`https://github.com/JeRryTry/mcd-avatar`（Public，`main`，317 个文件 / 约 22MB）。
`origin` 已配好，日常改完直接：

```bash
cd /Users/jerry/Desktop/code/MDC
git add -A && git commit -m "说明改了什么"
git push
```

**本机网络注意**：这台机器**直连 GitHub 不通**，必须走本地代理，且 `gh` / `git` 都不吃 macOS 系统代理：

```bash
# gh 只读环境变量，必须和命令在同一个 shell
export HTTPS_PROXY=http://127.0.0.1:6864
export HTTP_PROXY=http://127.0.0.1:6864
```

`git` 侧已给**本仓库**设了 `http.proxy=http://127.0.0.1:6864`（全局未动）。
代理端口变了就 `git config http.proxy http://127.0.0.1:<新端口>`；关掉代理时先 `git config --unset http.proxy`。
若 `push` 提示要用户名密码，用 `git -c credential.helper='!gh auth git-credential' push`，
或执行一次 `gh auth setup-git` 把凭证 helper 写进全局配置。

`.gitignore` 已排除 `.env` / `.venv/` / `output/` / `mcp/data/raw/` / `.workbuddy/` / `__pycache__`，
再提交也只会带上代码、文档和素材。

**仓库设置（已设）**：Description = `麦当劳 MCP + 零依赖 Canvas 头像引擎：给你的项目快速配上麦当劳新品头像`；
Topics = `mcp` `mcdonalds` `avatar-generator` `canvas` `vanilla-js`。
（Star 是唯一排名依据，Description 和 Topics 决定别人能不能搜到你。）

## 8. 排错速查

| 现象 | 原因 / 处理 |
| --- | --- |
| `No module named 'PIL'` | 未激活 `.venv` 或未装 Pillow → `source .venv/bin/activate && pip install -r requirements.txt` |
| 页面空白 / 食物不加载 | 用了 `file://` 直开 → 必须起 http 服务；只读浏览可用 `python3 -m http.server`，但管理页「保存」必须用 `python3 mcp/serve.py` |
| 改了菜品但页面没变 | 用 `serve.py` 图形界面保存会自动重跑导出；若手动改了 `catalog.json`，需再跑 `python3 mcp/export_avatar.py` 刷新 `avatar/manifest.json` |
| 菜单里某款不见了 | 它在 `catalog.json` 里 `in_catalog: false` → 管理页勾选保存，或 `manage.py --on <code>` 加回（缺图再跑 `fetch_images.py`）|
| 页面只有 148 款，但菜单 250 款 | 102 款被策展规则排除（套餐/非餐品/重名）；另有 23 款尚未下载本地图 |
| `manage.html` 打不开数据 | 必须在**项目根**起服务（推荐 `python3 mcp/serve.py`），访问 `/mcp/manage.html`（不是进 `mcp/` 只看到目录） |
| `update_menu.py` 报未找到 Token | 没配 `MCDONALD_TOKEN`；只想重算已有数据用 `--skip-fetch` |
| 嵌入后 `toDataURL` 报 SecurityError | 素材跨域导致 canvas 污染 → 素材与页面同源，或托管方返回 CORS 头 |

## 9. 改动守则（比排错更重要）

- 不要手改 `avatar/manifest.json` 或 `avatar/assets/foods/`——它们每次导出都会被重写。
- 不要手工编辑 `catalog.json` 的上下架字段——用 `manage.py` 或 `serve.py` 图形界面，避免格式/状态漂移。
- 不要物理删除图片或菜单条目——下架是布尔标记，删了就只能重连 MCP 采回来。
- 改动 `mc-avatar.js` 的几何参数时，同步 `tools/preview.py`（两端是同一套逻辑的两种实现）。
- `.env` 绝对不能提交；`CONTEST_DECLARATION.md` 一个字都不能改。
- 产品图片版权归麦当劳，仅做技术演示，勿商用。
