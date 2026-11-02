from copy import deepcopy
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import HumanMessage
from travelmate.agent import open_agent, chat, stream_chat, conversation
from travelmate.workflow import get_workflow
from test_workflow import REQ, PLAN


class Model:
    def __init__(self, intake=None, plans=None, fail=False):
        self.intake = intake or {"intent": "plan", "conditions": REQ}
        self.plans = plans or [PLAN]
        self.fail = fail
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        def run(messages):
            self.calls.append(schema.__name__)
            if schema.__name__ == "Intake":
                return schema.model_validate(self.intake)
            if schema.__name__ == "Areas":
                return schema.model_validate({"areas": [{"name": "西湖片区", "places": ["西湖"]}]})
            if self.fail:
                raise RuntimeError("private-key")
            return schema.model_validate(self.plans.pop(0) if len(self.plans) > 1 else self.plans[0])
        return RunnableLambda(run)


def open_test(tmp_path, model):
    return open_agent(model=model, database=tmp_path / "graph.sqlite", knowledge=tmp_path)


def test_required_order_versions_and_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    with open_test(tmp_path, Model()) as agent:
        text = chat(agent, "trip", "安排杭州一日游")
        state = get_workflow(agent, "trip")
        assert state["status"] == "review" and state["version"] == 1
        assert [row["node"] for row in state["trace"]] == ["requirements", "ready", "research", "organize_places", "verify_places", "generate", "check", "save_version", "present"]
        assert state["versions"][0]["plan"] == state["plan"]
        assert "估算" in text and "待核实" in text
    with open_test(tmp_path, Model(intake={"intent": "modify", "conditions": {"budget": 2000}})) as agent:
        chat(agent, "trip", "预算改成2000")
        state = get_workflow(agent, "trip")
        assert state["version"] == 2
        assert state["versions"][0]["requirements"]["budget"] == 1000
        assert state["versions"][1]["requirements"]["budget"] == 2000
        assert len(conversation(agent, "trip")["messages"]) == 4


def test_clarification_and_question_bypass_planning(tmp_path):
    model = Model(intake={"intent": "plan", "conditions": {"destination": "杭州"}, "direction": "可考虑西湖片区和人文街区。", "questions": ["玩几天？", "几人同行？"]})
    with open_test(tmp_path, model) as agent:
        text = chat(agent, "sparse", "想去杭州")
        assert "西湖" in text
        assert get_workflow(agent, "sparse")["status"] == "collecting"
        assert model.calls == ["Intake"]
    model = Model(intake={"intent": "question", "direction": "可以按兴趣选择片区。"})
    with open_test(tmp_path, model) as agent:
        assert "兴趣" in chat(agent, "qa", "如何选择景点")
        assert model.calls == ["Intake"]


def test_bounded_revision_and_preserve_success(tmp_path):
    with open_test(tmp_path, Model()) as agent:
        chat(agent, "trip", "规划")
        previous = get_workflow(agent, "trip")["plan"]
    bad = {**PLAN, "other_cost": 90000}
    model = Model(intake={"intent": "modify", "conditions": {"budget": 2000}}, plans=[bad])
    with open_test(tmp_path, model) as agent:
        answer = chat(agent, "trip", "改预算")
        state = get_workflow(agent, "trip")
        assert state["status"] == "blocked" and state["attempts"] == 3
        assert state["plan"] == previous and len(state["versions"]) == 1
        assert model.calls.count("Itinerary") == 3
        assert "停止" in answer


def test_generation_failure_keeps_plan_and_masks_error(tmp_path):
    with open_test(tmp_path, Model()) as agent:
        chat(agent, "trip", "规划")
        previous = get_workflow(agent, "trip")["plan"]
    with open_test(tmp_path, Model(fail=True)) as agent:
        answer = chat(agent, "trip", "再规划")
        state = get_workflow(agent, "trip")
        assert state["status"] == "failed" and state["plan"] == previous
        assert "private-key" not in answer


def test_missing_budget_assumption_never_reaches_check(tmp_path):
    req = {k: v for k, v in REQ.items() if k != "budget"}
    model = Model(intake={"intent": "plan", "conditions": req, "assumptions": {"budget": 5000}})
    with open_test(tmp_path, model) as agent:
        chat(agent, "trip", "先估一个预算")
        assert model.calls == ["Intake"]
        assert "budget" in get_workflow(agent, "trip")["missing"]


def test_interrupt_checkpoint_resume_and_stream_status(tmp_path):
    config = {"configurable": {"thread_id": "trip"}}
    with open_test(tmp_path, Model()) as agent:
        agent.interrupt_before_nodes = ["check"]
        agent.invoke({"messages": [HumanMessage(content="规划杭州")]}, config)
        assert agent.get_state(config).next == ("check",)
        assert conversation(agent, "trip")["interrupted"]
    with open_test(tmp_path, Model()) as agent:
        agent.invoke(None, config)
        assert not agent.get_state(config).next
        assert get_workflow(agent, "trip")["status"] == "review"
        events = list(stream_chat(agent, "stream", "规划"))
        assert events[-1][0] == "done"
        assert any(event == "status" for event, _ in events)


def test_revision_can_recover_and_context_changes(tmp_path):
    bad = {**PLAN, "other_cost": 90000}
    with open_test(tmp_path, Model(plans=[bad, PLAN])) as agent:
        chat(agent, "trip", "规划")
        assert get_workflow(agent, "trip")["attempts"] == 2
    req = {**REQ, "destination": "苏州"}
    plan = deepcopy(PLAN)
    plan["days"][0]["stops"][0].update(place="苏州博物馆", city="苏州")
    with open_test(tmp_path, Model(intake={"intent": "modify", "conditions": {"destination": "苏州"}}, plans=[plan])) as agent:
        chat(agent, "trip", "改苏州")
        state = get_workflow(agent, "trip")
        assert state["requirements"]["destination"] == "苏州"
        assert state["versions"][0]["requirements"]["destination"] == "杭州"
        assert state["version"] == 2


def test_default_graph_api_history_pdf_and_failed_edit(tmp_path):
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from travelmate.api import create_app
    @contextmanager
    def factory():
        with open_test(tmp_path, Model()) as agent:
            yield agent
    with TestClient(create_app(factory)) as client:
        response = client.post("/chat/stream", json={"session_id": "new", "message": "规划杭州"})
        assert "event: done" in response.text and "event: error" not in response.text
        messages = client.get("/sessions/new").json()["messages"]
        answer_id = messages[-1]["message_id"]
        assert client.get(f"/sessions/new/answers/{answer_id}/pdf").content.startswith(b"%PDF-")
        old = client.get("/sessions/new/trip").json()["plan"]
        invalid = {**PLAN, "other_cost": 99999}
        assert client.put("/sessions/new/trip", json=invalid).json()["status"] == "blocked"
        assert client.get("/sessions/new/trip").json()["plan"] == old
        assert client.get(f"/sessions/new/answers/{answer_id}/pdf").content.startswith(b"%PDF-")
