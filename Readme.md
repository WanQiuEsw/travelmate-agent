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

打开 http://127.0.0.1:8000 使用聊天页面。前端为原生 HTML/CSS/JavaScript，由 FastAPI 同时提供，无需 Node.js、npm 或额外依赖。支持发送消息、等待提示、失败后保留输入、新建会话；刷新会开始新会话，旧记录仍保存在服务端。回答以纯文本展示，不额外引入 Markdown 渲染器。

也可打开 http://127.0.0.1:8000/docs，通过 POST /chat 发送：

```json
{"session_id":"demo","message":"两个人去杭州三天，帮我规划"}
```

GET /health 为进程健康检查，不验证外部模型是否可用。API 为本地单用户版，无认证，不要直接暴露公网；会话以明文存入 data/checkpoints.sqlite。删除此数据库及关联的 WAL/SHM 文件前应先停止服务，并确认不再需要历史记录。

## 验证

```powershell
uv run pytest -q
```

离线测试使用确定性的测试模型驱动真实 create_agent 工具循环，不调用付费接口。覆盖预算、知识检索、未配置搜索、SQLite 重启与隔离、API 校验和上游错误脱敏。尚未验证真实模型与 Tavily 的账号权限、网络和生成质量。

## 后续开发建议

先用真实密钥验证一条完整旅游需求，再接高德地点/路线和天气工具；随后升级向量 RAG 与结构化行程，最后添加 MCP、PDF 和流式网页。每阶段继续独立提交，避免一次性复制原项目所有工具。
