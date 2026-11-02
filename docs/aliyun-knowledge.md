# 阿里云百炼知识库

当前对接中国站北京地域的「文档搜索类知识库」Retrieve OpenAPI（2023-12-29），不调用百炼应用生成回答。DeepSeek 继续回答，LangChain 按需调用检索工具。

入库：在控制台上传旅游文档 → 云端解析与切片 → Embedding → 云端索引。

查询：结合对话生成独立检索问题 → 云端查询向量及关键词检索 → 重排 → 返回最多三段原文和来源 → DeepSeek 参考资料回答。

## 接入步骤

1. 在百炼中国站北京地域创建文档搜索类知识库，上传有使用权的攻略，等待索引完成，并在控制台测试召回。
2. 获取业务空间 ID 和知识库 ID。
3. 为已加入业务空间的 RAM 身份授权检索权限，取得 AccessKey ID/Secret。优先限制到 Retrieve 所需权限。这是阿里云 OpenAPI 凭据，不是 DeepSeek 密钥或 DashScope 模型 API Key。不要提交 Git 或放到网页。
4. 安装可选 SDK：`uv sync --extra dev --extra aliyun`。
5. 在现有 `.env` 补充，保留原有 DeepSeek 配置：

```dotenv
KNOWLEDGE_PROVIDER=aliyun
ALIBABA_CLOUD_ACCESS_KEY_ID=你的AccessKeyID
ALIBABA_CLOUD_ACCESS_KEY_SECRET=你的AccessKeySecret
ALIYUN_WORKSPACE_ID=你的业务空间ID
ALIYUN_INDEX_ID=你的知识库ID
```

临时凭据还需设置 `ALIBABA_CLOUD_SECURITY_TOKEN`。

```powershell
uv run --extra aliyun uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000，新建对话，询问「根据知识库介绍杭州适合长辈的行程，并列出文档来源」。CLI 也可运行 `uv run --extra aliyun travelmate --session aliyun-demo`。

设 `KNOWLEDGE_PROVIDER=local` 可恢复本地字符检索。云端失败会明确返回错误，不会悄悄改用本地；空召回返回空列表。

## 三种方案的区别

| 方案 | 自己负责 | 特点 |
|---|---|---|
| 百炼托管知识库（本次） | 文档质量、权限、召回配置 | 少运维；文档及检索问题发送云端 |
| 云 Embedding + 本地向量库 | 切片、入库、检索、索引更新 | 不运行本地模型，但自己管理 RAG |
| 本地 Embedding + 本地向量库 | 上述流程及模型环境 | 本地处理向量化，消耗内存和算力 |

本地 Embedding 不必然需要 GPU；如果回答仍调用云端 DeepSeek，召回原文仍会发到云端。云端也不必然更准，需要用实际问题评估。

文档和查询应使用兼容的 Embedding 模型及向量空间；托管服务维护这种对应关系。生成模型、Embedding 模型和向量数据库是三个组件。只对检索问题向量化，不必把全部系统提示和历史对话向量化；这不是训练 DeepSeek。

相关解析、向量化、重排及存储的费用以当前控制台及所用服务说明为准，不假定免费。

## 验证边界

离线测试验证 SDK 请求参数、响应映射、空召回、错误脱敏、配置和 LangChain 工具循环。尚未用真实账号验证云端权限、索引及召回质量。

知识库不能替代对话记忆。网页刷新会创建新会话；本次提示词要求检索时补全上下文，但尚未加入网页会话恢复或结构化旅行偏好。

官方依据：
- https://help.aliyun.com/zh/model-studio/rag-knowledge-base-api-guide
- https://www.alibabacloud.com/help/en/model-studio/api-bailian-2023-12-29-retrieve
