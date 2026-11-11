from copy import deepcopy
from datetime import datetime, timezone
from travelmate.guide import make_guide, render_guide
from travelmate.result import coordinates
from test_workflow import PLAN, REQ


def test_result_sections_and_historical_snapshot():
    guide = make_guide(dict(version=1, plan=deepcopy(PLAN), requirements=REQ,
                            saved_at=datetime.now(timezone.utc).isoformat()), {})
    html = render_guide(guide, '/plans/1/pdf')
    for name in ('overview', 'budget', 'map', 'days', 'weather'):
        assert f'id="panel-{name}"' in html
        assert f'href="#panel-{name}"' in html
    assert '知识图谱' not in html
    assert 'href="#day-1"' in html and 'id="day-1"' in html
    assert '不代表真实导航路线' in html
    assert '人均已列费用' in html
    assert '<script type="module">' in html
    guide.pop('result')
    assert '历史方案未保存可计算的费用分项' in render_guide(guide)


def test_coordinates_reject_invalid_values():
    assert coordinates('120.1,30.2') == (120.1, 30.2)
    for value in (None, 'nan,30', 'inf,0', '181,30', '120,91', '<script>', '1,2,3'):
        assert coordinates(value) is None

def render_sample(req=None, plan=None):
    return render_guide(make_guide(dict(version=1, plan=deepcopy(plan or PLAN),
                                       requirements=req or REQ,
                                       saved_at=datetime.now(timezone.utc).isoformat()), {}), '/plans/1/pdf')


def test_missing_date_has_explicit_weather_empty_state_for_new_and_old_versions():
    req = {**REQ, 'start_date': None}
    plan = deepcopy(PLAN)
    plan['days'][0]['date'] = None
    guide = make_guide(dict(version=1, plan=plan, requirements=req,
                            saved_at=datetime.now(timezone.utc).isoformat()), {})
    for historical in (False, True):
        if historical:
            guide.pop('result')
        weather = render_guide(guide).split('aria-label="天气信息">')[1]
        assert '尚未选择出行日期' in weather
        assert 'weather-grid' not in weather
        assert '预报查询时间' not in weather
    assert '尚未选择出行日期' not in render_sample()


def test_carousel_has_wrapping_controls_and_daily_navigation():
    plan = deepcopy(PLAN)
    plan['days'].append(deepcopy(plan['days'][0]))
    html = render_sample(plan=plan)
    assert 'name="highlight" id="highlight-1"' in html
    assert 'name="highlight" id="highlight-2"' in html
    assert 'slide-1' in html and 'slide-2' in html
    assert 'data-carousel-target="highlight-2" aria-label="上一个景点"' in html
    assert 'data-carousel-target="highlight-1" aria-label="下一个景点"' in html
    assert 'aria-label="选择行程日"' in html
    assert 'href="#day-2"' in html
    budget = html.split('aria-label="预算明细">')[1].split('id="panel-map"')[0]
    assert '逐项费用' in budget and '西湖' in budget and '预算口径' in budget
    daily = html.split('aria-label="每日行程">')[1].split('id="panel-weather"')[0]
    for value in ('交通与已订安排', '住哪里更顺路', '当地特色美食', '下雨、排队或约不上时怎么换'):
        assert value in daily


def test_budget_ledger_counts_other_cost_once_and_keeps_unknown_amounts():
    plan = deepcopy(PLAN)
    plan['days'][0]['stops'][0].update(cost_category='景点门票', cost_estimated=True, cost=0.1)
    plan['other_cost_estimated'] = True
    plan['other_cost'] = 0.2
    guide = make_guide(dict(version=1, plan=plan, requirements=REQ,
                            saved_at=datetime.now(timezone.utc).isoformat()), {})
    assert [r['amount'] for r in guide['result']['ledger']] == [0.1, 0.2]
    html = render_guide(guide)
    assert 'data-total>¥0.30' in html
    assert 'data-category-total="景点门票">¥0.10' in html
    assert 'data-category-total="酒店住宿">未单列' in html
    plan['days'][0]['stops'][0]['cost_estimated'] = False
    guide = make_guide(dict(version=1, plan=plan, requirements=REQ,
                            saved_at=datetime.now(timezone.utc).isoformat()), {})
    assert guide['result']['ledger'][0]['amount'] is None
    assert 'data-total>¥0.20' in render_guide(guide)


def test_budget_browser_calculation_filter_sort_exclude_and_reset():
    import subprocess
    from travelmate.result import RESULT_JS
    stub = r'''
const assert = require('node:assert/strict');
function row(category, value, order) {
 const input = {value, defaultValue:value, validity:{valid:true}}, check = {checked:true};
 return {dataset:{category,order:String(order)},input,check,querySelector:s=>s.includes('number')?input:check};
}
const rows = [row('景点门票','0.10',0),row('综合费用','0.20',1),row('餐饮费用','',2)];
const total = {}, person = {}, notice = {}, filter = {value:''}, sort = {value:'original'};
const categories = ['景点门票','综合费用','餐饮费用'].map(c=>({dataset:{categoryTotal:c}}));
let update, reset;
const body = {append:()=>{}};
const nodes = {'[data-total]':total,'[data-person]':person,'[data-budget-notice]':notice,'[data-budget-filter]':filter,'[data-budget-sort]':sort,'[data-ledger]':body,'[data-budget-reset]':{addEventListener:(_,fn)=>reset=fn}};
const fakeWorkspace = {dataset:{travelers:'2'},querySelector:s=>nodes[s],querySelectorAll:s=>s.includes('tr')?rows:categories,addEventListener:(_,fn)=>update=fn};
global.document = {querySelector:()=>fakeWorkspace,querySelectorAll:()=>[]};
'''
    checks = r'''
update();assert.equal(total.textContent,'¥0.30');assert.equal(person.textContent,'¥0.15');
filter.value='景点门票';update();assert.equal(total.textContent,'¥0.30');assert.equal(rows[1].hidden,true);
rows[1].check.checked=false;update();assert.equal(total.textContent,'¥0.10');
rows[0].input.value='1e2';update();assert.equal(total.textContent,'待核实');
rows[0].input.value='12.34';sort.value='desc';update();assert.equal(total.textContent,'¥12.34');
reset();assert.equal(total.textContent,'¥0.30');assert.equal(filter.value,'');
'''
    subprocess.run(['node', '-e', stub + RESULT_JS + checks], check=True, capture_output=True, text=True)


def test_carousel_controls_and_compact_expense_description():
    from travelmate.result import budget_panel, RESULT_CSS
    from html import escape
    description = 'other_cost 600 元 = 住宿；' + '费用构成与估算依据。' * 30 + '<script>alert(1)</script>'
    html = budget_panel({'travelers': 2, 'ledger': [{'category': '综合费用', 'day': None,
                        'name': description, 'amount': 600, 'status': '估算'}]}, [], escape)
    assert '<td>其他综合费用<details class="expense-explanation">' in html
    assert '<summary>费用说明</summary>' in html
    assert 'other_cost' not in html and '&lt;script&gt;' in html
    assert 'data-total>¥600.00' in html
    assert 'clip-path:inset(50%)' in RESULT_CSS
    assert '.carousel-controls button:focus-visible' in RESULT_CSS
