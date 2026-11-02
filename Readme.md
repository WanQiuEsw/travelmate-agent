# TravelMate

Python + LangChain 旅游智能体。分步提交：设计 → 核心与工具 → API 和测试。

本阶段：持久对话、知识检索、联网搜索、地点与驾车路线、结构化行程校验、用户审核、PDF、CLI、SSE 和网页界面。
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

默认使用 DeepSeek 官方兼容接口的 deepseek-flash，并显式关闭思考模式以适配当前通用客户端的工具循环。模型必须支持 tool calling。可以通过 MODEL_NAME / MODEL_BASE_URL / MODEL_API_KEY 切换兼容服务；无密钥不会伪造模型回复。费用以服务商账单为准。

在 https://platform.deepseek.com/ 登录开放平台，在 API Keys 中创建密钥，保存至本地 `.env` 的 `MODEL_API_KEY`，并确认账户有可用 API 余额。不要将密钥发到聊天或提交 Git。模型名称及费用以 https://api-docs.deepseek.com/ 为准。

```dotenv
MODEL_API_KEY=在本地填入你的DeepSeek密钥
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
```

本地运行的是 Python 程序；模型通过网络调用 DeepSeek 云端，并非在本机部署模型。TAVILY_API_KEY 是独立的搜索服务密钥，可暂时留空；留空时联网检索会明确返回不可用。修改配置后重启程序。如果系统环境变量已经设置同名配置，它会优先于 `.env`。

示例：`从上海出发，两个人，杭州三天，预算3000元，喜欢自然风景，帮我规划`。再次使用 `--session demo` 可继续对话。知识文件放在 `knowledge/*.md`，每次检索读取最新文件；示例资料并非实时旅游数据库。

```powershell
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 使用聊天页面。前端为原生 HTML/CSS/JavaScript，由 FastAPI 同时提供，无需 Node.js、npm 或额外运行依赖。

- SSE 接收模型回复并提示资料查询、计算及生成进度；生成过程中不展示未排版的正文，收到完整回复后进行 Markdown 排版并一次性展示。
- 当前会话 ID 保存在浏览器 localStorage，刷新后从 SQLite 恢复消息；历史列表展示最近 50 个已有消息的会话，可切换或新建。浏览器禁用存储时仍可从历史列表选择。切换会话会清空未发送的输入。
- 回复支持简单 Markdown 子集：标题、粗体、行内代码、代码块、单层列表、表格和 HTTP(S) 链接；不解析原始 HTML、图片或任意脚本。不支持完整 CommonMark 和复杂嵌套。
- 失败保留输入并提示未完成，不展示未排版的部分回复；刷新后以服务端已保存的消息为准。流式请求不自动重试，以免重复提交；手动重新发送可能在历史中留下重复问题。
- Ctrl/Command + Enter 发送；手机布局和可见焦点样式。设计参考 UI UX Pro Max 的通用可读性、可访问性建议：https://github.com/nextlevelbuilder/ui-ux-pro-max-skill 。

接口：`POST /chat/stream` 返回 SSE `status`、`token`、`done` 或 `error` 事件；`done` 包含最终回复，只有收到它才表示完整结束。`GET /sessions` 列出本地会话，`GET /sessions/{session_id}` 读取用户及最终助手消息，不返回工具内部消息。原 `POST /chat` 保留。

这是单用户学习版：历史接口没有身份认证，流式请求仍串行执行；不要直接暴露公网。网页断开连接不保证立即中止已发出的模型/工具请求。部署反向代理时需关闭 SSE 缓冲，并配置合适的读取超时。

也可打开 http://127.0.0.1:8000/docs，通过 POST /chat 发送：

```json
{"session_id":"demo","message":"两个人去杭州三天，帮我规划"}
```

GET /health 为进程健康检查，不验证外部模型是否可用。API 为本地单用户版，无认证，不要直接暴露公网；会话以明文存入 data/checkpoints.sqlite。删除此数据库及关联的 WAL/SHM 文件前应先停止服务，并确认不再需要历史记录。

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

模型提交结构化行程后，程序检查连续日期、天数、活动顺序、交通时间预留、城市一致性、全员总费用；首次失败后最多再调整两次，仍失败则停止并请用户修改条件。有效行程进入审核状态。页面提供逐日预览，可通过聊天修改旅行条件，或展开编辑行程数据，保存后重新校验；点击确认后才能下载中文 PDF。任何条件变更或行程保存都会取消旧确认。费用字段全部为全员人民币，其他费用必须包含住宿、往返交通等说明。

新增接口：

- `GET /sessions/{id}/trip`：读取条件、行程、阶段、校验问题及尝试次数。
- `PUT /sessions/{id}/trip`：保存结构化行程并重新校验。
- `POST /sessions/{id}/trip/confirm`：请求体为用户查看的行程，服务端检查与当前版本一致且通过校验。
- `GET /sessions/{id}/trip/pdf`：仅导出已确认行程，否则返回 409。

最小版本限制：一次旅行为单一目的地城市，最多 30 天；城市检查依据结构化字段，不是独立地理认证。地点真实性、开放时间及路线估算仍取决于外部工具和模型正确使用结果；工具调用顺序和条件提取由提示词驱动，预算、时间、调整上限与确认导出门槛由程序强制执行。未核实资料会保留到 PDF，出行前需核实。
