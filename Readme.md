# TravelMate

Python + LangChain 旅游智能体。分步提交：设计 → 核心与工具 → API 和测试。

本阶段：持久对话、工具循环、本地知识检索、联网搜索、预算计算、CLI 和 API。
后续协商：地图/天气、向量 RAG、MCP、PDF、SSE 和网页界面。

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

- SSE 逐步展示模型回复，提示资料查询及计算进度；生成完成后进行排版。
- 当前会话 ID 保存在浏览器 localStorage，刷新后从 SQLite 恢复消息；历史列表展示最近 50 个已有消息的会话，可切换或新建。浏览器禁用存储时仍可从历史列表选择。切换会话会清空未发送的输入。
- 回复支持简单 Markdown 子集：标题、粗体、行内代码、代码块、单层列表、表格和 HTTP(S) 链接；不解析原始 HTML、图片或任意脚本。不支持完整 CommonMark 和复杂嵌套。
- 失败保留输入和本次已收到的部分回复，并标注中断；刷新后以服务端已保存的消息为准。流式请求不自动重试，以免重复提交；手动重新发送可能在历史中留下重复问题。
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

可选前端渲染回归检查（开发验证才需要 Node）：`node --test tests/markdown.test.mjs`。已用离线测试模型完成网页逐步显示、表格与链接、刷新恢复、历史切换、错误保留输入和窄屏检查；不代表真实模型和云知识库联调。

离线测试使用确定性的测试模型驱动真实 create_agent 工具循环，不调用付费接口。覆盖预算、知识检索、未配置搜索、SQLite 重启与隔离、API 校验和上游错误脱敏。尚未验证真实模型与 Tavily 的账号权限、网络和生成质量。

## 后续开发建议

先用真实密钥验证一条完整旅游需求，再接高德地点/路线和天气工具；随后升级向量 RAG 与结构化行程，最后添加 MCP、PDF 和流式网页。每阶段继续独立提交，避免一次性复制原项目所有工具。
