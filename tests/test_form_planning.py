"""Form requests keep user conditions exact and reuse versioned planning."""
from contextlib import contextmanager
from copy import deepcopy
import json

from fastapi.testclient import TestClient

from travelmate.api import create_app
from travelmate.agent import stream_chat
from travelmate.workflow import get_workflow
from test_planner import Model, open_test
from test_workflow import REQ, PLAN


def form_conditions(**changes):
    return {**REQ, "start_date": None, **changes}


def relative_plan():
    plan = deepcopy(PLAN)
    plan["days"][0]["date"] = None
    return plan


def test_form_skips_intake_extraction_and_preserves_each_version(tmp_path):
    model = Model(plans=[relative_plan()])
    with open_test(tmp_path, model) as agent:
        first = list(stream_chat(agent, "form", "摘要不包含预算", planning_requirements=form_conditions()))
        assert first[-1][1]["plan_version"] == 1
        assert "Intake" not in model.calls
        state = get_workflow(agent, "form")
        assert state["requirements"]["start_date"] is None
        assert state["requirements"]["budget"] == 1000
        original = deepcopy(state["versions"][0])
        second = list(stream_chat(agent, "form", "修改预算", planning_requirements=form_conditions(budget=2000)))
        assert second[-1][1]["plan_version"] == 2
        state = get_workflow(agent, "form")
        assert state["versions"][0] == original
        assert state["versions"][1]["requirements"]["budget"] == 2000
        starts = [data["stage"] for event, data in first if event == "status" and data.get("state") == "running"]
        assert starts == ["intake", "research", "organize", "verify_places", "generate", "check", "review", "save", "present"]


def test_blocked_form_revision_does_not_report_old_version_as_new_success(tmp_path):
    model = Model(plans=[relative_plan()])
    with open_test(tmp_path, model) as agent:
        list(stream_chat(agent, "form", "生成", planning_requirements=form_conditions()))
        original = deepcopy(get_workflow(agent, "form")["versions"][0])
        events = list(stream_chat(agent, "form", "预算改成一元", planning_requirements=form_conditions(budget=1)))
        assert events[-1][0] == "error"
        assert events[-1][1]["generation_failed"] is True
        state = get_workflow(agent, "form")
        assert state["versions"] == [original]
        assert state["plan"] == original["plan"]


def test_screenshot_conditions_accept_departure_transport_and_unverified_rain_places(tmp_path):
    plan = relative_plan()
    plan['days'] = [deepcopy(plan['days'][0]) for _ in range(3)]
    plan['days'][0]['stops'].insert(0, {
        **deepcopy(plan['days'][0]['stops'][0]), 'place': '厦门北站出发（车次待核实）',
        'city': '厦门', 'transport_mode': 'rail', 'activities': ['other'], 'cost': 0,
    })
    for number, day in enumerate(plan['days'], 27):
        day['date'] = f'2026-11-{number}'
    plan['days'][-1]['rain_stops'] = [{**deepcopy(plan['days'][-1]['stops'][0]),
                                     'place': '灵隐飞来峰景区', 'fact_refs': {'place': 'wrong-place'}}]
    model = Model(plans=[plan])
    with open_test(tmp_path, model) as agent:
        events = list(stream_chat(agent, 'screenshot', '生成攻略', planning_requirements=form_conditions(
            origin='厦门', start_date='2026-11-27', days=3, budget=3000,
            preferences='美食寻味；旅行节奏：轻松；', dietary='只能吃微辣')))
        assert events[-1][0] == 'done' and events[-1][1]['plan_version'] == 1
        state = get_workflow(agent, 'screenshot')
        assert state['requirements']['dietary'] == '只能吃微辣'
        assert state['plan']['days'][0]['stops'][0]['city'] == '厦门'
        assert state['plan']['days'][-1]['rain_stops'][0]['fact_refs'] == {}
        assert model.calls.count('Itinerary') == 1


def test_generation_failure_names_the_stage_without_changing_conditions(tmp_path):
    with open_test(tmp_path, Model(fail=True)) as agent:
        events = list(stream_chat(agent, 'failed-form', '生成攻略', planning_requirements=form_conditions()))
        assert events[-1][0] == 'error'
        assert '行程生成阶段未能完成' in events[-1][1]['text']
        assert '旅行条件已保留' in events[-1][1]['text']
        assert 'private-key' not in events[-1][1]['text']
        assert get_workflow(agent, 'failed-form')['requirements']['budget'] == 1000


def test_form_api_validates_before_running_and_renders_adjustment_link(tmp_path):
    model = Model(plans=[relative_plan()])

    @contextmanager
    def factory():
        with open_test(tmp_path, model) as agent:
            yield agent

    with TestClient(create_app(factory, auth_enabled=False)) as client:
        payload = {"session_id": "form", "message": "生成攻略", "planning_requirements": form_conditions()}
        for changes in ({"budget": -1}, {"budget": "NaN"}, {"days": 31}, {"budget_currency": "USD"}, {"destination": "  "},
                        {"destination": "上海"}, {"start_date": "2020-01-01"}, {"travelers": 0}):
            invalid = deepcopy(payload)
            invalid["planning_requirements"].update(changes)
            assert client.post("/chat/stream", json=invalid).status_code == 422
        mixed = {**payload, "interaction_response": {"id": "a" * 32, "answers": {"days": 1}}}
        assert client.post("/chat/stream", json=mixed).status_code == 422
        assert not model.calls
        response = client.post("/chat/stream", json=payload)
        assert response.status_code == 200
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["plan_version"] == 1
        page = client.get("/sessions/form/plans/1")
        assert page.status_code == 200
        assert "修改条件重新规划" in page.text
        assert "/?session=form&amp;edit=1" in page.text
        assert client.get("/sessions/form/trip").json()["requirements"]["budget_scope"] == "total"
