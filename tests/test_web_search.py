from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from travelmate import tools


def test_deepseek_search_is_the_default_and_maps_results(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"title": "参观须知", "url": "https://example.org", "snippet": "当日开放",
                                 "content": "长" * 3000}]}

    def post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return Response()

    monkeypatch.setenv("MODEL_API_KEY", "ds-key")
    monkeypatch.setenv("MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(tools.httpx, "post", post)
    assert tools.search_web.invoke({"query": "上海博物馆 参观须知"}) == {
        "results": [{"title": "参观须知", "url": "https://example.org", "content": "当日开放"}]}
    assert captured["url"] == "https://api.deepseek.com/v1/tools/search"
    assert captured["headers"]["Authorization"] == "Bearer ds-key"
    assert captured["json"] == {"query": "上海博物馆 参观须知", "count": 5, "need_content": True}


def test_search_provider_falls_back_to_tavily_without_deepseek_key(monkeypatch):
    monkeypatch.setenv("MODEL_BASE_URL", "https://api.deepseek.com")
    assert tools.search_provider() == "tavily"
    monkeypatch.setenv("MODEL_API_KEY", "ds-key")
    assert tools.search_provider() == "deepseek"
    monkeypatch.setenv("MODEL_BASE_URL", "https://other.example/v1")
    assert tools.search_provider() == "tavily"


def test_web_search_uses_configured_mcp_and_normalizes_results(monkeypatch):
    monkeypatch.setenv("TAVILY_SEARCH_TRANSPORT", "mcp")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    async def search(key, query):
        assert (key, query) == ("test-key", "上海博物馆 参观须知")
        return {"results": [{"title": "参观须知", "url": "https://example.org", "content": "馆" * 2100}]}

    monkeypatch.setattr(tools, "tavily_mcp_search", search)
    result = tools.search_web.invoke({"query": "上海博物馆 参观须知"})
    assert result == {"results": [{"title": "参观须知", "url": "https://example.org", "content": "馆" * 2000}]}

    async def unavailable(*args):
        raise TimeoutError

    monkeypatch.setattr(tools, "tavily_mcp_search", unavailable)
    assert "未核实" in tools.search_web.invoke({"query": "上海博物馆 参观须知"})["error"]


def test_mcp_session_parses_tavily_text_with_source_links(monkeypatch):
    mcp = pytest.importorskip("mcp")
    from mcp.client import streamable_http

    @asynccontextmanager
    async def connect(url, http_client):
        assert url == "https://mcp.tavily.com/mcp/"
        assert http_client.headers["Authorization"] == "Bearer test-key"
        yield None, None, None

    class Session:
        def __init__(self, *streams): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): pass

        async def call_tool(self, name, arguments):
            assert name == "tavily_search"
            assert arguments["query"] == "上海博物馆"
            content = ("Request ID: test\nDetailed Results:\n\nTitle: 参观须知\nID: first\n"
                       "URL: https://example.org/visit\nContent: 当日开放信息\n\n"
                       "URL: https://example.org/tickets\nContent: 预约规则")
            return SimpleNamespace(isError=False, structuredContent=None,
                                   content=[SimpleNamespace(type="text", text=content)])

    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(streamable_http, "streamable_http_client", connect)
    monkeypatch.setenv("TAVILY_SEARCH_TRANSPORT", "mcp")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert tools.search_web.invoke({"query": "上海博物馆"})["results"] == [
        {"title": "参观须知", "url": "https://example.org/visit", "content": "当日开放信息"},
        {"title": "", "url": "https://example.org/tickets", "content": "预约规则"},
    ]
