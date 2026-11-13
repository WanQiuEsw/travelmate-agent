"""Select local reference search or Alibaba Cloud managed document retrieval."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from langchain.tools import tool

from travelmate.tools import knowledge_tool


def knowledge_coverage(data, requirements):
    """保守检查参考资料覆盖；分数仅保留供校准，不跨提供商设置阈值。"""
    city = requirements['destination']
    texts, accepted = [], []
    for index, row in enumerate([] if data.get('error') else data.get('results') or []):
        if not isinstance(row, dict) or not isinstance(row.get('content'), str):
            continue
        content = row['content'].strip()
        if not content or (row.get('city') and row['city'] != city):
            continue
        if city not in str(row.get('source', '')) + content and data.get('city_filter') != 'on':
            continue
        if row.get('expires_at'):
            try:
                expiry = datetime.fromisoformat(row['expires_at'])
                if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                    continue
            except (ValueError, TypeError):
                continue
        texts.append(content)
        accepted.append(index)
    text = '\n'.join(texts)
    topics = ['特色美食', *requirements.get('interests', [])]
    preferences = requirements.get('preferences', '')
    if preferences and preferences != '无特殊偏好':
        topics.extend(part.strip() for part in re.split(r'[，,、；;。\n]', preferences) if part.strip())
    aliases = {'特色美食': ('美食', '小吃', '餐饮', '餐厅'), '美食': ('美食', '小吃', '餐饮', '餐厅')}
    # shortcut: 词面匹配会多补查同义表达，有固定评估集后再扩充语义匹配。
    missing = [topic for topic in dict.fromkeys(topics)
               if not any(word in text for word in aliases.get(topic, (topic,)))]
    if not any(word in text for word in ('景点', '游览', '游玩', '参观', '路线', '片区')):
        missing.insert(0, '游览路线与景点')
    return {'accepted_results': accepted, 'missing': missing,
            'queried_at': datetime.now(timezone.utc).isoformat(),
            'dynamic_facts': '价格、开放时间、预约规则和闭馆公告需独立核实'}


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
    def search_knowledge(query: str, city: str = "") -> dict:
        """检索阿里云旅游知识库，返回相关原文、来源与分数；city 为目的地城市，用于按城市标签过滤。"""
        if not query.strip() or len(query) > 2000:
            return {"error": "知识库查询需为 1–2000 字符"}

        def retrieve(filters):
            request = RetrieveRequest(index_id=index, query=query.strip(),
                                      dense_similarity_top_k=10,
                                      sparse_similarity_top_k=10,
                                      enable_reranking=True, rerank_top_n=3,
                                      enable_rewrite=False,
                                      save_retriever_history=False,
                                      search_filters=filters)
            body = client.retrieve_with_options(
                workspace, request, {},
                RuntimeOptions(read_timeout=20000, connect_timeout=5000, autoretry=False)).body
            if body is None or body.success is not True or body.data is None:
                raise ValueError("cloud retrieve failed")
            return body.data.nodes or []

        try:
            # 标签过滤只认 JSON 字符串；传数组会被静默忽略（实测）。
            nodes = retrieve([{"tags": json.dumps([city], ensure_ascii=False)}]) if city else []
            filtered = bool(nodes)
            if not nodes:
                # 库里没有这个城市的标签时退回全库检索，别把知识库整个废掉。
                nodes = retrieve(None)
            results = []
            for node in nodes[:3]:
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
                                "content": node.text[:2500], "score": node.score})
            return {"results": results, "city_filter": "on" if filtered else "off",
                    "notice": "云知识库参考资料；无匹配时不要编造。价格及开放时间仍需实时核实。"}
        except Exception:
            # SDK exceptions may contain signed request details; never return them to the model.
            return {"error": "云知识库请求失败，请检查网络、权限及服务状态；资料未核实"}

    return search_knowledge
