from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from travelmate.agent import open_agent
from travelmate.api import create_app
from travelmate.workflow import update_trip, submit_itinerary, Itinerary, save_workflow
from test_travelmate import BudgetModel

REQ = dict(mobility='每天10000步以内', origin='上海', destination='杭州', start_date='2026-12-01', days=1, travelers=2, budget=1000, budget_scope='total', budget_currency='CNY', budget_includes='全部费用')
PLAN = dict(days=[dict(date='2026-12-01', stops=[dict(place='西湖', city='杭州', start='09:00', end='11:00', travel_minutes=30, cost=100, notes='步行，时间估算', source='未核实')])], other_cost=500, cost_notes='全员住宿及往返交通估算', foods=[dict(name='片儿川', description='杭州面食，常以雪菜、笋片等搭配，点单前确认具体食材。', area='结合当日游览片区顺路用餐', tips='按忌口确认配料')])

def call(fn, state, **kwargs):
    runtime = SimpleNamespace(state={'workflow': state}, tool_call_id='test')
    return fn.func(runtime=runtime, **kwargs).update['workflow']


def test_collection_validation_and_limit():
    state = call(update_trip, {}, conditions={'destination': '杭州'})
    assert state['status'] == 'collecting' and 'budget' in state['missing']
    state = call(update_trip, state, conditions=REQ)
    assert state['status'] == 'researching'
    bad = Itinerary.model_validate({**PLAN, 'other_cost': 2000})
    for expected in ('adjusting', 'adjusting', 'blocked'):
        state = call(submit_itinerary, state, plan=bad)
        assert state['status'] == expected
    runtime = SimpleNamespace(state={'workflow': state}, tool_call_id='test')
    assert 'error' in submit_itinerary.func(plan=bad, runtime=runtime)
    state = call(update_trip, state, conditions={'budget': 3000})
    state = call(submit_itinerary, state, plan=bad)
    assert state['status'] == 'review' and state['attempts'] == 1


def test_time_city_date_checks():
    from travelmate.workflow import validate_plan
    import copy
    data = copy.deepcopy(PLAN)
    data['days'][0]['date'] = '2026-12-02'
    data['days'][0]['stops'][0].update(city='北京', end='08:00')
    issues, _ = validate_plan(REQ, data)
    assert len(issues) == 3


def test_followup_revises_without_manual_review():
    from langchain_core.messages import HumanMessage, AIMessage
    old = call(update_trip, {}, conditions=REQ)
    old = call(submit_itinerary, old, plan=Itinerary.model_validate(PLAN))
    runtime = SimpleNamespace(state={'workflow': old, 'messages': [
        HumanMessage(content='请把行程调整得更轻松'),
        AIMessage(content='', tool_calls=[{'name': 'submit_itinerary', 'args': {}, 'id': 'new'}])]},
        tool_call_id='new')
    updated = submit_itinerary.func(plan=Itinerary.model_validate(PLAN), runtime=runtime).update['workflow']
    assert updated['status'] == 'review' and updated['attempts'] == 1


def test_review_confirmation_pdf_and_restart(tmp_path):
    database = tmp_path / 'workflow.sqlite'
    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=database, knowledge=tmp_path) as agent:
            yield agent
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        state = call(update_trip, {}, conditions=REQ)
        state = call(submit_itinerary, state, plan=Itinerary.model_validate(PLAN))
        save_workflow(client.app.state.agent, 'alice', state)
        assert client.get('/sessions/bob/trip').json() == {}
        assert client.get('/sessions/alice/trip/pdf').status_code == 409
        assert client.post('/sessions/alice/trip/confirm', json={**PLAN, 'other_cost': 501}).status_code == 409
        assert client.post('/sessions/alice/trip/confirm', json=PLAN).status_code == 200
        response = client.get('/sessions/alice/trip/pdf')
        assert response.status_code == 200 and response.content.startswith(b'%PDF-')
        assert client.put('/sessions/alice/trip', json=PLAN).json()['status'] == 'review'
        assert client.get('/sessions/alice/trip/pdf').status_code == 409
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        assert client.get('/sessions/alice/trip').json()['status'] == 'review'


def test_map_failure_and_coordinates(monkeypatch):
    from travelmate.tools import search_places, search_route
    monkeypatch.delenv('AMAP_API_KEY', raising=False)
    assert 'error' in search_places.invoke({'keyword': '西湖', 'city': '杭州'})
    assert 'error' in search_route.invoke({'origin': '999,99', 'destination': '120,30'})


def test_real_workflow_tool_runtime(tmp_path):
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from travelmate.agent import chat
    from travelmate.workflow import get_workflow
    class PlanningModel(BudgetModel):
        def _generate(self, messages, **kwargs):
            last = messages[-1]
            if not isinstance(last, ToolMessage):
                message = AIMessage(content='', tool_calls=[dict(name='update_trip', args={'conditions': REQ}, id='req')])
            elif last.name == 'update_trip':
                message = AIMessage(content='', tool_calls=[dict(name='submit_itinerary', args={'plan': PLAN}, id='plan')])
            else:
                message = AIMessage(content='请审核行程')
            return ChatResult(generations=[ChatGeneration(message=message)])
    with open_agent(legacy_tool_loop=True, model=PlanningModel(), database=tmp_path / 'real.sqlite', knowledge=tmp_path) as agent:
        assert chat(agent, 'demo', '规划旅行') == '请审核行程'
        assert get_workflow(agent, 'demo')['status'] == 'review'


def test_optional_origin_date_and_transport_support_relative_days():
    from travelmate.workflow import validate_plan
    from travelmate.pdf_export import itinerary_pdf
    req = {key: value for key, value in REQ.items() if key not in ("origin", "start_date")}
    state = call(update_trip, {}, conditions={**req, "transport": "高铁"})
    assert state["status"] == "researching"
    assert state["requirements"]["start_date"] is None
    assert state["requirements"]["origin"] is None
    plan = {**PLAN, "days": [{**PLAN["days"][0], "date": None}]}
    assert validate_plan(state["requirements"], plan)[0] == []
    assert validate_plan(state["requirements"], PLAN)[0]
    state = call(submit_itinerary, state, plan=Itinerary.model_validate(plan))
    assert state["status"] == "review"
    assert itinerary_pdf(state).startswith(b"%PDF-")
    revised = call(update_trip, state, conditions={"origin": "上海", "start_date": "2026-12-01"})
    assert validate_plan(revised["requirements"], PLAN)[0] == []
