import json
from contextlib import contextmanager

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

from travelmate.agent import open_agent, tool_progress
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
        with open_agent(legacy_tool_loop=True, model=StreamingBudgetModel(), database=tmp_path / "sse.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        with client.stream("POST", "/chat/stream", json={"session_id": "sse", "message": "预算"}) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            frames = [line for line in response.iter_lines() if line]
        assert frames.count("event: token") >= 1
        assert "event: status" in frames and "event: done" in frames
        assert "event: error" not in frames
        data = [json.loads(line[6:]) for line in frames if line.startswith("data: ")]
        assert data[-1]["answer"] == "预算合计1800元\n供参考"
        events = [(frames[i][7:], json.loads(frames[i + 1][6:])) for i in range(0, len(frames), 2)]
        assert ''.join(payload['text'] for event, payload in events if event == 'token') == data[-1]['answer']
        history = client.get("/sessions/sse").json()
        assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
        assert history["messages"][-1]["content"] == data[-1]["answer"]
        assert history["messages"][-1]["message_id"] == data[-1]["message_id"]
        assert client.get(f"/sessions/sse/answers/{data[-1]['message_id']}/pdf").status_code == 200
        assert not history["interrupted"]
        assert client.get("/sessions").json()["sessions"] == [{"session_id": "sse", "title": "预算", "pinned": False}]
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


def test_tool_progress_sources_and_failure(monkeypatch):
    monkeypatch.setenv("ALIYUN_INDEX_ID", "secret-index")
    result = tool_progress(ToolMessage(name="search_web", tool_call_id="one", content=json.dumps({
        "results": [{"title": "官方攻略", "url": "https://example.com/guide", "content": "private body"}]})))
    assert result["sources"] == [{"title": "官方攻略", "url": "https://example.com/guide"}]
    assert "1 条结果" in result["text"]
    assert "private body" not in str(result)
    failed = tool_progress(ToolMessage(name="search_web", tool_call_id="two", content='{"error":"private-key"}'))
    assert "失败" in failed["text"] and "private-key" not in str(failed)
    empty = tool_progress(ToolMessage(name="search_knowledge", tool_call_id="three", content='{"results":[]}'))
    assert "未找到" in empty["text"]


def test_map_and_knowledge_progress_are_concise():
    mapped = tool_progress(ToolMessage(name="search_places", tool_call_id="map", content='{"results":[{"name":"机场细节"}]}'))
    assert mapped == {"text": "已通过高德查询。"}
    knowledge = tool_progress(ToolMessage(name="search_knowledge", tool_call_id="kb", content=json.dumps({"results": [{"source": "重庆知识库（城市概况）", "content": "长篇资料"}]})))
    assert knowledge == {"text": "已使用重庆知识库。"}


def test_refresh_during_generation_does_not_wait_for_model(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import travelmate.api as api

    started, release = Event(), Event()
    original = api.stream_chat

    def paused_stream(*args):
        started.set()
        assert release.wait(10), "test did not release generation"
        yield from original(*args)

    monkeypatch.setattr(api, "stream_chat", paused_stream)

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=StreamingBudgetModel(), database=tmp_path / "refresh.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory)) as client, ThreadPoolExecutor(max_workers=3) as pool:
        running = pool.submit(client.post, "/chat/stream", json={"session_id": "refresh", "message": "预算"})
        try:
            assert started.wait(5)
            # Simulate reload before the first checkpoint exists.
            listing = pool.submit(client.get, "/sessions").result(timeout=2)
            history = pool.submit(client.get, "/sessions/refresh").result(timeout=2)
            assert listing.status_code == history.status_code == 200
            assert history.json()["generating"] is True
            duplicate = pool.submit(client.post, "/chat", json={"session_id": "refresh", "message": "继续"}).result(timeout=2)
            assert duplicate.status_code == 409
        finally:
            release.set()
        assert "event: done" in running.result(timeout=10).text
        history = client.get("/sessions/refresh").json()
        assert history["generating"] is False
        assert len(history["messages"]) == 2


def test_disconnected_stream_keeps_progress_and_completes(tmp_path, monkeypatch):
    import asyncio
    from threading import Event
    import travelmate.api as api

    release, completed = Event(), Event()
    original = api.stream_chat

    def paused_stream(*args):
        yield "status", {"text": "正在查询景点", "sources": [{"title": "景区官网", "url": "https://example.com"}]}
        assert release.wait(10), "test did not release generation"
        try:
            yield from original(*args)
        finally:
            completed.set()

    monkeypatch.setattr(api, "stream_chat", paused_stream)

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=StreamingBudgetModel(), database=tmp_path / "disconnect.sqlite") as agent:
            yield agent

    app = create_app(factory)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/chat/stream")

    async def disconnect():
        sent = asyncio.Event()

        async def send(frame):
            if frame.get("body", b"").find("正在查询景点".encode()) >= 0:
                sent.set()

        async def receive():
            await sent.wait()
            return {"type": "http.disconnect"}

        response = endpoint(api.ChatRequest(session_id="reload", message="预算"))
        await response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)

    with TestClient(app) as client:
        try:
            asyncio.run(disconnect())
            history = client.get("/sessions/reload").json()
            assert history["generating"] is True
            assert history["progress"]["message"] == "预算"
            assert history["progress"]["started_at"] > 0
            assert history["progress"]["steps"][-1]["text"] == "正在查询景点"
            assert history["progress"]["steps"][-1]["sources"][0]["title"] == "景区官网"
        finally:
            release.set()
        assert completed.wait(10)
        # Wait for the worker's generation guard to release as well.
        app.state.executor.shutdown(wait=True)
        history = client.get("/sessions/reload").json()
        assert history["generating"] is False
        assert history["progress"] is None
        assert history["messages"][-1]["content"] == "预算合计1800元\n供参考"
