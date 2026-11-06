# TravelMate

Python + LangChain 旅游智能体。分步提交：设计 → 核心与工具 → API 和测试。

本阶段：持久对话、知识检索、联网搜索、地点与驾车路线、结构化行程校验、按回答一键导出 PDF、CLI、SSE 和网页界面。
后续协商：天气、公交/步行路线及 MCP。

详见 [设计说明](docs/design.md)。

新增可选阿里云百炼托管向量知识库，继续使用 DeepSeek 生成回答。配置和原理见 [云知识库接入说明](docs/aliyun-knowledge.md)。默认仍使用本地字符匹配；切换需安装 `aliyun` 可选依赖并设置 `KNOWLEDGE_PROVIDER=aliyun`。

## 本地运行（Python 3.11+）

```powershell
uv sync --extra dev
Copy-Item .env.example .env
# 编辑 .env，填写 MODEL_API_KEY；需要联网搜索时填写 TAVILY_API_KEY
uv run travelmate --session demo
```

默认使用 DeepSeek 官方兼容接口的 deepseek-flash，并显式关闭思考模式以适配当前通用客户端的工具循环。模型必须支持 tool calling。deepseek-flash 就是 DeepSeek-V4.1-Flash 的官方模型名；把 `MODEL_NAME` 写成 `deepseek-v4.1-flash`、`deepseek-v4-flash` 或 `deepseek-chat` 会自动映射到它，避免换了名字就调不通。可以通过 MODEL_NAME / MODEL_BASE_URL / MODEL_API_KEY 切换兼容服务；无密钥不会伪造模型回复。费用以服务商账单为准。

## 预设人格（每次新会话自动加载）

`travelmate/prompts/advisor-v1.txt` 是「行策」预设人格，由 `open_agent` 在每个新会话拼进 system prompt，不需要用户每次复述。它规定了两件事：**信息怎么查**（反幻觉、置信度标注 🔎/⏳、多平台情报源）和**正文长什么样**（先说结论+硬规则 → 预算三档 → 交通 → 住宿 → 每日 → 美食 → 费用 → 避坑 → 应急 → 行前 + 待核实清单，语气对齐 `E:\test\北京到上海3天2晚-美食路线.md` 这份样稿）。

正文仍由程序按结构化字段渲染，模型不直接写 Markdown：`key_call`（关键判断）、`hard_rules`（≤3 条硬规则）、`budget_tiers`（三档）、`pitfalls`（≥5 条避坑）、`verify_items`（待核实渠道）这几个字段分别对应上面几个新模块，缺字段就不渲染该模块，不会退化成空标题。改人格只改这一个文件，`PROMPT_VERSION` 在 `travelmate/agent.py` 里同步。

在 https://platform.deepseek.com/ 登录开放平台，在 API Keys 中创建密钥，保存至本地 `.env` 的 `MODEL_API_KEY`，并确认账户有可用 API 余额。不要将密钥发到聊天或提交 Git。模型名称及费用以 https://api-docs.deepseek.com/ 为准。

```dotenv
MODEL_API_KEY=在本地填入你的DeepSeek密钥
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
```

