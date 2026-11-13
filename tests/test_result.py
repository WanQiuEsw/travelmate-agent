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
        assert value not in daily
        assert value in html.split('id="panel-tips"')[1]


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
let moves=0;
const body = {append(row) { moves++; rows.splice(rows.indexOf(row),1); rows.push(row); }};
function row(category, value, order) {
 const input = {value, defaultValue:value, validity:{valid:true}}, check = {checked:Boolean(value),defaultChecked:Boolean(value)};
 return {parentElement:body,dataset:{category,order:String(order)},input,check,querySelector:s=>s.includes('number')?input:check};
}
const rows = [row('景点门票','0.10',0),row('综合费用','0.20',1),row('餐饮费用','',2)];
const total = {}, person = {}, notice = {}, filter = {value:''}, sort = {value:'original'};
const categories = ['景点门票','综合费用','餐饮费用'].map(c=>({dataset:{categoryTotal:c}}));
const balance={}, barLabel={}, bar={style:{},querySelector:()=>barLabel}, pending={};
const limitInput={value:'3.00',defaultValue:'3.00',validity:{valid:true}};
const segmentLabel={}, segment={dataset:{segment:'景点门票'},style:{},querySelector:()=>segmentLabel};
const events={};
let update, reset;
const nodes = {'[data-budget-limit]':limitInput,'[data-total]':total,'[data-person]':person,'[data-unknown]':notice,'[data-budget-filter]':filter,'[data-budget-sort]':sort,'[data-balance]':balance,'[data-balance-bar]':bar,'.budget-pending h3':pending,'[data-budget-reset]':{addEventListener:(_,fn)=>reset=fn}};
const fakeWorkspace = {dataset:{travelers:'2',limit:'300'},querySelector:s=>nodes[s],querySelectorAll:s=>s.includes('tr[')?rows:s==='[data-ledger]'?[body]:s.includes('category-total')?categories:s==='[data-segment]'?[segment]:[],addEventListener:(name,fn)=>{events[name]=fn;if(name==='change')update=fn;}};
global.document = {querySelector:()=>fakeWorkspace,querySelectorAll:()=>[]};
'''
    checks = r'''
