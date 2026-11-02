from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from travelmate.agent import chat, open_agent
from travelmate.knowledge import create_knowledge_tool
from test_travelmate import BudgetModel


@pytest.fixture
def cloud(monkeypatch):
    sdk = pytest.importorskip("alibabacloud_bailian20231229.client")
    from alibabacloud_bailian20231229.models import RetrieveResponseBody

    for key, value in {"KNOWLEDGE_PROVIDER": "aliyun", "ALIYUN_WORKSPACE_ID": "workspace",
                       "ALIYUN_INDEX_ID": "index", "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-id",
                       "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-secret"}.items():
        monkeypatch.setenv(key, value)
    calls = []
    payload = {"Success": True, "Data": {"Nodes": [
        {"Text": "西湖适合慢行", "Score": 0.9,
         "Metadata": '{"doc_name":"杭州攻略.md","doc_id":"doc-1"}'}]}}

    def retrieve(self, workspace, request, headers, runtime):
        calls.append((workspace, request, runtime))
        return SimpleNamespace(body=RetrieveResponseBody().from_map(payload))

    monkeypatch.setattr(sdk.Client, "retrieve_with_options", retrieve)
    return payload, calls, sdk


def test_mapping_and_request(cloud, tmp_path):
    payload, calls, _ = cloud
    tool = create_knowledge_tool(tmp_path)
    result = tool.invoke({"query": "杭州长辈行程"})
    assert result["results"][0] == {"source": "杭州攻略.md",
                                       "content": "西湖适合慢行", "score": 0.9}
    workspace, request, runtime = calls[0]
    assert workspace == "workspace" and request.index_id == "index"
    assert request.query == "杭州长辈行程" and request.enable_reranking
    assert request.rerank_top_n == 3 and runtime.read_timeout == 20000
    assert "error" in tool.invoke({"query": " "})
    assert len(calls) == 1
    payload["Data"]["Nodes"] = []
    assert tool.invoke({"query": "杭州"})["results"] == []
    payload["Success"] = False
    assert "error" in tool.invoke({"query": "杭州"})


def test_metadata_and_failure(cloud, tmp_path, monkeypatch):
    payload, _, sdk = cloud
    tool = create_knowledge_tool(tmp_path)
    payload["Data"]["Nodes"][0]["Metadata"] = {"title": "攻略"}
    assert tool.invoke({"query": "杭州"})["results"][0]["source"] == "攻略"
    payload["Data"]["Nodes"][0]["Metadata"] = "invalid json"
    assert tool.invoke({"query": "杭州"})["results"][0]["source"] == "云知识库文档"

    def fail(*args):
        raise RuntimeError("secret-credential")

    monkeypatch.setattr(sdk.Client, "retrieve_with_options", fail)
    result = tool.invoke({"query": "杭州"})
    assert "error" in result and "secret-credential" not in str(result)


def test_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="KNOWLEDGE_PROVIDER"):
        create_knowledge_tool(tmp_path)
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "aliyun")
    monkeypatch.delenv("ALIYUN_INDEX_ID", raising=False)
    with pytest.raises(ValueError, match="ALIYUN_INDEX_ID"):
        create_knowledge_tool(tmp_path)


def test_agent_cloud_tool_loop(cloud, tmp_path):
    class KnowledgeModel(BudgetModel):
        def _generate(self, messages, **kwargs):
            if isinstance(messages[-1], ToolMessage):
                answer = AIMessage(content=messages[-1].content)
            else:
                answer = AIMessage(content="", tool_calls=[{"name": "search_knowledge",
                    "args": {"query": "杭州长辈行程"}, "id": "search-1"}])
            return ChatResult(generations=[ChatGeneration(message=answer)])

    with open_agent(model=KnowledgeModel(), database=tmp_path / "cloud.sqlite") as agent:
        answer = chat(agent, "cloud", "杭州长辈行程")
        assert "杭州攻略.md" in answer and "西湖适合慢行" in answer
