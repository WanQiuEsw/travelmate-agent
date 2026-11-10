from copy import deepcopy
from datetime import datetime, timezone
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import HumanMessage
from travelmate.agent import open_agent, chat, stream_chat, conversation
from travelmate.workflow import get_workflow
from test_workflow import REQ, PLAN
import json
from threading import Barrier
from langchain.tools import tool
import pytest


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
            if schema.__name__ == "ReviewReport":
                return schema.model_validate({"issues": []})
            if self.fail:
                raise RuntimeError("private-key")
            return schema.model_validate(self.plans.pop(0) if len(self.plans) > 1 else self.plans[0])
        return RunnableLambda(run)


def open_test(tmp_path, model):
    return open_agent(model=model, database=tmp_path / "graph.sqlite", knowledge=tmp_path)


@pytest.mark.parametrize('mode', ['flight', 'ferry'])
def test_flight_and_ferry_plans_can_be_validated_saved_and_presented(tmp_path, monkeypatch, mode):
    from travelmate.guide import get_version, render_guide
    monkeypatch.delenv('AMAP_API_KEY', raising=False)
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'][0]['transport_mode'] = mode
    with open_test(tmp_path, Model(plans=[plan])) as agent:
        events = list(stream_chat(agent, 'transport', '规划'))
        state = get_workflow(agent, 'transport')
        assert state['status'] == 'review'
        guide = get_version(state, 1)
        assert ('飞机' if mode == 'flight' else '轮渡') in render_guide(guide, '/guide.pdf')
        assert events[-1][0] == 'done' and events[-1][1]['plan_version'] == 1


@pytest.mark.parametrize('always_invalid', [False, True])
def test_schema_format_repair_is_bounded_and_streams_progress(tmp_path, monkeypatch, always_invalid):
    monkeypatch.delenv('AMAP_API_KEY', raising=False)

    class InvalidFormatModel(Model):
        def with_structured_output(self, schema, **kwargs):
            if schema.__name__ != 'Itinerary':
                return super().with_structured_output(schema, **kwargs)
            def run(messages):
                self.calls.append('Itinerary')
                plan = deepcopy(PLAN)
                if self.calls.count('Itinerary') == 1 or always_invalid:
                    plan['days'][0]['stops'][0]['transport_mode'] = 'unsupported-mode'
                else:
                    assert 'transport_mode' in messages[-1].content
                return schema.model_validate(plan)
            return RunnableLambda(run)

    model = InvalidFormatModel()
    with open_test(tmp_path, model) as agent:
        events = list(stream_chat(agent, 'format', '规划'))
        assert model.calls.count('Itinerary') == 2
        assert sum(event == 'status' and '正在修正回答的数据格式' in data['text'] for event, data in events) == 1
        assert get_workflow(agent, 'format')['status'] == ('failed' if always_invalid else 'review')
        kind, payload = events[-1]
        assert kind == ('error' if always_invalid else 'done')
        assert 'unsupported-mode' not in (payload.get('text') or payload['answer'])


@pytest.mark.parametrize('always_empty', [False, True])
def test_preset_intake_retries_when_the_model_omits_the_structured_result(tmp_path, always_empty):
    class EmptyIntakeModel(Model):
        def with_structured_output(self, schema, **kwargs):
            assert schema.__name__ == 'Intake'

            def run(messages):
                self.calls.append(schema.__name__)
                if len(self.calls) == 1 or always_empty:
                    return None
                assert '未返回结构化结果' in messages[-1].content
                return schema.model_validate({'intent': 'plan', 'conditions': {
                    'origin': '厦门', 'destination': '北京', 'days': 3, 'travelers': 2,
                    'budget': 3000, 'budget_scope': 'total', 'budget_currency': 'CNY', 'transport': '高铁',
                }})

            return RunnableLambda(run)

    model = EmptyIntakeModel()
    preset = '我们【2人】从【厦门】出发到【北京】玩【3天】，总预算【3000元】，交通方式【高铁】，请帮我们规划行程。'
    with open_test(tmp_path, model) as agent:
        events = list(stream_chat(agent, 'preset', preset))
        message = conversation(agent, 'preset')['messages'][-1]
        assert model.calls == ['Intake', 'Intake']
        assert any('正在修正回答的数据格式' in data['text'] for kind, data in events if kind == 'status')
        kind, payload = events[-1]
        if always_empty:
            assert kind == 'error' and payload['generation_failed'] and payload['text'] == message['content']
            assert message['generation_failed'] and 'plan_version' not in message
        else:
            assert kind == 'done' and not message.get('generation_failed')
            assert [field['key'] for field in payload['interaction']['fields']] == ['budget_includes']


