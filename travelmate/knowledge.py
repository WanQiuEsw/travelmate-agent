"""Select local reference search or Alibaba Cloud managed document retrieval."""
import json
import os
from pathlib import Path

from langchain.tools import tool

from travelmate.tools import knowledge_tool


def create_knowledge_tool(directory: Path):
    provider = os.getenv("KNOWLEDGE_PROVIDER", "local")
    if provider == "local":
        return knowledge_tool(directory)
    if provider != "aliyun":
        raise ValueError("KNOWLEDGE_PROVIDER 必须为 local 或 aliyun")
    names = ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
             "ALIYUN_WORKSPACE_ID", "ALIYUN_INDEX_ID")
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError("阿里云知识库缺少配置：" + ", ".join(missing))
    try:
        from alibabacloud_bailian20231229.client import Client
        from alibabacloud_bailian20231229.models import RetrieveRequest
        from alibabacloud_tea_openapi.models import Config
        from alibabacloud_tea_util.models import RuntimeOptions
    except ImportError as exc:
        raise ValueError("请先执行 uv sync --extra aliyun 安装知识库 SDK") from exc

    config = Config(access_key_id=os.environ[names[0]],
                    access_key_secret=os.environ[names[1]],
                    security_token=os.getenv("ALIBABA_CLOUD_SECURITY_TOKEN"))
    config.endpoint = "bailian.cn-beijing.aliyuncs.com"
    client = Client(config)
    workspace = os.environ["ALIYUN_WORKSPACE_ID"]
    index = os.environ["ALIYUN_INDEX_ID"]

    @tool
    def search_knowledge(query: str) -> dict:
        """检索阿里云旅游知识库，返回相关原文、来源与分数；查询应包含明确目的地和需求。"""
        if not query.strip() or len(query) > 2000:
            return {"error": "知识库查询需为 1–2000 字符"}
        try:
            request = RetrieveRequest(index_id=index, query=query.strip(),
                                      dense_similarity_top_k=10,
                                      sparse_similarity_top_k=10,
                                      enable_reranking=True, rerank_top_n=3,
                                      enable_rewrite=False,
                                      save_retriever_history=False)
            response = client.retrieve_with_options(
                workspace, request, {},
                RuntimeOptions(read_timeout=20000, connect_timeout=5000, autoretry=False))
            body = response.body
            if body is None or body.success is not True or body.data is None:
                return {"error": "云知识库检索失败，请检查索引状态及权限；资料未核实"}
            results = []
            for node in (body.data.nodes or [])[:3]:
                if not node.text:
                    continue
                metadata = node.metadata or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except ValueError:
                        metadata = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                results.append({"source": str(metadata.get("doc_name") or
                                              metadata.get("title") or "云知识库文档"),
                                "document_id": str(metadata.get("doc_id") or ""),
                                "content": node.text[:2500], "score": node.score})
            return {"results": results,
                    "notice": "云知识库参考资料；无匹配时不要编造。价格及开放时间仍需实时核实。"}
        except Exception:
            # SDK exceptions may contain signed request details; never return them to the model.
            return {"error": "云知识库请求失败，请检查网络、权限及服务状态；资料未核实"}

    return search_knowledge
