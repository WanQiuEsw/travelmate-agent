from langchain_core.messages import ToolMessage

from travelmate.public import public_data


def test_identifiers_hidden_in_history_plan_and_source(monkeypatch):
    monkeypatch.setenv("ALIYUN_INDEX_ID", "index-private-123")
    messages = [ToolMessage(content='{"results":[{"document_id":"doc-private-456"}]}', tool_call_id="old")]
    value = {"source": "杭州攻略 doc-private-456 index-private-123", "doc_id": "private",
             "notes": "知识库ID：kb-private-789"}
    result = public_data(value, messages)
    assert result["source"].startswith("杭州攻略")
    assert "private" not in str(result)
    assert "doc_id" not in result
