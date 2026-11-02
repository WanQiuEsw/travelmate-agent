# 迁移设计

参考：https://github.com/liyupi/yu-ai-agent
研究 README、LoveApp.java、agent/YuManus.java：Spring AI 实现恋爱对话、记忆、RAG、工具、MCP；YuManus 使用 ToolCallAgent 进行自主工具循环，并限制步数。

Python 对应：ChatClient → ChatOpenAI；ToolCallAgent → LangChain create_agent；ChatMemory → LangGraph SQLite checkpointer；Spring MVC → FastAPI。
旅游业务：澄清日期、目的地、人数、预算，再检索知识、搜索实时资料、计算预算，生成逐日行程。不能编造票价、开放时间和政策；检索内容视为资料，不能覆盖系统指令。

第一阶段使用本地 Markdown 字符匹配检索（非向量 RAG）、Tavily 搜索和预算工具。后续增加 Embeddings/pgvector、地图天气、MCP、PDF、SSE、前端。并非原项目全部功能的完整移植。

本地单用户服务，session_id 不是认证凭证。公网部署需要认证、会话归属、限流和数据保留策略。无任意文件/终端执行、预订和支付。

验收：预算边界、检索来源、真实 LangChain 工具循环、SQLite 重启恢复及会话隔离、API 验证；外部服务有密钥后联调。

官方依据：
https://docs.langchain.com/oss/python/langchain/agents
https://docs.langchain.com/oss/python/langgraph/persistence