def test_real_evidence_ids_reach_model_and_places_query_concurrently(tmp_path, monkeypatch):
    import travelmate.agent as agent_module
    barrier = Barrier(4)

    @tool
    def search_places(keyword: str, city: str) -> dict:
        """Return a matched place without network access."""
        barrier.wait(timeout=5)
        return {'results': [{'name': keyword, 'location': '120.1,30.2'}]}

    monkeypatch.setattr(agent_module, 'search_places', search_places)

    class EvidenceModel(Model):
        def with_structured_output(self, schema, **kwargs):
            if schema.__name__ not in ('Areas', 'Itinerary'):
                return super().with_structured_output(schema, **kwargs)

            def run(messages):
                self.calls.append(schema.__name__)
                if schema.__name__ == 'Areas':
                    return schema.model_validate({'areas': [{'name': '杭州', 'places': ['西湖', '灵隐寺', '断桥', '雷峰塔']}]})
                data = json.loads(messages[-1].content)
                evidence = data['evidence']
                assert len(evidence) >= 4
                ref = next(key for key, record in evidence.items() if record['value'] == '西湖')
                assert evidence[ref]['id'] == ref and len(ref.split(':')[0]) == 32
                plan = deepcopy(PLAN)
                plan['days'][0]['stops'][0]['fact_refs'] = {'place': ref}
                return schema.model_validate(plan)
            return RunnableLambda(run)

    model = EvidenceModel()
    with open_test(tmp_path, model) as agent:
        answer = chat(agent, 'evidence', '规划杭州')
        state = get_workflow(agent, 'evidence')
        assert state['status'] == 'review' and state['attempts'] == 1
        ref = state['plan']['days'][0]['stops'][0]['fact_refs']['place']
        assert ref in state['evidence']
        assert '核实情况' not in answer and ref not in answer
        assert model.calls.count('Itinerary') == model.calls.count('ReviewReport') == 1


def test_required_order_versions_and_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    with open_test(tmp_path, Model()) as agent:
        text = chat(agent, "trip", "安排杭州一日游")
        state = get_workflow(agent, "trip")
        assert state["status"] == "review" and state["version"] == 1
        assert [row["node"] for row in state["trace"]] == ["requirements", "ready", "research", "organize_places", "verify_places", "generate", "check", "quality_review", "save_version", "present"]
        assert state["versions"][0]["plan"] == state["plan"]
        assert "1天旅行攻略已整理完成" in text
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
        assert "上一版可用攻略已保留" in answer
        assert conversation(agent, "trip")["messages"][-1]["plan_version"] == 1


def test_unverifiable_refs_are_cleaned_instead_of_regenerating():
    from travelmate.evidence import normalize, validate_evidence
    from travelmate.planner import clean_refs
    evidence = normalize('search_places', {'keyword': '西湖', 'city': '杭州'},
                         {'results': [{'name': '西湖', 'location': '120.1,30.2'}]}, 'map', REQ)
    ref = next(iter(evidence))
    candidate = deepcopy(PLAN)
    stop = candidate['days'][0]['stops'][0]
    stop['place'] = '西湖（断桥入口）'
    stop['fact_refs'] = {'place': ref, 'cost': ref, 'opening_hours': ref}
    assert clean_refs(candidate, evidence, REQ) is True
    assert stop['place'] == '西湖' and stop['fact_refs'] == {'place': ref}
    assert validate_evidence(REQ, candidate, evidence) == []


def test_slow_run_skips_remaining_checks_and_tells_the_user(tmp_path, monkeypatch):
    import travelmate.planner as planner
    monkeypatch.setattr(planner, 'run_deadline', lambda workflow: datetime(2000, 1, 1, tzinfo=timezone.utc))
    model = Model(plans=[{**PLAN, 'other_cost': 90000}])
    with open_test(tmp_path, model) as agent:
        answer = chat(agent, 'slow', '规划')
        state = get_workflow(agent, 'slow')
    assert state['status'] == 'review' and state['attempts'] == 1
    assert model.calls.count('Itinerary') == 1
    assert '跳过部分自动复核' in answer


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
    model = Model(intake={"intent": "question", "direction": "可以按兴趣选择片区。" * 8})
    with open_test(tmp_path, model) as agent:
        events = list(stream_chat(agent, "stream", "怎么选景点"))
        assert events[-1][0] == "done"
        assert any(event == "status" for event, _ in events)
        tokens = [data['text'] for event, data in events if event == 'token']
        assert len(tokens) > 1 and all(tokens)
        assert ''.join(tokens) == events[-1][1]['answer']


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
    with TestClient(create_app(factory, auth_enabled=False)) as client:
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
