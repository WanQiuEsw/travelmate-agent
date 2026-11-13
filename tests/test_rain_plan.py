from copy import deepcopy
from datetime import datetime, timezone

import pytest

from travelmate.guide import make_guide, render_guide
from travelmate.workflow import Itinerary, period_plan, validate_plan
from travelmate.evidence import validate_evidence
from test_workflow import PLAN, REQ


def rain_plan():
    plan = deepcopy(PLAN)
    plan['days'][0]['rain_stops'] = [{**plan['days'][0]['stops'][0], 'place': '室内展馆',
                                    'notes': '提前预约，保留午餐与返程安排', 'cost_estimated': True}]
    plan['days'][0]['rain_note'] = '将湖边漫步替换为室内参观；交通与费用按卡片估算。'
    return plan


def test_rain_route_survives_snapshot_and_keeps_original_and_budget():
    plan = rain_plan()
    plan.update(lodging=['围绕当天路线选择地铁附近住宿'], pitfalls=[{'level': '注意', 'text': '室内展馆需预约'}],
                verify_items=[{'item': '预约展馆', 'channel': '场馆官方公众号'}])
    guide = make_guide(dict(version=1, plan=plan, requirements=REQ,
                           saved_at=datetime.now(timezone.utc).isoformat()), {})
    saved = deepcopy(guide)
    html = render_guide(guide)
    daily = html.split('id="panel-days"')[1].split('id="panel-lodging"')[0]
    assert '西湖' in daily and '室内展馆' in daily and plan['days'][0]['rain_note'] in daily
    assert '原定行程' in daily and '雨天方案' in daily
    assert '待核实清单' not in html and '出行待办' in html and '预约展馆' in html
    assert '方案详情与依据' in html
    assert guide == saved
    assert len(guide['result']['ledger']) == 2  # 备选费用不能与原路线重复相加。


def test_rain_route_uses_original_validation_and_timing_conversion():
    plan = rain_plan()
    assert validate_plan(REQ, plan)[0] == []
    assert period_plan(plan)['days'][0]['rain_stops'][0]['start'] is None
    plan['days'][0]['rain_stops'][0].update(city='北京', end='08:00', cost=2000)
    issues, _ = validate_plan(REQ, plan)
    assert all(any(word in issue for issue in issues) for word in ('雨天方案', '城市', '时间', '超过预算'))
    with pytest.raises(ValueError):
        Itinerary.model_validate({**plan, 'days': [{**plan['days'][0], 'rain_stops': [
            {**plan['days'][0]['rain_stops'][0], 'start': None}]}]})
    issues, _ = validate_plan({**REQ, 'return_deadline': '10:00'}, rain_plan())
    assert any('雨天方案' in issue and '时限' in issue for issue in issues)


def test_rain_route_does_not_bypass_evidence_or_mixed_day_budget():
    plan = rain_plan()
    plan['days'][0]['rain_stops'][0]['fact_refs'] = {'place': 'missing'}
    assert any('室内展馆' in issue for issue in validate_evidence(REQ, plan, {}))
    plan['days'].append(deepcopy(plan['days'][0]))
    plan['days'][1]['date'] = '2026-12-02'
    plan['days'][0]['stops'][0]['cost'] = 300
    plan['days'][1]['rain_stops'][0]['cost'] = 300
    issues, _ = validate_plan({**REQ, 'days': 2}, plan)
    assert any('按天切换' in issue for issue in issues)


def test_old_days_offer_honest_empty_state_and_separate_day_controls():
    plan = deepcopy(PLAN)
    plan['days'].append(deepcopy(plan['days'][0]))
    guide = make_guide(dict(version=1, plan=plan, requirements={**REQ, 'days': 2}), {})
    html = render_guide(guide)
    assert html.count('本版尚无完整雨天路线') == 2
    assert 'name="day-plan-1"' in html and 'name="day-plan-2"' in html
