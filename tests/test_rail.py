import asyncio
import json
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import travelmate.rail as rail
from travelmate.api import create_app


def test_rail_validation_and_disabled_config(monkeypatch):
    monkeypatch.delenv("RAIL_MCP_URL", raising=False)
    day = rail.china_today().isoformat()
    args = dict(origin="上海", destination="北京", departure_date=day)
    assert "未启用" in rail.search_train_tickets.invoke(args)["error"]
    assert "出发地" in rail.search_train_tickets.func(**{**args, "origin": " "})["error"]
    assert "日期" in rail.search_train_tickets.invoke({**args, "departure_date": "2026-02-30"})["error"]
    assert "日期" in rail.search_train_tickets.invoke({**args, "departure_date": (rail.china_today() - timedelta(days=1)).isoformat()})["error"]
    assert "格式" in rail.search_train_tickets.invoke({**args, "origin": "上海|北京"})["error"]
    assert "仅支持" in rail.search_train_tickets.func(**{**args, "transport": "飞机"})["error"]


def test_mcp_station_resolution_and_ticket_filters(monkeypatch):
    mcp = pytest.importorskip("mcp")
    import mcp.client.sse as transport
    calls = []

    @asynccontextmanager
    async def connection(url):
        assert url == "http://127.0.0.1:8081/sse"
        yield None, None

    class Session:
        def __init__(self, *args): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): calls.append(("initialize", {}))
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            if name == "get-station-code-of-citys":
                data = {"上海虹桥": {"error": "missing"}, "北京": {"station_code": "BJP"}}
            elif name == "get-station-code-by-names":
                data = {"上海虹桥": {"station_code": "AOH"}}
            else:
                data = [{"start_train_code": "G123", "start_time": "08:00", "from_station": "上海虹桥", "prices": [], "internal": "hidden"}, {"start_train_code": "G999", "from_station": "上海", "prices": []}]
            return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=json.dumps(data))])
    monkeypatch.setattr(mcp, "ClientSession", Session)
    monkeypatch.setattr(transport, "sse_client", connection)
    result = asyncio.run(rail.query_mcp("http://127.0.0.1:8081/sse", "上海虹桥", "北京", "2026-12-01", "高铁"))
    assert calls[0][0] == "initialize"
    args = calls[-1][1]
    assert args["fromStation"] == "AOH" and args["toStation"] == "BJP"
    assert args["trainFilterFlags"] == "G" and args["date"] == "2026-12-01"
    assert args["limitedNum"] == 8
    assert result["results"][0]["start_train_code"] == "G123"
    assert "internal" not in result["results"][0]
    assert len(result["results"]) == 1


def test_rail_api_and_failure_are_sanitized(monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("RAIL_MCP_URL", "http://127.0.0.1:8081/sse")
    requests = []
    async def query(*args):
        requests.append(args)
        return {"results": [], "notice": "无匹配"}
    monkeypatch.setattr(rail, "query_mcp", query)
    @contextmanager
    def factory(): yield object()
    with TestClient(create_app(factory)) as client:
        body = dict(origin="上海", destination="北京", departure_date=rail.china_today().isoformat(), transport="动车")
        assert client.post("/transport/trains", json=body).json()["results"] == []
        assert requests[-1][-1] == "动车"
        assert client.post("/transport/trains", json={**body, "transport": "飞机"}).status_code == 422
        assert client.post("/transport/trains", json={**body, "origin": ""}).status_code == 422
        async def broken(*args): raise RuntimeError("private-token")
        monkeypatch.setattr(rail, "query_mcp", broken)
        response = client.post("/transport/trains", json=body)
        assert "未核实" in response.json()["error"]
        assert "private-token" not in response.text
