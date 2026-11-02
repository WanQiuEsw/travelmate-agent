from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from travelmate.agent import chat, open_agent
from travelmate.api import create_app
from travelmate.tools import estimate_budget, knowledge_tool, search_web


class BudgetModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "offline-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            message = AIMessage(content="预算：" + messages[-1].content)
        else:
            message = AIMessage(content="", tool_calls=[{
                "name": "estimate_budget", "args": {"days": 3, "travelers": 2,
                "daily_per_person": 200, "transport_total": 600}, "id": "budget-1"}])
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_budget():
    args = dict(days=3, travelers=2, daily_per_person=200, transport_total=600)
    assert estimate_budget.invoke(args)["total"] == 1800
    for value in (-1, float("nan"), float("inf")):
        assert "error" in estimate_budget.invoke({**args, "daily_per_person": value})
    assert "error" in estimate_budget.invoke({**args, "travelers": 0})


def test_knowledge_and_search(tmp_path, monkeypatch):
    (tmp_path / "杭州.md").write_text("杭州西湖游览建议", encoding="utf-8")
    tool = knowledge_tool(tmp_path)
    assert tool.invoke({"query": "西湖"})["results"][0]["source"] == "杭州.md"
    assert tool.invoke({"query": "xyz"})["results"] == []
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert "error" in search_web.invoke({"query": "杭州"})


def test_real_agent_loop_persistence_and_isolation(tmp_path):
    database = tmp_path / "memory.sqlite"
    with open_agent(model=BudgetModel(), database=database, knowledge=tmp_path) as agent:
        assert "1800" in chat(agent, "alice", "算预算")
    with open_agent(model=BudgetModel(), database=database, knowledge=tmp_path) as agent:
        state = agent.get_state({"configurable": {"thread_id": "alice"}})
        assert len(state.values["messages"]) == 4
        assert not agent.get_state({"configurable": {"thread_id": "bob"}}).values
        chat(agent, "alice", "再算一次")
        assert len(agent.get_state({"configurable": {"thread_id": "alice"}}).values["messages"]) == 8


def test_api(tmp_path):
    @contextmanager
    def factory():
        with open_agent(model=BudgetModel(), database=tmp_path / "api.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/chat", json={"session_id": "demo", "message": "预算"})
        assert response.status_code == 200
        assert "1800" in response.json()["answer"]
        for message in (" ", "x" * 8001):
            assert client.post("/chat", json={"session_id": "demo", "message": message}).status_code == 422
        assert client.post("/chat", json={"session_id": "../bad", "message": "hi"}).status_code == 422


def test_api_failure():
    class BrokenAgent:
        def invoke(self, *args):
            raise RuntimeError("secret-token")

    @contextmanager
    def factory():
        yield BrokenAgent()

    with TestClient(create_app(factory)) as client:
        response = client.post("/chat", json={"session_id": "demo", "message": "hi"})
        assert response.status_code == 502
        assert "secret-token" not in response.text
