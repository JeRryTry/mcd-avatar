# 项目笔记 · 今天什麦人

## 这是个啥
基于麦当劳中国 MCP 的真实菜单数据,把「简笔画人物 + 麦麦帽 + 今天想吃的那一口」合成一张有梗的麦当劳头像.可以网页里点选下载,也能一行代码嵌到自己项目里程序化生成.

## 现在做到哪了
- 架构就两块:**`mcp/`** 是数据源(MCP 采集 + 管菜品),**`avatar/`** 是纯静态头像生成器.数据单向从 mcp 流向 avatar.
- 数据层闭环:从麦当劳 MCP 采集 → 清洗成 **250 款全量菜单**(本地图 227 张) → 策展 **148 款上架单品**(都带官方原图).
- 数据源只有一份:`mcp/data/catalog.json`.全量菜单、上下架状态、本地图路径都在里面,不再有单独的清单 txt.
- 头像应用能跑:7 个角色 × 148 食物,两种模式(只戴帽 / 帽+食物)、搜索筛选、聊天框文案、Canvas 实时合成下载.
- 合成逻辑抽成了独立引擎 `avatar/mc-avatar.js`,页面只做界面;别人可以三行代码嵌到自己项目里生成头像(带 seed 可复现、可返回 dataURL/Blob).
- 菜单是「可更新」的,不是一次性爬虫:`mcp/update_menu.py` 一条命令重新采样 MCP,跑完报告新增/下线单品.
- 菜品管理两套等价入口:`mcp/manage.py`(命令行)和 `mcp/manage.html`(页面点选,**点「保存更改」直接写回 catalog.json 并自动导出**,需 `mcp/serve.py` 起服务);**下架不删数据**,状态只是 `in_catalog` 一个布尔值,而且重跑清洗会继承.
- 环境:项目 `.venv` + Pillow 就绪,新增 `requirements.txt`.
- 参赛必须的文件齐了(README、参赛声明、MCP 集成说明、脱敏配置示例、`workbuddy.md`).

三种玩法都验证过能用:
```bash
# 头像应用(不需要 Python)
cd avatar && python3 -m http.server 8777           # localhost:8777
# 菜品管理页(在项目根起服务,保存需 serve.py 的写接口)
python3 mcp/serve.py                               # localhost:8777/mcp/manage.html
# 更新菜单(MCP,需要 Token)
python3 mcp/update_menu.py                         # 或 --skip-fetch 不联网重算
# 本地出图 / 自检
.venv/bin/python tools/preview.py --seed 20261020
.venv/bin/python tools/check.py
```

## 接下来要搞的(都是为了多捞 Star)
排名只看 GitHub Star,所以重点是让人**愿意点开、用得爽、好意思转发**.目前缺的就是这口气:

- [ ] README 顶部放个真实演示 GIF _ 别人扫一眼就知道能干啥,这是给人点 Star 的理由.
- [ ] 网页版部署到 GitHub Pages _ 现在还得本地起服务,门槛太高;做成一条链接打开就能玩,传播才起得来.
- [ ] 生成完加个「分享」引导 _ 比如一键带文案发圈,或者把头像和一句「今天你什麦?」打包,让人有得晒.
- [ ] 首屏再打磨一下 _ 落地页/预览区视觉还不够抓人,配色和排版往麦当劳红黄那味儿靠.
- [ ] 报名别忘了 _ 截止 10-25 23:59,去官方活动仓库发 Issue(标题自定义,正文填项目名称/地址/简介),仓库设成 Public.

## 几个底线
- Token 走环境变量 `.env` 或 `mcp/.env`,绝不提交真实密钥.
- 参赛声明文件内容一个字都不能改.
- 图片版权归麦当劳,只做技术演示,别商用.

## 2026-10-21 更新
- 停掉残留的 8777 服务.
- 修数据链路:补回 `clean_products.py`(此前缺失导致 `merge_full.py` 直接崩),已用现有 145 快照逐条校验,仅保留 2 处分类修正(高达吉士双牛堡→汉堡、锦州蜜烤肉骨鸡架→炸鸡)与 2 处规格选择(薯条取中薯、新地取朱古力).
- 固化上架清单,解决"merge 一跑就打回 250"的问题.
- 新建 `.venv` + Pillow,三端(Web/服务/CLI)冒烟测试全部通过.
- 文档整理:新增 `workbuddy.md`(专项奖)、`ONBOARDING.md`(维护/数据手册),README 补环境准备与数据流水线;本文件只记进度.

## 2026-10-21 更新(二)
- 定了架构:Python 只做数据层(MCP 采集/清洗/导出),合成只有一套 JS 引擎,不再三份实现各写一遍.
- 抽 `mc-avatar.js`:draw / toDataURL / toBlob / list,支持 mode/person/code/bubble/seed/size,`app.js` 瘦成纯界面层.
- 「更新菜单」升级成正式功能:一条命令串 fetch → merge → 下图 → export,并打印本次新增/下线单品.
- 上架/下架改成非破坏性:打 `in_catalog` 标,不再删数据删图.
- 默认策展规则:套餐/组合装 69 款、非餐品(玩具/酱料包/袋盒)15 款不上架,同名重复只留 18 款,最终上架 148 款.
- 补上 `fetch_images.py`:原来 `merge_full.py` 只产出 `image_url`,图没落地,所以「更新菜单」拿到新品也合成不了;本轮补了 82 张.
- 用无头 Chrome 实跑验证:首页出图正常、管理页可用、`McAvatar` 各 API 路径通过(同 seed 结果一致).

## 2026-10-21 更新(三)· 目录重构
之前 `scripts/` + `web/public/` 的摆法,让人看不出 MCP 在哪被消费:数据脚本埋在 scripts 里,菜单管理页又混在前端目录,
还有一份游离的 `keep_codes.txt` 当配置.这次按「职责」重新切:

```
mcp/      数据源:拉最新菜单 + 管菜品(Python)
avatar/   纯静态头像生成器,只读 mcp 导出的清单
tools/    本地验证(出图 + 自检),不是产品运行时
```

- 数据源合并成一份 `mcp/data/catalog.json`:全量菜单 + `in_catalog`(上下架) + `local_image`(本地图) + `hint`(建议原因).
  删掉了 `products_full.json` 和 `keep_codes.txt` _ 状态属于数据,不该另立一份文本.
- `merge_full.py` 重写时会按 code **继承旧的上架状态**,所以「更新菜单」不会把手动调过的策展冲掉(实测:下架巨无霸→重跑清洗→仍是下架).
- `manage.py` 直接改 `catalog.json` 的 `in_catalog`;`manage.html` + `serve.py` 让页面点「保存更改」直接写回 `catalog.json` 并自动重跑导出(不再需要复制命令去终端跑).
- `export_avatar.py` 只导出「上架 + 有图」的单品,并且**清空重建** `avatar/assets/foods/`,不会留下去掉的下架图.
- 人物/帽子从「每次导出都复制一遍」改成 `avatar/assets/` 里的固定素材,导出只补算头顶锚点,少一份重复.
- 删掉 `avatar_server.py`(纯静态已经足够,不需要本地 Python 服务)和 `remove_foods.py`(会物理删官方图,和可逆原则冲突).
- `selftest.py` 改成 `tools/check.py`,检查项跟着新结构走:数据源自洽 → manifest 与数据源一致 → 静态资源齐 → JS 语法 → 出图.
- 实测:`update_menu.py --skip-fetch` 全链路跑通;自检全过;无头 Chrome 两页正常(avatar 148 款 / 管理页 250 款).