update();assert.equal(total.textContent,'¥0.30');assert.equal(person.textContent,'¥0.15');assert.equal(balance.textContent,'¥2.70');
filter.value='景点门票';update();assert.equal(total.textContent,'¥0.30');assert.equal(rows.find(r=>r.dataset.category==='综合费用').hidden,true);
const other=rows.find(r=>r.dataset.category==='综合费用'), ticket=rows.find(r=>r.dataset.category==='景点门票'), unknown=rows.find(r=>r.dataset.category==='餐饮费用');
other.check.checked=false;update();assert.equal(total.textContent,'¥0.10');
ticket.input.value='1e2';update();assert.equal(total.textContent,'待核实');
ticket.input.value='12.34';sort.value='desc';update();assert.equal(total.textContent,'¥12.34');assert.equal(balance.textContent,'¥-9.34');assert.equal(rows[0],ticket);
unknown.input.value='10.00';unknown.check.checked=true;update();assert.equal(total.textContent,'¥22.34');assert.equal(notice.textContent,'0 项待核实');
const beforeMoves=moves;
ticket.input.value='2.00';events.input({target:{matches:()=>true}});
assert.equal(total.textContent,'¥12.00');assert.equal(moves,beforeMoves);assert.equal(segment.style.flexGrow,200);assert.equal(segmentLabel.textContent,'¥2.00');
limitInput.value='20.00';events.input({target:{matches:()=>true}});
assert.equal(balance.textContent,'¥8.00');assert.equal(bar.style.flexGrow,800);assert.equal(barLabel.textContent,'¥8.00');
limitInput.value='';events.input({target:{matches:()=>true}});assert.equal(balance.textContent,'待确认');
reset();assert.equal(limitInput.value,'3.00');assert.equal(total.textContent,'¥0.30');assert.equal(filter.value,'');assert.equal(unknown.check.checked,false);assert.equal(notice.textContent,'1 项待核实');
'''
    subprocess.run(['node', '-e', stub + RESULT_JS + checks], check=True, capture_output=True, text=True)


def test_carousel_controls_and_compact_expense_description():
    from travelmate.result import budget_panel, RESULT_CSS
    from html import escape
    description = 'other_cost 600 元 = 住宿；' + '费用构成与估算依据。' * 30 + '<script>alert(1)</script>'
    html = budget_panel({'travelers': 2, 'ledger': [{'category': '综合费用', 'day': None,
                        'name': description, 'amount': 600, 'status': '估算'}]}, [], escape)
    assert '<td>其他综合费用<small>估算</small>' in html
    assert '<details class="expense-explanation">' in html
    assert '<summary>费用说明</summary>' in html
    assert 'other_cost' not in html and '&lt;script&gt;' in html
    assert 'data-total>¥600.00' in html
    assert 'clip-path:inset(50%)' in RESULT_CSS
    assert '.carousel-controls button:focus-visible' in RESULT_CSS


def test_legacy_expense_breakdown_requires_matching_total():
    from travelmate.result import split_expenses
    row = dict(category='综合费用', day=None, amount=2200, status='估算',
               name='其他费用2200元构成：厦门—成都往返机票按1600元估算（单程700–900元）；住宿1晚按350元估算；市内交通（机场地铁约20元+打车约40元）按60元；机动/小吃/水按190元。合计1600+350+60+190=2200元。')
    parts = split_expenses([row])
    assert [r['amount'] for r in parts] == [1600, 350, 60, 190]
    assert sum(r['amount'] for r in parts) == 2200
    assert parts[0]['category'] == '交通费用'
    assert parts[1]['category'] == '酒店住宿'
    assert split_expenses([{**row, 'amount': 2300}]) == [{**row, 'amount': 2300}]
    assert split_expenses([{**row, 'amount': None}]) == [{**row, 'amount': None}]


def test_structured_other_expenses_validation_and_display():
    import pytest
    from travelmate.workflow import Itinerary
    plan = deepcopy(PLAN)
    plan.update(other_cost=2200, other_cost_estimated=True, other_cost_items=[
        dict(name='往返机票', category='交通费用', amount=1600),
        dict(name='住宿', category='酒店住宿', amount=600)])
    Itinerary.model_validate(plan)
    guide = make_guide(dict(version=1, plan=plan, requirements=REQ,
                            saved_at=datetime.now(timezone.utc).isoformat()), {})
    ledger = guide['result']['ledger']
    assert [r['amount'] for r in ledger[1:]] == [1600,600]
    assert sum(r['amount'] or 0 for r in ledger) == 2200
    html = render_guide(guide)
    assert 'data-card="酒店住宿"' in html and 'data-card="交通费用"' in html
    assert all(f'data-order="{i}"' in html for i in range(3))
    assert 'value="desc" selected' in html and 'class="budget-cards"' in html
    plan['other_cost_items'][0]['amount'] = 1700
    with pytest.raises(ValueError, match='分项之和'):
        Itinerary.model_validate(plan)

def test_daily_layout_and_separate_tips_keep_exports():
    html = render_sample()
    daily = html.split('id="panel-days"')[1].split('id="panel-weather"')[0]
    tips = html.split('id="panel-tips"')[1]
    assert '<header class="daily-heading">' in daily
    assert 'class="daily-footer"' in daily
    assert 'href="#panel-tips"' in daily
    for title in ('交通与已订安排', '住哪里更顺路', '下雨、排队或约不上时怎么换'):
        assert title not in daily
        assert title in tips
    masthead = html.split('class="daily-masthead"')[1].split('</header>')[0]
    assert 'TravelMate' in masthead
    assert 'href="/plans/1/pdf"' in masthead
    assert 'href="/plans/1/html"' in masthead
    assert 'href="#panel-tips">其他攻略</a>' in html


def test_all_views_share_header_and_snapshot_details_live_in_tips():
    html = render_sample()
    assert '<header class="hero">' not in html
    assert html.count('class="daily-masthead"') == 1
    masthead = html.split('class="daily-masthead"')[1].split('</header>')[0]
    assert '版本' not in masthead and '保存时间' not in masthead
    tips = html.split('id="panel-tips"')[1]
    assert '方案版本与使用说明' in tips
    assert '保存时间' in tips and '已列费用' in tips
    overview = html.split('id="panel-overview"')[1].split('id="panel-budget"')[0]
    assert 'trip-facts' in overview and 'carousel-stage' in overview
    assert '<summary>先说结论</summary>' in tips
    assert '<summary>旅行概览</summary>' in tips
    from travelmate.result import RESULT_CSS
    assert '.result .daily-masthead{display:flex' in RESULT_CSS
    assert 'body:has(.panel-days:target' not in RESULT_CSS
    assert '.btn.ghost{color:#285b48' in RESULT_CSS
