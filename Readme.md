# TravelMate

**中文** | [English](#english)

TravelMate 是基于 LangChain / LangGraph 的旅行规划智能体，使用 FastAPI、原生 HTML/CSS/JS 和 SQLite。通过多轮对话收集旅行条件，结合攻略、联网搜索和地点查询，生成可查看、继续修改和导出的旅行方案。

例如：**“从上海去杭州，2 人玩 3 天，全员总预算 3000 元人民币，包含住宿、餐饮、门票和市内交通，不含往返高铁，喜欢自然风景和当地美食，日期暂定。”**

日期未定也可以规划，页面按“第几天”展示；日期确定后再查询对应天气和票务信息。费用区分估算、查询结果与未知金额，不把未查到价格当作免费。

## 目前已实现

### 七个攻略板块

| 板块 | 当前功能 |
| --- | --- |
| 行程概览 | 旅行信息、景点轮播、按天进入日程、方案版本与来源说明；轮播每 4 秒自动切换，左右按钮、圆点和键盘手动切换后重新计时 |
| 预算明细 | 分类费用、全员与人均金额、预算余量；支持修改金额、勾选计入、分类筛选、排序和恢复方案金额 |
| 每日行程 | 按天查看景点卡片、交通预留、费用和提醒；查看天气、地点地图及已生成的普通雨天备选路线 |
| 住宿推荐 | 按片区比较适合人群、交通、区域取舍与参考预算，结合行程动线展示，并提示取消条款、房型和到站交通 |
| 当地美食 | 按天与餐次查看菜品、顺路用餐建议和点单提醒；未指定日期的推荐单独标为灵活安排 |
| 避坑指南 | 按预订前、出发前、游玩中、返程前查看通用提醒，并保留该方案已有的专项避坑内容 |
| 行程准备 | 按类别管理准备事项，支持勾选、新增、修改、删除、状态筛选及进度统计；在线按账号、会话和方案版本保存 |

页面采用奶油白、墨绿与橙色配色，适配桌面和手机。内置城市、风景及 AI 生成的住宿、美食参考素材，用于缺少照片时的示意展示；运行时不会自动生成真实景点或酒店照片。

### 规划、资料与交付

- **多轮需求收集**：确认目的地、天数、人数、预算口径、币种及包含范围，结合偏好、忌口、行动限制、已订安排和返程时限规划。出发地和日期可暂缺。
- **显式规划流程**：收集条件 → 检索资料 → 组织片区与核对地点 → 生成行程 → 程序校验 → 保存版本；可选启用模型语义复核。失败修订保留上一版可用方案。
- **多来源检索**：配置小红书 Cookie 后优先检索旅游笔记，知识库补充主题缺口；支持本地 Markdown 和阿里云百炼。动态价格、预约与开放规则另行查询。
- **搜索与交通**：支持 DeepSeek Search / Tavily、高德地点与驾车路线工具，以及自部署 12306 MCP。未查到有效结果时保留待核实状态。
- **版本与导出**：每版方案保存攻略快照，可导出 PDF、Markdown 和内嵌素材的单文件 HTML；聊天回答也支持 PDF / Markdown 导出。
- **语音输入**：将录音转成可编辑文字，用户确认发送后才进入规划流程。
- **行前复核**：网页服务运行且定时检查启用时，在出发前配置的时间窗口内重新查询部分资料并报告变化，不自动改写原行程。
- **账号与历史**：邀请码注册、登录、每日额度、会话历史、置顶和多选删除，数据持久化到 SQLite。
- **我的攻略**：独立攻略库自动保存生成结果，支持搜索、收藏、重命名、历史版本、下载和继续调整。删除聊天后攻略仍保留；旧方案启动时自动补入，详见[我的攻略说明](docs/my-guides.md)。

## 使用边界

- **预算试算仅影响当前页面**，不会修改保存的方案或同步改写导出金额。综合费用只有存在明确分项与金额依据时才拆分。
- **雨天切换用于查看备选路线**，预算、地图和 PDF / Markdown 导出仍对应原定行程；需要保存调整时，通过对话生成新版本。
- **图片是参考素材**，不代表对应目的地、酒店或菜品的真实照片。住宿建议不提供实时可订房态，也没有自动预订功能。
- **地点地图为坐标连线示意**。默认规划尚未完整接入关键路段的实时路线核验；地点存在性不能证明步行、公交或接驳耗时准确。
- **天气依赖日期与有效查询结果**。无日期时不查询天气；无结果或超出预报范围时不编造预报。第三方铁路查询结果不保证出票或余票。
- **在线与离线清单分别保存**。在线清单支持同账号跨设备读取；离线 HTML 的修改只保存在当前浏览器，不自动回传账号。清理浏览器数据会丢失离线修改。
- 小红书接入面向个人低频演示，失败时降级补查知识库。真实外部接口质量、成功率和调用成本仍需独立验收。

## 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。以下命令使用 PowerShell，在项目根目录执行。

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

已有 `.env` 时保留原配置。至少设置 `MODEL_API_KEY`，其余默认项可参考 `.env.example`：

```dotenv
MODEL_API_KEY=你的模型密钥
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
AUTH_COOKIE_SECURE=false
```

默认接入 DeepSeek，也可配置兼容接口的地址与模型名。模型及外部 API 的费用由所用服务决定。`.env`、账号数据库和私人会话不提交到 Git；本地 HTTP 使用 `AUTH_COOKIE_SECURE=false`，公网 HTTPS 部署设回 `true`。

### 启动网页

```powershell
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

首次使用时生成邀请码：

```powershell
uv run python -m travelmate.accounts invite
```

打开 [本地网页](http://127.0.0.1:8000)，在 [登录页](http://127.0.0.1:8000/login) 使用邀请码注册，然后创建会话开始规划。后续可在同一会话里继续修改需求并查看历史版本。

### 命令行

```powershell
uv run travelmate --session demo
```

复用相同 `--session` 继续历史对话，输入 `/exit` 退出。

### 可选配置

| 变量 | 用途 |
| --- | --- |
| `SEARCH_PROVIDER` / `TAVILY_API_KEY` | `auto` 默认在配置 DeepSeek 官方网关与密钥时使用其搜索，否则选择 Tavily；可指定 `deepseek` 或 `tavily` |
| `AMAP_API_KEY` | 高德 Web 服务 Key，用于地点查询、天气及驾车路线工具 |
| `KNOWLEDGE_PROVIDER` / `KNOWLEDGE_DIR` | `local` 使用本地攻略，`aliyun` 使用百炼知识库；默认本地目录为 `knowledge` |
| `XHS_COOKIE` / `XHS_ENABLED` | 小红书笔记检索；Cookie 仅保存在服务端，接入方法见文档 |
| `RAIL_MCP_URL` | 自部署 12306 MCP 地址；未配置时尝试搜索参考交通信息 |
| `ASR_PROVIDER` / `ASR_API_KEY` / `ASR_BASE_URL` / `ASR_MODEL` | 语音转文字；支持兼容接口或需另行安装的本地 `faster-whisper` |
| `COST_MODE` | `research` 调研费用；`plan` 只规划流程，金额待核实 |
| `REVIEW_MODE` | 默认 `program`，只做程序检查；`full` 增加模型语义复核 |
| `PLAN_BUDGET_SECONDS` | 规划软时限，默认 55 秒；影响后续复核与重排，不保证请求在该秒数内返回 |
| `WATCH_SCHEDULER` / `WATCH_LEAD_DAYS` / `WATCH_INTERVAL_HOURS` | 行前复核开关、出发前窗口和同版复核间隔；默认启用、3 天、24 小时 |
| `DATABASE_PATH` | SQLite 文件位置，默认 `data/checkpoints.sqlite`；部署时使用持久存储并备份 |

百炼、小红书、铁路客户端分别需要 `aliyun`、`xhs`、`rail` 可选依赖，按需安装。例如同时启用三项：

```powershell
uv sync --extra dev --extra aliyun --extra xhs --extra rail
uv run --extra aliyun --extra xhs --extra rail uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

后续 `uv run` 也应保留所需的可选依赖参数。修改 `.env` 后重启服务。完整配置和说明见 [.env.example](.env.example)。

## 开发与验证

```powershell
# Python 回归测试
uv run --extra dev pytest -q

# 前端脚本测试，需要 Node.js
node --test tests/markdown.test.mjs tests/quick-fill.test.mjs tests/auth.test.mjs tests/voice.test.mjs

# 格式与空白检查
git diff --check
```

部分 Python 用例也通过 Node.js 验证页面交互。测试使用模拟模型与工具结果，不替代真实接口联调。轮播回归包含临近自动切换时手动翻页、完整 4 秒重新计时，以及离开视口或后台时暂停。

## 更多文档

| 文档 | 内容 |
| --- | --- |
| [设计说明](docs/design.md) | 架构与模块划分 |
| [规划工作流](docs/planning-workflow.md) | 规划、证据、版本与失败保护的演进记录 |
| [邀请与账号](docs/invitation-access.md) | 登录、额度与部署 |
| [行前准备](docs/preparation.md) | 清单保存、版本隔离、冲突处理和离线限制 |
| [住宿参考图](docs/lodging-visuals.md) | 内置素材、生成提示词与旧方案兼容 |
| [避坑页面](docs/pitfalls-ui.md) | 阶段筛选、通用提醒与专项内容 |
| [小红书接入](docs/xiaohongshu.md) | Cookie、检索自检与降级 |
| [阿里云知识库](docs/aliyun-knowledge.md) | 百炼接入与标签过滤 |
| [12306 MCP](docs/12306-mcp-setup.md) | 铁路查询配置与排错 |
| [天气与工具](docs/weather-and-tool-options.md) | 天气能力及工具接入说明 |

工作流及阶段总结文档包含历史记录；当前页面行为以本 README 和实现为准。

---

<a id="english"></a>

# TravelMate (English)

**English** | [中文](#travelmate)

TravelMate is a travel-planning agent built with LangChain / LangGraph, FastAPI, plain HTML/CSS/JS and SQLite. It collects trip requirements through conversation, researches guides and places, checks structured itineraries, and saves versioned travel guides.

Example: **“Two people travelling from Shanghai to Hangzhou for three days. Total budget: CNY 3,000, including accommodation, meals, tickets and local transport, excluding return train fares. We like nature and local food; dates are undecided.”** Dates and origin are optional; an undated trip uses relative days.

## Current features

| Guide section | Implemented behavior |
| --- | --- |
| Overview | Trip facts, scenic carousel, daily links and saved-version details; manual navigation restarts the full 4-second autoplay delay |
| Budget | Category totals, per-person costs and remaining budget; editable amounts, inclusion toggles, filters, sorting and reset |
| Daily itinerary | Daily activity cards, transport estimates, weather, schematic maps and saved rain alternatives |
| Accommodation | Area comparisons covering suitability, transport, trade-offs, reference budgets and booking checks |
| Local food | Recommendations by day and meal, route context and ordering tips; undated suggestions are marked flexible |
| Pitfalls | Reminders by travel stage, with the saved itinerary's specific advice retained |
| Preparation | Categorized editable checklists, filters and progress; online changes saved per account, session and plan version |

The responsive UI includes bundled city, scenery and AI-generated reference assets. Other capabilities include local Markdown or Bailian knowledge retrieval, optional Xiaohongshu research, DeepSeek / Tavily search, Amap tools, a self-hosted 12306 MCP integration, editable voice transcription, invitation-based accounts and pre-departure checks while the web service is running.

Each saved guide supports PDF, Markdown and standalone HTML exports. Failed revisions keep the previous usable plan. Programmatic validation is enabled by default; model-based review is optional.

## Limits

Budget edits are page-only calculations. Switching to a rain alternative previews that route; budgets, maps and PDF / Markdown exports still refer to the original itinerary. Request a revised plan in chat to save changes.

Reference images are illustrative, and images are not generated automatically at runtime. Accommodation suggestions do not provide live availability or automatic booking. Map lines are schematic; place lookup does not verify walking or transit times. Weather requires a date and valid query results, and third-party train results do not guarantee availability.

Online checklists can be read across devices under the same account. Offline HTML checklists use browser storage and do not sync back to the account. External service reliability, planning quality and costs need separate real-world validation.

## Run locally

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/). From the project root in PowerShell:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

Keep an existing `.env` rather than replacing it. Set `MODEL_API_KEY`, `MODEL_NAME` and `MODEL_BASE_URL`; defaults target DeepSeek. Set `AUTH_COOKIE_SECURE=false` for local HTTP and `true` for public HTTPS. Keep credentials and private data out of Git.

```powershell
uv run python -m travelmate.accounts invite
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

Open the [local login page](http://127.0.0.1:8000/login), register with the invite code and start a conversation. For CLI usage, run `uv run travelmate --session demo`; reuse the session ID to continue, and type `/exit` to quit.

Optional integrations use the `aliyun`, `xhs` and `rail` extras. Include the required extras in both `uv sync` and subsequent `uv run` commands. Local speech recognition requires a separate `faster-whisper` installation. See [.env.example](.env.example) and the configuration table above for settings. Restart the service after changing configuration, and persist and back up the SQLite database.

## Development

Run `uv run --extra dev pytest -q` for Python regressions. Node.js is needed for JavaScript tests and some Python interaction checks; the frontend test command is listed above. Mocked tests do not verify live external services.

The documentation table above links to architecture, workflow, account, checklist, image asset, knowledge-base, weather and railway setup notes in Chinese. Some documents record earlier implementation stages.
