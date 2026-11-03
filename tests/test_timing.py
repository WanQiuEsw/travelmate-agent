from copy import deepcopy

import pytest
from pydantic import ValidationError

from travelmate.workflow import Itinerary, adapt_timing, period_plan, validate_plan
from travelmate.review import timing_warnings, blocking_messages
from travelmate.guide import make_guide, render_guide
from travelmate.pdf_export import itinerary_pdf, guide_pdf
from test_workflow import REQ, PLAN
from test_review import PROBLEM, ReviewedModel
from test_planner import open_test
from travelmate.agent import stream_chat
from travelmate.workflow import get_workflow


def test_unknown_transport_and_conflicting_estimates_become_periods():
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'].append({**plan['days'][0]['stops'][0], 'start': '10:30', 'end': '12:00'})
    assert any('时间重叠' in x for x in validate_plan(REQ, plan)[0])
    coarse = adapt_timing(REQ, plan, {})
    assert coarse['time_granularity'] == 'period'
    assert all(s['start'] is None and s['end'] is None for s in coarse['days'][0]['stops'])
    assert validate_plan(REQ, coarse)[0] == []
    assert plan['days'][0]['stops'][0]['start'] == '09:00'


def test_precise_timing_remains_available_when_transport_is_verified():
    from travelmate.evidence import normalize
    plan = deepcopy(PLAN)
    evidence = normalize('search_route', {}, {'paths': [{'duration': 1800}]}, 'route', REQ)
    plan['days'][0]['stops'][0].update(transport_mode='driving', fact_refs={'travel_minutes': 'route:0'})
    assert adapt_timing(REQ, plan, evidence) == plan
    assert validate_plan(REQ, plan)[0] == []


def test_period_plan_does_not_require_fabricated_clock_times_or_travel_minutes():
    coarse = period_plan(PLAN)
    stop = coarse['days'][0]['stops'][0]
    stop.pop('start')
    stop.pop('end')
    stop.pop('travel_minutes')
    stop['travel_estimate'] = '约30至60分钟，包含候车缓冲'
    assert not validate_plan(REQ, coarse)[0]
    assert Itinerary.model_validate(coarse).days[0].stops[0].travel_minutes is None
    invalid = deepcopy(coarse)
    invalid['days'][0]['stops'][0]['start'] = '09:00'
    with pytest.raises(ValidationError):
        Itinerary.model_validate(invalid)


def test_hard_departure_and_budget_are_not_erased_by_coarse_timing():
    req = {**REQ, 'bookings': [{'description': '已订返程车票', 'day': 1, 'departure': '10:00'}]}
    assert adapt_timing(req, PLAN, {}) == PLAN
    assert any('时限' in x for x in validate_plan(req, PLAN)[0])
    coarse = period_plan(PLAN)
    coarse['days'][0]['stops'][0]['period'] = '下午'
    assert any('时限' in x for x in validate_plan(req, coarse)[0])
    assert any('时限' in x for x in validate_plan({**REQ, 'return_deadline': '12:00'}, coarse)[0])
    assert any('预算' in x for x in validate_plan(REQ, {**coarse, 'other_cost': 99999})[0])
    assert any('超出' in x for x in validate_plan(REQ, {**coarse, 'other_cost': 99999})[0])


def test_timing_warnings_keep_actual_user_time_anchors_and_program_errors():
    issue = {**PROBLEM, 'dimension': 'space_time', 'time_basis': 'booking'}
    coarse = period_plan(PLAN)
    assert timing_warnings([issue], REQ, coarse)[0]['blocking'] is False
    booked = {**REQ, 'bookings': [{'description': '返程车票', 'day': 1, 'departure': '10:00'}]}
    assert timing_warnings([issue], booked, coarse)[0]['blocking'] is True
    program = {**issue, 'rule_id': 'PROGRAM-1', 'time_basis': 'estimate'}
    assert timing_warnings([program], REQ, coarse)[0]['blocking'] is True
    assert timing_warnings([PROBLEM], REQ, coarse)[0]['blocking'] is True


def test_explicit_nonblocking_review_does_not_trigger_regeneration():
    assert blocking_messages([{**PROBLEM, 'blocking': False}]) == []
    assert len(blocking_messages([PROBLEM])) == 1


@pytest.mark.parametrize('dimension,blocking', [('space_time', True), ('facts', False)])
def test_repeated_estimated_time_conflicts_deliver_without_a_generation_loop(tmp_path, monkeypatch, dimension, blocking):
    monkeypatch.delenv('AMAP_API_KEY', raising=False)
    issue = {**PROBLEM, 'dimension': dimension, 'blocking': blocking, 'basis': '交通耗时尚不确定，不能保证准时到达',
             'suggestion': '按实际到达时间调整上午活动顺序'}
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'].append({**plan['days'][0]['stops'][0], 'start': '10:30', 'end': '12:00'})
    model = ReviewedModel([[issue]], plans=[plan])
    with open_test(tmp_path, model) as agent:
        events = list(stream_chat(agent, 'coarse', '时间不确定，给我大致行程即可'))
        state = get_workflow(agent, 'coarse')
        assert state['status'] == 'review' and state['attempts'] == 1
        assert model.calls.count('Itinerary') == model.calls.count('ReviewReport') == 1
        assert state['plan']['time_granularity'] == 'period'
        answer = events[-1][1]['answer']
        assert events[-1][0] == 'done'
        assert '上午' in answer and '可按实际到达时间' in answer
        assert '09:00' not in answer and '10:30' not in answer
        assert '未通过检查' not in answer


def test_period_guide_and_both_pdf_exports_share_estimates_and_keep_deadline():
    coarse = period_plan(PLAN)
    req = {**REQ, 'return_deadline': '18:00'}
    version = {'version': 1, 'requirements': req, 'plan': coarse}
    guide = make_guide(version, {})
    html = render_guide(guide, '/download')
    assert '上午' in html and '18:00' in html
    assert '09:00' not in html and '11:00' not in html and 'None' not in html
    assert '细化' in html
    assert guide_pdf(guide).startswith(b'%PDF-')
    assert itinerary_pdf({'requirements': req, 'plan': coarse, 'total': 600}).startswith(b'%PDF-')


def test_period_plan_can_be_edited_confirmed_and_exported_through_existing_api(tmp_path):
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from travelmate.agent import open_agent
    from travelmate.api import create_app
    from travelmate.workflow import update_trip, submit_itinerary, save_workflow
    from test_workflow import call
    from test_travelmate import BudgetModel

    coarse = period_plan(PLAN)

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=tmp_path / 'period.sqlite', knowledge=tmp_path) as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        state = call(update_trip, {}, conditions=REQ)
        state = call(submit_itinerary, state, plan=Itinerary.model_validate(coarse))
        save_workflow(client.app.state.agent, 'period', state)
        edited = client.put('/sessions/period/trip', json=coarse)
        assert edited.status_code == 200 and edited.json()['status'] == 'review'
        assert client.post('/sessions/period/trip/confirm', json=coarse).status_code == 200
        assert client.get('/sessions/period/trip/pdf').content.startswith(b'%PDF-')
    with TestClient(create_app(factory)) as client:
        state = client.get('/sessions/period/trip').json()
        assert state['status'] == 'confirmed' and state['plan']['time_granularity'] == 'period'
