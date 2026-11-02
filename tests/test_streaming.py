import json
from contextlib import contextmanager

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

from travelmate.agent import open_agent
from travelmate.api import create_app
from test_travelmate import BudgetModel


class StreamingBudgetModel(BudgetModel):
    def _stream(self, messages, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            for text in ("预算", "合计", "1800元\n供参考"):
                yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        else:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                "name": "estimate_budget", "args": json.dumps({"days": 3, "travelers": 2,
                "daily_per_person": 200, "transport_total": 600}), "id": "call-1", "index": 0}]))


def test_sse_real_tool_loop(tmp_path):
    @contextmanager
    def factory():
        with open_agent(model=StreamingBudgetModel(), database=tmp_path / "sse.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        with client.stream("POST", "/chat/stream", json={"session_id": "sse", "message": "预算"}) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            frames = [line for line in response.iter_lines() if line]
        assert frames.count("event: token") == 3
        assert "event: status" in frames and "event: done" in frames
        assert "event: error" not in frames
        data = [json.loads(line[6:]) for line in frames if line.startswith("data: ")]
        assert data[-1]["answer"] == "预算合计1800元\n供参考"
        history = client.get("/sessions/sse").json()
        assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
        assert history["messages"][-1]["content"] == data[-1]["answer"]
        assert not history["interrupted"]
        assert client.get("/sessions").json()["sessions"] == [{"session_id": "sse", "title": "预算"}]
        assert client.get("/sessions/other").json()["messages"] == []
        assert client.get("/sessions/bad.id").status_code == 422
        assert client.post("/chat/stream", json={"session_id": "sse", "message": " "}).status_code == 422

    with TestClient(create_app(factory)) as client:
        assert len(client.get("/sessions/sse").json()["messages"]) == 2
        client.post("/chat/stream", json={"session_id": "sse", "message": "继续调整"})
        assert len(client.get("/sessions/sse").json()["messages"]) == 4


def test_sse_failure_is_sanitized():
    class Broken:
        def stream(self, *args, **kwargs):
            raise RuntimeError("private-api-key")

    @contextmanager
    def factory():
        yield Broken()

    with TestClient(create_app(factory)) as client:
        response = client.post("/chat/stream", json={"session_id": "bad", "message": "hi"})
        assert "event: error" in response.text
        assert "private-api-key" not in response.text
        assert "event: done" not in response.text
