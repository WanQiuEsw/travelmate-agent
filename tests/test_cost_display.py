from copy import deepcopy
from datetime import datetime, timedelta, timezone

from travelmate.workflow import cost_label, total_cost_label, time_label
from travelmate.evidence import context_key
from test_workflow import PLAN, REQ


def test_unknown_zero_cost_is_not_presented_as_free_and_totals_stay_unknown():
    stop = {**deepcopy(PLAN['days'][0]['stops'][0]), 'cost': 0}
    assert cost_label(stop, REQ, {}) == '无法查询'
    assert total_cost_label([stop], REQ, {}) == '无法查询'
    assert time_label({'time_granularity': 'period'}, {'period': '上午'}) == '上午'


def test_estimates_show_partial_subtotal_and_advisory_window():
    stop = {**PLAN['days'][0]['stops'][0], 'cost_estimated': True}
    unknown = {**stop, 'cost': 0, 'cost_estimated': False}
    assert cost_label(stop, REQ, {}) == '约¥100.00（估算）'
    assert total_cost_label([stop, unknown], REQ, {}, 500, other_cost_estimated=True) == '约¥600.00（部分项目待核实）'
    assert time_label({'time_granularity': 'period'}, {
        'period': '上午', 'suggested_window': '09:00–11:00'}) == '上午 · 09:00–11:00（建议）'


def test_only_matched_current_price_is_displayed_including_a_verified_free_price():
    stop = {**deepcopy(PLAN['days'][0]['stops'][0]), 'cost': 0, 'fact_refs': {'cost': 'price:0'}}
    record = {'context': context_key(REQ), 'query_status': 'success', 'verification': 'matched',
              'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), 'kind': 'price', 'value': 0}
    evidence = {'price:0': record}
    assert cost_label(stop, REQ, evidence) == '¥0.00'
    assert total_cost_label([stop], REQ, evidence) == '¥0.00'
    assert total_cost_label([stop], REQ, evidence, other_cost=100) == '无法查询'
    for changes in ({'query_status': 'failed'}, {'verification': 'reference'}, {'kind': 'place'},
                    {'value': 5}, {'expires_at': '2000-01-01T00:00:00+00:00'}):
        assert cost_label(stop, REQ, {'price:0': {**record, **changes}}) == '无法查询'