本地运行的是 Python 程序，模型通过网络调用 DeepSeek 云端。网页检索默认走 **DeepSeek 官方 Search API**（`POST https://api.deepseek.com/v1/tools/search`，与模型共用 `MODEL_API_KEY`，返回标题、链接、摘要和正文），不需要额外申请搜索密钥；请求体限制查询 128 字符，超长会被截断。`SEARCH_PROVIDER=auto` 表示有 DeepSeek 密钥就用官方搜索，否则回退 Tavily（`TAVILY_API_KEY`）；设成 `deepseek` 或 `tavily` 可强制指定。Tavily 支持通过 [Tavily MCP](https://docs.tavily.com/documentation/mcp) 联网：执行 `uv sync --extra rail` 安装 MCP 客户端，在 `.env` 设置 `TAVILY_SEARCH_TRANSPORT=mcp` 后重启。MCP 查询失败时继续使用其他可用资料，并保留查询失败状态。系统环境变量优先于 `.env`。

示例：`从上海出发，两个人，杭州三天，预算3000元，喜欢自然风景，帮我规划`。再次使用 `--session demo` 可继续对话。知识文件放在 `knowledge/*.md`，每次检索读取最新文件；示例资料并非实时旅游数据库。

```powershell
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 使用聊天页面。前端为原生 HTML/CSS/JavaScript，由 FastAPI 同时提供，无需 Node.js、npm 或额外运行依赖。

网页现已开启邀请制登录，账号、会话归属和每日额度复用现有 SQLite。首次使用在 `.env` 设置 `AUTH_COOKIE_SECURE=false`（仅本地 HTTP），执行 `uv run python -m travelmate.accounts invite` 生成邀请码，再在 `/login` 注册。服务器 HTTPS 必须设回 `true`。默认每人每天 20 次、全站 100 次生成，按北京时间刷新。[邀请、账号管理与部署说明](docs/invitation-access.md)。

- SSE 在需求整理、资料检索、地点核对、生成和审查开始时立即报告处理进度，地点查询显示完成数量，修订显示轮次；不展示模型内部推理。最终回答完成校验后，发送非空正文分段，网页逐步渲染 Markdown。
- 当前会话 ID 保存在浏览器 localStorage，刷新后从 SQLite 恢复消息；历史列表展示最近 50 个已有消息的会话，可切换或新建。浏览器禁用存储时仍可从历史列表选择。切换会话会清空未发送的输入。
- 回复支持简单 Markdown 子集：标题、粗体、行内代码、代码块、单层列表、表格和 HTTP(S) 链接；不解析原始 HTML、图片或任意脚本。不支持完整 CommonMark 和复杂嵌套。
- 失败保留输入并提示未完成，不展示未排版的部分回复；刷新后以服务端已保存的消息为准。流式请求不自动重试，以免重复提交；手动重新发送可能在历史中留下重复问题。
- 回答后需要补充旅行条件时，底部显示“点击选择”入口，点击后才打开独立的分步窗口，不挤占回答区域；优先点选目的地、天数、人数、预算、币种和费用范围，也可展开自定义输入。支持上一步修改与稍后再选，关闭窗口后保留本次选择，最后统一确认后继续规划。既有条件不重复询问，提交失败时保留本次选择。刷新或切换会话后定位到最新消息，后台恢复时保留用户向上阅读的位置。
- Enter 发送，Ctrl/Command + Enter 换行；中文输入法选字时不会误发送。暖白与青绿旅行主题、左侧历史记录、用户消息靠右与助手回复靠左；首页提供旅行灵感卡，只填写可编辑草稿，开始聊天后收起配图，保留底部输入框。手机端可展开对话记录，支持手机布局和可见焦点样式。登录页与首页共用本地 AI 生成配图和品牌样式。[视觉优化说明与验证](docs/visual-refresh.md)。设计参考 UI UX Pro Max 的通用可读性、可访问性建议：https://github.com/nextlevelbuilder/ui-ux-pro-max-skill 。

每条对话右侧的“…”菜单提供带图标的删除、置顶/取消置顶、多选操作；分享暂未开放。普通模式隐藏勾选框，点击多选后可勾选对话，并在侧栏底部删除所选；支持取消多选，批量操作暂不支持置顶。置顶保存在 SQLite 中，重启后保留，置顶对话优先显示。删除需确认，并清除对应聊天、行程和回答导出记录。

执行记录隐藏中间查询失败、合并重复提示，以无编号列表展示，回答完成后自动折叠；展开时随聊天页面滚动。用户消息靠右显示且省略姓名。参考来源保留知识库名称和公开链接。

会话管理接口：`DELETE /sessions/{session_id}` 删除单条；`POST /sessions/delete` 接收 `{"session_ids":["demo"]}` 批量删除；`POST /sessions/pin` 接收 `{"session_ids":["demo"],"pinned":true}` 置顶，`false` 取消置顶。`GET /sessions` 返回 `pinned` 并优先显示置顶对话。原分组入口和接口已移除。

接口：`POST /chat/stream` 返回 SSE `status`、`token`、`done` 或 `error` 事件；`done` 包含最终回复，只有收到它才表示完整结束。`GET /sessions` 列出本地会话，`GET /sessions/{session_id}` 读取用户及最终助手消息，不返回工具内部消息。原 `POST /chat` 保留。

所有业务接口要求登录，并校验会话归属；流式请求仍串行执行，首版面向小范围邀请体验，使用单进程部署。网页断开连接不保证立即中止已发出的模型/工具请求。部署反向代理时需关闭 SSE 缓冲，并配置合适的读取超时。

`/docs` 默认关闭。程序化调用先登录并保存 Cookie，写操作携带 `X-TravelMate-Request: 1`，例如向 POST /chat 发送：

```json
{"session_id":"demo","message":"两个人去杭州三天，帮我规划"}
```

GET /health 为公开的进程健康检查，不验证外部模型是否可用。公网通过 HTTPS 反向代理访问，应用仅监听内网或回环地址；会话以明文存入 data/checkpoints.sqlite，该文件也保存账号、邀请码摘要和用量。删除此数据库及关联的 WAL/SHM 文件前应先停止服务，并确认不再需要历史和账号记录。

## 验证

```powershell
uv run pytest -q
```

离线测试会隔离本机 `.env` 和真实服务密钥，默认使用本地知识库。不安装阿里云 SDK 时，3 项 SDK 相关测试会显示 `skipped`，这是正常跳过。若实际运行配置为 `KNOWLEDGE_PROVIDER=aliyun`，或要运行完整云知识库模拟测试，请执行：

```powershell
uv sync --extra dev --extra aliyun
uv run --extra dev --extra aliyun pytest -q
```

测试报错时先执行 `uv run pytest -x -q --tb=short`，只显示首个失败，优先排查最后一条异常；测试通过后再进行真实服务联调。

可选前端渲染回归检查（开发验证才需要 Node）：`node --test tests/markdown.test.mjs`。已用离线测试模型完成网页逐步显示、表格与链接、刷新恢复、历史切换、错误保留输入和窄屏检查；不代表真实模型和云知识库联调。

离线测试使用确定性的测试模型驱动真实 create_agent 工具循环，不调用付费接口。覆盖预算、知识检索、未配置搜索、SQLite 重启与隔离、API 校验和上游错误脱敏。尚未验证真实模型与 Tavily 的账号权限、网络和生成质量。

## 后续开发建议

先用真实密钥验证一条完整旅游需求，再按实际需要扩充天气与交通方式。

## 单独验证高德（PowerShell）

在项目根目录直接运行内置检查命令，无需复制多行 Python：

```powershell
cd E:\travelmate-agent\travelmate-agent
uv run python -m travelmate.check_amap
```

脚本明确读取当前目录的 `.env`，兼容 UTF-8 BOM，不使用 `find_dotenv()` 自动查找，避免标准输入运行时的 `AssertionError`。`AMAP_API_KEY` 必须填写高德控制台生成的真实 Web 服务 Key，不能原样填写“这里替换为你刚申请的高德Key”。系统环境变量仍优先于 `.env`。

命令会真实查询两个地点和一条驾车路线；地点和路线都非空才返回成功，否则返回非零退出码并提示失败步骤。不会输出 Key。距离单位为米，耗时单位为秒。

## 行程工作流

旅行条件和行程与聊天一起持久化在 SQLite checkpoint 中，按会话隔离。模型从用户文字提取出发地、目的地、开始日期、天数、人数、全员人民币预算和偏好；关键条件缺失时返回缺失字段并追问，不猜测日期和预算口径。偏好默认无特殊偏好。

条件齐全后检索知识库、搜索最新资料，再查询地点及相邻地点驾车路线。配置 `AMAP_API_KEY`（高德 Web 服务 Key）启用地图；未配置或失败会返回未核实。接口依据[高德地点搜索文档](https://developer.amap.com/api/webservice/guide/api/search/)和[路径规划文档](https://lbs.amap.com/api/webservice/guide/api/direction)。目前地图适用于中国境内，路线仅为驾车结果。

模型提交结构化行程后，程序在后台检查连续日期、天数、活动顺序、交通时间预留、城市一致性及全员总费用；首次失败后最多再调整两次。用户直接阅读聊天答案，需要修改时继续对话，无需理解 JSON、保存、审核或确认。

每条已完成的助手回答下都有“导出这份回答为 PDF”。导出依据 SQLite 中该条回答的唯一标识及正文生成，不读取当前最新行程，也不重新调用模型。例如同一对话先问上海、再问重庆，两个按钮分别导出上海和重庆；修改方案后的新答案有自己的导出入口。刷新或重启服务后可继续导出历史回答。未完成回复不提供导出入口。查看与导出会过滤“检查项”“待确定事项”等内部段落及其子项，保留实际行程、美食、来源和安全提醒；历史攻略重新导出也使用此过滤。导出内容不代表价格或地点经过独立认证。

每日标题显示中文日期、星期几与对应日期的天气预报，例如“2026年11月6日 · 星期五 · 天气预报：白天晴，夜间多云，3至12℃”（格式示例，非实际预报）。无有效预报时显示“暂无预报”或“超出预报范围”；日期未定时仍按第几天展示。版本攻略使用保存时的天气记录，查看或导出不会额外联网，也不会用新查询替换旧版预报。

新攻略包含独立的“当地特色美食”模块，介绍目的地菜品或小吃的特点、顺路用餐建议及忌口提示，复用当前规划模型和资料检索，不增加单独模型调用或依赖。已保存且未记录美食的历史版本不会在导出时临时编造推荐，可在对话中生成新版。北京美食参考资料位于 `knowledge/beijing-food.md`。版本预览与 PDF 不展示“查看地图”位置链接，内部地点核对仍正常执行。

回答末尾的“参考来源”默认折叠，点击可展开文档名称和公开链接，PDF 中完整保留来源。云检索不向模型提供文档 ID；最终回答、历史和 PDF 继续对已知内部 ID 脱敏。

当前网页使用的接口：

- `GET /sessions/{id}`：历史回答包含稳定的 `message_id`。
- `POST /chat/stream`：完整 `done` 事件包含答案及 `message_id`。
- `POST /asr`：录音转文字，只回填文本框，不产生对话。
- `GET /sessions/{id}/watch`：出发前复核状态与最近一次 diff。
- `POST /sessions/{id}/watch/check`：立刻复核当前版本；不在 3 天窗口内返回 409。
- `GET /sessions/{id}/answers/{message_id}/pdf`：导出这一会话中指定的已完成回答；不存在返回 404，非法标识返回 422，服务繁忙返回 409。

旧的 `/trip`、`/trip/confirm` 和 `/trip/pdf` 接口保留兼容已有调用，网页不再使用它们。旧接口的确认限制不影响按回答导出。

最小版本限制：结构化规划面向单一目的地城市、最多 30 天。城市检查依据结构化字段，不是独立地理认证。地点真实性、开放时间及路线估算仍取决于外部工具和模型正确使用结果；未核实资料会保留到 PDF，出行前需核实。

车次查询支持免费自部署的第三方12306 MCP。快速规划中的出发地和日期可选，新增交通方式及铁路查询按钮；缺少出发条件可按第几天规划目的地攻略。[完整配置与排错教程](docs/12306-mcp-setup.md)。安装可选依赖 `uv sync --extra rail` 并配置 `RAIL_MCP_URL` 后启用。

## 语音成行（Voice intake）

`POST /asr` 只做一件事：把这段录音转成文字，原样回给页面。前端拿到文字后填进输入框，用户确认或改完再自己点发送，走的还是原来的 `/chat/stream`。**语音永远不会直接进大模型**——地名、日期、人数只要听错一个字，用户都有机会在发送前改掉，不需要靠模型猜。

- 请求：原始音频字节（`Content-Type: audio/webm|audio/ogg|audio/mp4|audio/wav|audio/mpeg`），上限 8MB、60 秒，超限分别返回 413 / 415。
- 响应：`{text, raw, corrections, provider}`；`corrections` 是按热词表改回来的部分，页面会显示“鼓浪与 → 鼓浪屿”这样的提示。
- 两个免费路径：`ASR_API_KEY` 配任意 OpenAI 兼容 `/audio/transcriptions`（各家免费额度都能用），或设 `ASR_PROVIDER=local` 用 faster-whisper 在本机跑，零调用成本。没配密钥时自动走 local，两者都没有则明确返回 503，不会静默降级成“假装识别”。
- 热词表在 `travelmate/asr.py`：15 个城市 + 20 个景点共 35 条，既作为识别提示词（`ASR_PROMPT=1`）传给接口，也在识别后做一次纠错。纠错只处理三个字以上的词、且要求同长度错一两个字或多／少一个字，两个字的城市（北京/南京）一律不动——错一个字就是另一个地方，宁可让用户自己改。
- 频控：每用户每小时 30 次、每天 200 次；不与生成额度混用。

## 行前保鲜（Trip Watch）

出发前 3 天，系统按当前版本重跑一次检索，只报“哪条变了、差多少”，不重做行程。

- 触发：进程内定时任务（`WATCH_SCHEDULER=1`，默认每 60 分钟扫描一次）+ 页面上的“现在复核”按钮（`POST /sessions/{id}/watch/check`）。
- 选目标：从已存的 `versions` 快照里取当前版本，按 **车次 > 门票/开放时间 > 地点** 排序，并且只挑 `evidence.expires_at` 已过期的项——依据没过期就不花钱重查。每次最多 `WATCH_MAX_QUERIES`（默认 3）次检索，说清“另有 N 项本轮没重跑”。
- 比对：车次比时刻与同席别票价；门票/开放时间用 `search_web` 重跑后从文本里抽数字和时段，和快照里 `stop.cost`、`stop.opening_hours` 比；地点用 `search_places` 比名称与地址（沿用 `same_label` 的全半角容错）。抽不到数据时标“未取到”，不猜。
- 输出：`| 项目 | 变动前 | 变动后 | 差额 |` 的 diff 表，写进会话消息，同时在页面顶部留一张复核卡片。同一版本 24 小时内不重复复核（`WATCH_INTERVAL_HOURS`），期间手动点按钮可强制重查。
- 成本：每次 2–3 次搜索调用，量级与一次调研相当；没有变动的版本一天最多花一次。

## 交通时刻与票价

- **铁路**：配了 `RAIL_MCP_URL` 就走 12306 MCP，拿真实车次号、发到时刻和票价；没配或查询失败时自动改用联网搜索，只给参考票价与大致时段，标注待核实，**不编车次号**。
- **飞机**：没有可用的实时接口，一律走联网搜索取参考票价与最早/最晚班次，同样标注待核实。
- **时间锚点**：去程取「最早到达」、返程取「最晚出发」，作为行程编排的起止边界传给生成环节——首日从到达时刻加出站通勤之后开始，末日必须在返程出发前 90 分钟收尾。没有锚点（如飞机只有参考班次）时按条件式安排写「抵达后/出发前」，不假设早班抵达。
- 锚点只影响编排建议，**不进入硬校验**：赶不上不会被判定为错误、不会触发反复重排，最多在 notes 里提示压缩或删减。

## 百炼知识库的标签与过滤

**标签规范**：一个文件一个城市标签，`厦门.md -> ["厦门"]`。不留景点级标签（故宫、鼓浪屿这类）——过滤是粗筛，细了反而要求上传时维护几百个标签，检索收益为零。

**检索侧已经接上过滤**（`knowledge.py`）：查询时带上目的地城市，`search_filters` 只认 JSON 字符串形式 `{"tags": "[\"厦门\"]"}`，传数组会被**静默忽略**（这是实测的坑）。过滤后为空（库里没有该城市）自动退回全库检索，并在返回里标 `city_filter: off`。

实测：查「厦门」只返回厦门文档；查「九寨沟」（库里没有）自动回退，返回其它城市文档。

**批量改标签**：

```bash
.venv/Scripts/python.exe scripts/tag_kb.py plan              # 只读，看现状与建议值
.venv/Scripts/python.exe scripts/tag_kb.py apply --all       # 真写，按文件名映射成城市标签
.venv/Scripts/python.exe scripts/tag_kb.py apply --file 北京.md
```

脚本用 `batch_update_file_tag`（一次 20 个），`update_mode=replace`；省份文件（如 `福建.md`）认不出城市会跳过，需人工处理。

**内容改了要重传**：百炼没有「更新文件内容」的接口，索引是切片快照，改正文只能删旧文件→传新文件→重建索引。标签不用重传，可以单独批量改。注意 front matter 不会变成百炼的元数据，它只是切片文本的一部分，价值在阅读与本地检索，不在云端过滤。

## 知识库源文件的规范化

`scripts/normalize_kb.py` 把人工整理的城市攻略 Markdown 转成带元数据、切片友好的条目：

```bash
.venv/Scripts/python.exe scripts/normalize_kb.py "E:/test/travel-agent/data/knowledge/已录入" kb
```

输出到 `kb/`（英文目录，已加入 `.gitignore`，**不入库**）：每个城市一个 `cities/{城市名}.md`（中文文件名，和百炼里的文档名一致），带 city/tags/best_season/valid_until 等 front matter、统一 8 段结构、每景点一行「速查」、超长段落按句切分。另有 `kb/_index.json` 供检索前过滤。字段说明见 `kb/README.md`。

注意：front matter 只有上传到百炼时写进文档 metadata 才有过滤价值，光放本地不生效。

## 检索顺序（知识库优先）

1. 先查知识库（本地 Markdown 或阿里云百炼）。有一条原文超过约 120 字就认为**命中**，跳过联网找攻略——省钱，也少一个幻觉来源。
2. 价格不受影响：`COST_MODE=research` 时仍会联网查票价与人均，因为价格是实时信息，知识库不可能有。
3. 没命中（空结果、报错、只有零散短句）才走联网搜索；两边都没有就按原规则降级为 ⏳ 待核实。
4. 参考来源会写明来源类型：`本地知识库「杭州.md」 · 文档参考`、`网页资料「标题」 · 文档参考`、`高德地点查询`。有知识库参与时，区块开头多一行「本版参考了本地知识库文档」。

## 金额处理两档（COST_MODE）

`COST_MODE=research`（默认）：检索阶段多打一次联网搜索查门票与人均价格，查到的写进 notes 并注明来源，查不到标 ⏳；模型仍不许按记忆报价，也不许编门店价。费用表和三档对照后面会自动附一行「金额来源：网页资料搜索 · 2026-11-06 查询」，说明这批数字来自哪类网上资料、哪天查的。

`COST_MODE=plan`：完全不调研价格。所有 `cost` 填 0 且 `cost_estimated=false`，不写任何具体金额，`cost_notes` 固定写明「本次未做价格调研，费用请按官方渠道确认」，预算只用于取舍排序。适合"先排流程、价格自己订票时再看"的场景，也不再因为凑价格而触发无依据估算。

## 响应速度

- **骨架先行**：「组织片区」那一次模型调用顺便产出按天骨架（主题标题 + 每天 2–4 条要点 + 三档量级），生成完立刻以正文形式流到前端，感知等待从"等完整攻略"降到十几秒；完整版校验通过后替换同一气泡，不产生第二条消息，历史与 PDF 仍是完整版。
- **检索并发**：知识库、网页、价格、天气、车次同时发出，不再串行等 HTTP；车次去返程在同一线程内顺序执行，避免抢同一个 MCP 会话。
- **依据瘦身**：给模型的 evidence 只保留判断要用的字段（id/kind/value/title/url/status/address/location/query/expires_at），实测生成输入减少三分之一；程序核验仍用完整记录。
- **审查可换模型**：`REVIEW_MODEL_NAME` 指定更快的模型只做审查，留空则与主模型相同。审查只看硬伤，不需要旗舰模型。

## 复查开关（REVIEW_MODE）

`REVIEW_MODE=program`（默认）：不调第二个模型做语义审查，只跑程序检查——日期天数、时段衔接、交通预留、预算超支、城市一致、返程时限、引用是否支持字段值、车次有无依据、爬山排除项这些硬错误照样 blocking，`blocked` 分支和降级逻辑不变。

`REVIEW_MODE=full`：恢复独立模型审查（跨城折返、体力不匹配、把无依据的营业时间写成事实这类软问题）。审查记录里的 `prompt_version` 会写 `program-only` 或 `reviewer-v1`，历史能看出这一版有没有做过语义审查。

代价：program 模式下，模型在 notes 里编造营业时间、安排跨片区折返这类问题不会被独立发现，只靠生成指令约束。

## 行程时间段格式

每日行程的「时段」列统一显示成 `09:00–11:00（上午）`：精确方案给确定的起止时间；交通耗时不确定、被降级成分时段安排时，**原来的时刻会保留成建议窗口**，不会退化成只写「上午」。降级后仍会提示可以按实际到达时间前后挪动。

## 图文攻略页（HTML）

每版方案保存后都有一页 HTML：`GET /sessions/{id}/plans/{version}`，聊天回答下方的「查看图文攻略」直接打开。页面是单文件、样式内联、零外链，含渐变头图（按目的地从内置图里选：山地/海滨/城镇三类）、概览卡、每日时间轴表格、避坑红框、待核实清单，手机端自适应，可直接 Ctrl+P 存 PDF。

头图是**示意图不是实景**，页脚有标注。要换成目的地实景图，把同尺寸 webp 放好并改 `DESTINATION_IMAGES` 的匹配词即可。

## 攻略输出与 Markdown 下载

输出按“结论→概览→预算→交通住宿→每日路线→美食→备选→行前准备→来源”组织，聊天与版本攻略共用内容。全费用人民币预算可展示“预算预留额度（非报价）”，分项合计等于用户总预算；实际费用仍以查询依据显示。美食偏好进入每日路线。首轮先给玩法草案，再确认缺失的预算口径及范围，步数不再必填。

每条回答和版本攻略提供 Markdown 下载：`GET /sessions/{id}/answers/{message_id}/md`、`GET /sessions/{id}/plans/{version}/md`，与 PDF 一样校验归属，按原记录导出，不重新调用模型。配置 DeepSeek 密钥（`MODEL_API_KEY`）或 `TAVILY_API_KEY` 后每次规划最多增加一次网页资料检索，未配置时继续使用已有资料、铁路和天气工具。参考稿的优缺点与接入状态见[对照分析](docs/reference-output-review.md)。
