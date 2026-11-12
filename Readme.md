# TravelMate

**中文** | [English](#english)

TravelMate 是一个基于 LangChain 的旅行规划智能体。你给一句话就行，比如「从上海出发，两个人，杭州三天，预算 3000 元，喜欢自然风景」。它先把缺的条件问清楚，翻本地攻略或者联网查票价，再核对一遍地点，最后给出带预算、交通、住宿、每日路线、美食和避坑清单的行程。日期、时段衔接、费用合计这些容易出错的地方由程序核对，查不到的资料标「待核实」。

## 能做什么

- 多轮对话补齐出发地、目的地、日期、天数、人数、总预算和偏好，日期和预算口径都等你确认。
- 行程含结论、硬规则、预算三档、交通住宿、每日路线、美食、避坑、行前准备和待核实清单，天气预报写进每日标题。
- 配置小红书 Cookie 后优先检索最新旅游笔记，按主题缺口用知识库补充；未配置时使用知识库。本地 Markdown 和阿里云百炼均支持，动态规则仍独立联网核实。
- 联网搜索走 DeepSeek 官方 Search API，与模型共用密钥；没有 DeepSeek 密钥时回退到 Tavily。
- 高德查地点和驾车路线。铁路走自部署的 12306 MCP，拿真实车次和票价；飞机只走搜索，标待核实。
- 每条回答可以导出 PDF 或 Markdown。每版方案另有一页单文件 HTML 攻略，手机能看，也能直接存成 PDF。
- 语音输入只把录音转成文字填进输入框，你确认后才发出去，听错的地名还有机会改。
- 出发前 3 天按当前版本重跑一次检索，报出变动的条目和差额，原有行程照旧。
- 邀请制登录，按人按天限额。会话历史、置顶、多选删除都存在 SQLite 里，重启不丢。

## 渲染与校验

正文由程序按结构化字段渲染，模型只负责把字段填对。缺字段就跳过那一块，页面上不会出现空标题。

日期天数、时段衔接、交通预留、预算合计、城市一致、返程时限这些检查都在代码里跑，不通过就重排，最多两次。价格、时刻、地点都带来源，依据过期会标出来，PDF 里也一起保留。

整个服务是一个 FastAPI 进程，前端用原生 HTML/CSS/JS，会话和账号存在同一个 SQLite 文件里，本地跑装好 Python 就够了。

## 本地运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

编辑 `.env`，至少填一个模型密钥：

```dotenv
MODEL_API_KEY=你的 DeepSeek 密钥
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
AUTH_COOKIE_SECURE=false   # 本地 HTTP 必须改 false；公网 HTTPS 设回 true
```

密钥在 https://platform.deepseek.com/ 的 API Keys 里建，别提交到 Git。

### 命令行

```powershell
uv run travelmate --session demo
```

### 网页

```powershell
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。第一次用要先拿个邀请码，再去 `/login` 注册：

```powershell
uv run python -m travelmate.accounts invite
```

可以试这句：`从上海出发，两个人，杭州三天，预算3000元，喜欢自然风景，帮我规划`。用同一个 `--session` 或同一个浏览器会话可以接着问。

### 可选能力

| 变量 | 作用 |
| --- | --- |
| `AMAP_API_KEY` | 高德 Web 服务 Key，启用地点与驾车核对 |
| `TAVILY_API_KEY` | 没有 DeepSeek 密钥时的搜索兜底 |
| `KNOWLEDGE_PROVIDER` | `local` 本地字符匹配 / `aliyun` 百炼知识库 |
| `XHS_COOKIE` / `XHS_ENABLED` | 小红书最新攻略，配置 Cookie 自动启用；需安装 `xhs` 可选依赖，见接入说明 |
| `RAIL_MCP_URL` | 12306 MCP 地址，查真实车次；不配则退回搜索 |
| `ASR_PROVIDER` / `ASR_API_KEY` | 语音转文字，支持 OpenAI 兼容接口或 faster-whisper 本地跑 |
| `COST_MODE` | `research` 联网查票价与人均 / `plan` 只排流程不查价 |
| `REVIEW_MODE` | `program` 只跑程序检查 / `full` 加一次模型语义审查 |
| `PLAN_BUDGET_SECONDS` | 规划软时限（默认 55 秒），超时跳过模型复核与剩余重排，先交付方案并提示待核实 |

改完 `.env` 要重启服务，uvicorn 不会热加载。

## 测试

```powershell
uv run pytest -q
```

离线测试用确定性的测试模型跑真实工具循环，不调用付费接口。只想看第一个失败就加 `-x --tb=short`。

## 更多文档

| 文档 | 内容 |
| --- | --- |
| [设计说明](docs/design.md) | 整体架构与模块划分 |
| [邀请与账号](docs/invitation-access.md) | 登录、额度与部署 |
| [阿里云知识库](docs/aliyun-knowledge.md) | 百炼知识库接入与标签过滤 |
| [小红书接入](docs/xiaohongshu.md) | 本地演示配置、Cookie、检索自检与降级说明 |
| [12306 MCP](docs/12306-mcp-setup.md) | 车次查询的配置与排错 |

---

<a id="english"></a>

# TravelMate (English)

**English** | [中文](#travelmate)

TravelMate is a travel-planning agent built on LangChain. One sentence gets it going, for example "Two of us, from Shanghai to Hangzhou for three days, 3,000 CNY budget, we like nature." It asks for whatever is missing, reads local guides or looks up fares online, checks the places, and returns an itinerary with a budget, transport, accommodation, a day-by-day plan, local food and a list of pitfalls. The program checks the parts that usually go wrong: date range, transfer times, cost totals. Anything it cannot confirm is marked unverified.

## What it does

- Multi-turn intake fills in origin, destination, dates, trip length, party size, total budget and preferences. Dates and the budget basis always come from you.
- The itinerary covers a verdict, hard rules, three budget tiers, transport and accommodation, a daily route, local food, pitfalls, pre-trip preparation and a to-verify list. The forecast sits in each day header.
- With `XHS_COOKIE` configured, recent Xiaohongshu notes come first and the knowledge base fills topic gaps. Without it, local Markdown or Alibaba Cloud Bailian is used directly. Dynamic facts are checked independently.
- Web search uses the official DeepSeek Search API with the same key as the model, and falls back to Tavily when there is no DeepSeek key.
- Amap handles place lookup and driving routes. Train data comes from a self-hosted 12306 MCP server, so you get real train numbers and fares. Flights go through web search only and stay marked unverified.
- Every answer can be exported to PDF or Markdown, and each saved version has a standalone single-file HTML guide that works on a phone and prints to PDF.
- Voice input only transcribes audio into the input box. Nothing is sent until you press send, so a misheard place name can still be fixed.
- Three days before departure it re-runs the research against the saved version and reports which items changed and by how much. The saved itinerary stays as it is.
- Login is by invitation, with per-user daily quotas. History, pins and multi-select deletion live in SQLite and survive a restart.

## Rendering and checks

The program renders the answer from structured fields, and the model only fills those fields in. A missing field drops that block, so the page never shows an empty heading.

The code also handles validation: date range, day count, transfer buffers, budget totals, single-city consistency and the return-time limit. A failed check triggers a rewrite, at most twice. Prices, times and places each carry their source, expired evidence is flagged, and the PDF keeps all of it.

The app runs as one FastAPI process with a plain HTML/CSS/JS frontend, and sessions and accounts share a single SQLite file. Python is the only thing you need to install.

## Run locally

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

Edit `.env` and set at least one model key:

```dotenv
MODEL_API_KEY=your-deepseek-key
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
AUTH_COOKIE_SECURE=false   # required for local HTTP; set back to true behind HTTPS
```

Create the key under API Keys at https://platform.deepseek.com/, and keep it out of Git.

### Command line

```powershell
uv run travelmate --session demo
```

### Web UI

```powershell
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. First-time use needs an invite code, generated locally and then entered at `/login`:

```powershell
uv run python -m travelmate.accounts invite
```

Try this: `Two of us from Shanghai, three days in Hangzhou, 3,000 CNY, we like nature.` Reusing the same `--session` or the same browser session continues the conversation.

### Optional features

| Variable | Purpose |
| --- | --- |
| `AMAP_API_KEY` | Amap web-service key; enables place lookup and driving-route checks |
| `TAVILY_API_KEY` | Search fallback when no DeepSeek key is set |
| `KNOWLEDGE_PROVIDER` | `local` for local text matching, `aliyun` for the Bailian knowledge base |
| `RAIL_MCP_URL` | 12306 MCP endpoint for real train data; unset falls back to web search |
| `ASR_PROVIDER` / `ASR_API_KEY` | Speech to text through any OpenAI-compatible endpoint, or faster-whisper locally |
| `COST_MODE` | `research` looks up fares and per-head prices, `plan` skips pricing |
| `REVIEW_MODE` | `program` runs the code checks only, `full` adds one model-based review |
| `PLAN_BUDGET_SECONDS` | Soft planning budget in seconds (default 55); on timeout the model review and remaining revisions are skipped, and the plan ships with a verify-before-you-go notice |

Restart the server after editing `.env`; uvicorn does not reload it.

## Tests

```powershell
uv run pytest -q
```

The offline suite drives the real tool loop with a deterministic test model and never calls a paid API. Add `-x --tb=short` to stop at the first failure.

## Further reading

| Document | Contents |
| --- | --- |
| [Design notes](docs/design.md) | Architecture and modules (Chinese) |
| [Invitations and accounts](docs/invitation-access.md) | Login, quotas and deployment (Chinese) |
| [Alibaba Cloud knowledge base](docs/aliyun-knowledge.md) | Bailian setup and tag filtering (Chinese) |
| [12306 MCP](docs/12306-mcp-setup.md) | Train lookup setup and troubleshooting (Chinese) |
