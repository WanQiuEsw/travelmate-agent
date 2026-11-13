"""Accessible result navigation and local interactions over the frozen guide."""
import re
from math import isfinite
from decimal import Decimal
from urllib.parse import urlencode

from travelmate.daily_ui import CSS as DAILY_CSS, day_cards
from travelmate.food_ui import CSS as FOOD_CSS, panel as food_panel
from travelmate.weather_ui import WEATHER_CSS, weather_panel
from travelmate.lodging_ui import CSS as LODGING_CSS, lodging_cards
from travelmate.carousel import CAROUSEL_CSS, CAROUSEL_JS, coverflow
from travelmate.preparation import CSS as PREPARATION_CSS, JS as PREPARATION_JS, panel as preparation_panel
from travelmate.pitfalls_ui import CSS as PITFALL_CSS, panel as pitfalls_panel

RESULT_CSS = """
.result-nav a{text-decoration:none;white-space:nowrap;padding:12px 4px;border-bottom:3px solid transparent;color:#63736c}
.result:not(:has(:target)) a[href="#panel-overview"],.result:has(#panel-overview:target) a[href="#panel-overview"],.result:has(#panel-prepare:target) a[href="#panel-prepare"],.result:has(#panel-budget:target) a[href="#panel-budget"],.result:has(#panel-days:target,.day-anchor:target) a[href="#panel-days"],.result:has(#panel-lodging:target) a[href="#panel-lodging"],.result:has(#panel-food:target) a[href="#panel-food"],.result:has(#panel-pitfalls:target) a[href="#panel-pitfalls"]{border-color:#b94d2a;color:#b94d2a;font-weight:700}
body{background:#faf8f3;color:#193c38}main{max-width:1240px;padding:28px 28px 60px}
.hero img{height:280px}.hero{box-shadow:none}.card{box-shadow:none;border-color:#dedfd5}
.result{background:#f2f0e8;border:1px solid #dedfd5;border-radius:24px;padding:24px}
.result-nav{display:flex;gap:24px;overflow-x:auto;border-bottom:1px solid #ccd4cb;margin-bottom:24px}
.panel{display:none;scroll-margin-top:100vh}.panel-overview{display:block}.result:has(.panel:target,.day-anchor:target) .panel{display:none}.result .panel:target,.result:has(.day-anchor:target) .panel-days{display:block!important}
.result-intro{color:#63736c}.day-anchor{scroll-margin-top:20px}.budget-summary{background:#193c38;color:#fff;border-radius:18px;padding:24px;display:flex;gap:36px;flex-wrap:wrap}.budget-summary strong{display:block;font-size:26px}.budget-summary p{margin:0}.weather-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.weather-day{background:#eaf3ee;border:1px solid #cadbd1;padding:24px;border-radius:18px}.weather-day h3{font-size:20px}.route-map{width:100%;height:300px;background:#eaf3ee;border-radius:18px;border:1px solid #cadbd1}.route-map text{font:16px sans-serif;fill:#fff}.route-map circle{fill:#087f7a}.route-map polyline{stroke:#b94d2a;stroke-width:3;fill:none;stroke-dasharray:8 6}.map-stops{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.map-stops a{background:#fff;border:1px solid #dedfd5;padding:8px 14px;border-radius:12px}.result .card:first-child{margin-top:0}
.day-picker{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}.day-picker a{padding:8px 18px;border:1px solid #cadbd1;border-radius:999px;background:#fff;text-decoration:none}.day-detail{margin-bottom:18px}.day-detail>summary{background:#eaf3ee;padding:16px 20px;border:1px solid #cadbd1;border-radius:16px}.day-detail .card{margin-top:10px}.day-anchor:target>.day-detail>summary{border-color:#b94d2a}.result a:focus-visible,.carousel input:focus-visible{outline:3px solid #b94d2a;outline-offset:4px}
@media print{.day-picker{display:none}}
@media(max-width:700px){main{padding:12px}.result{padding:14px;border-radius:18px}.result-nav{gap:20px}.highlights,.weather-grid{grid-template-columns:1fr}.hero img{height:230px}.budget-summary{gap:18px}}
@media print{.result-nav,.result>input{display:none}.panel,.result:has(.day-anchor:target) .panel{display:block!important}.result{padding:0;border:0}.highlight,.weather-day,.card{break-inside:avoid}}
"""


RESULT_CSS += DAILY_CSS + WEATHER_CSS + CAROUSEL_CSS + PREPARATION_CSS + LODGING_CSS + FOOD_CSS
RESULT_CSS += """
.result-nav a[aria-current=page]{border-color:#b94d2a;color:#b94d2a;font-weight:700}
.trip-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:0 0 20px}.trip-facts>div{background:#eef2e7;padding:14px 20px;border-radius:12px;min-width:0}.trip-facts dt{font-size:12px;color:#63736c}.trip-facts dd{margin:4px 0 0;font-size:17px;overflow-wrap:anywhere}.guide-detail{background:#fffefa;border:1px solid #d8ddcf;border-radius:14px;margin:12px 0;padding:16px 20px}.guide-detail>summary{font-size:17px;color:#285b48}.guide-detail>.card{border:0;padding:12px 0 0;margin:0;background:transparent}.guide-detail>.card>h2{display:none}.snapshot-facts{display:grid;grid-template-columns:auto 1fr;gap:8px 20px;font-size:14px}.snapshot-facts dt{color:#63736c}.snapshot-facts dd{margin:0;overflow-wrap:anywhere}.snapshot-info>p{font-size:13px;color:#63736c}.result-nav a{flex-shrink:0}.panel{min-width:0}.daily-masthead{flex-wrap:wrap}.daily-masthead .actions{flex-shrink:0}.panel-pitfalls .daily-heading{margin-bottom:20px}
@media(max-width:700px){.trip-facts{grid-template-columns:1fr;gap:8px}.trip-facts>div{display:flex;align-items:baseline;gap:16px;padding:10px 14px}.trip-facts dt{flex-shrink:0}.trip-facts dd{font-size:14px}.daily-masthead .actions{margin-left:0;width:100%}.daily-masthead strong{font-size:28px}.daily-masthead span{border:0;padding-left:0;font-size:16px}.guide-detail{padding:14px}.result .result-nav{gap:22px;justify-content:flex-start}}
@media print{.daily-masthead .actions{display:none}.guide-detail::details-content{display:block;content-visibility:visible}.guide-detail{break-inside:avoid}.snapshot-info{font-size:12px}}
"""



def coordinates(value):
    try:
        x, y = map(float, value.split(','))
        return (x, y) if isfinite(x) and isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90 else None
    except (AttributeError, TypeError, ValueError):
        return None


def result_panels(guide, sections, text, inline_images=False, actions=""):
    days = [s for s, _ in sections if s['kind'] == 'day']
    meta = guide.get('result', {})
    out = ['<div class="result" aria-label="旅行方案">']
    views = [('overview', '行程概览'), ('budget', '预算明细'), ('days', '每日行程'), ('lodging', '住宿推荐'), ('food', '当地美食'), ('pitfalls', '避坑指南'), ('prepare', '行程准备')]
    out.append(f'<header class="daily-masthead"><strong><svg class="budget-brand-mark" viewBox="0 0 60 36" aria-hidden="true"><path d="M2 28 21 5q4-5 8 0l21 23-17-5-12-4Z" fill="#196457"/><path d="m30 12 8-7 20 24-17-5Z" fill="#73947f"/><path d="M10 32q14-13 28-3t20-3q-12 14-28 7t-20-1" fill="#196457"/></svg>TravelMate</strong><span>{text(guide["title"])}</span>{actions}</header>')
    out.append('<svg class="budget-header-art" viewBox="0 0 480 120" aria-hidden="true"><path d="M0 99 66 68l36 13 49-35 33 16 48-25 59 39 49-27 47 22 46-19 47 30v25Z" fill="#cfddd3"/><path d="m0 103 70-16 45 4 64-22 54 10 51-12 60 15 57-14 79 25v17H0Z" fill="#9fb9a1"/><path d="M0 106q120-18 240-1t240-2v17H0Z" fill="#d6e3d9"/><path d="M42 112h190m-135 5h260m-80-9h130" stroke="#8ca9a0" opacity=".5"/><g stroke="#294d43" stroke-width="2" fill="#637d6b"><path d="M350 94h53m-44 0V65h34v29m-39-24h44m-50-6q18 0 28-14 10 14 28 14Zm6 14h42m-28-10v26m-10-26v26"/><path d="M256 69V28m-8 41V36h16v33m-20-30h24m-22-8h20m-17-6h14m-11-5h8" fill="none"/></g><g stroke="#779449" fill="none"><path d="M470 0q-20 37-4 102M452 0q-23 25-24 73m20-73q-4 35-12 57M479 0q-4 56-1 110" stroke-width="2"/><path d="m466 15-9 17m9 3 8 18m-11 4-9 18m-17-54-7 15m0 13-9 17m51-50 7 17" stroke-width="5"/></g></svg>')
    out.append('<nav class="result-nav" aria-label="结果板块">' + ''.join(f'<a href="#panel-{key}">{title}</a>' for key, title in views) + '</nav>')
    groups = {key: [] for key, _ in views}
    groups['map'] = []
    details = []
    overview = next((s for s, _ in sections if s['kind'] == 'overview'), {})
    selected_date = meta.get('start_date') if 'start_date' in meta else next((r[1] for r in overview.get('rows', []) if r[0] == '日期' and '未定' not in r[1]), None)
    for index, (section, html) in enumerate(sections):
        kind = section['kind']
        if section['title'] == '行前准备':
            continue
        if kind == 'verify':
            groups['prepare'].append('<details class="guide-detail"><summary>出行待办 · 预约与出发确认</summary><ul>' + ''.join('<li>' + text(row[0]) + ' · ' + text(row[1]) + '</li>' for row in section.get('rows', []) if len(row) >= 2) + '</ul></details>')
            continue
        if kind == 'sources':
            details.append(html)
            continue
        group = ('lodging' if section['title'] == '住哪里更顺路' else
                 kind if kind in ('budget', 'food', 'pitfalls') else
                 'days' if kind == 'day' or section['title'] == '下雨、排队或约不上时怎么换' else 'overview')
        if kind == 'day':
            if not selected_date:
                section = dict(section, title=section['title'].split(' · 天气')[0])
            number = sum(s['kind'] == 'day' for s, _ in sections[:index]) + 1
            html = day_cards(section, number, text, inline_images) if section.get("columns", [])[:1] == ["时段"] else f'<div id="day-{number}" class="day-anchor"><details class="day-detail" open><summary>第 {number} 天 · 查看或收起安排</summary>{html}</details></div>'
        if group == 'lodging':
            html = lodging_cards(section, days, text, inline_images)
        if group == 'overview' or section['title'] == '下雨、排队或约不上时怎么换':
            html = '<details class="guide-detail"><summary>' + text(section['title']) + '</summary>' + html + '</details>'
        groups[group].append(html)
    groups['overview'].insert(0, coverflow(days, text, inline_images))
    groups['prepare'].append(preparation_panel(guide, text))
    facts = [r for r in overview.get('rows', []) if r[0] in ('路线', '人数与天数', '日期')]
    groups['overview'].insert(0, '<dl class="trip-facts">' + ''.join('<div><dt>' + text(r[0]) + '</dt><dd>' + text(r[1]) + '</dd></div>' for r in facts) + '</dl>')
    budget_facts = [r for r in overview.get('rows', []) if '预算' in r[0]]
    groups['budget'].insert(0, budget_panel(meta, days, text) + '<details class="card"><summary>预算口径</summary><ul>' + ''.join('<li>' + text('：'.join(r)) + '</li>' for r in budget_facts) + '<li>综合费用不拆成未经核实的餐饮、酒店报价。</li></ul></details>')
    if meta.get('ledger') is not None:
        groups['budget'] = [groups['budget'][0].replace('<details class="card">', '<details class="budget-source-notes">')] + ['<details class="budget-source-notes"><summary>查看原方案费用表</summary>' + ''.join(groups['budget'][1:]) + '</details>']
    groups['days'].insert(0, '<header class="daily-heading"><h2>每日行程</h2><p>跟着节奏走，把风景慢慢看。</p><nav class="day-picker" aria-label="选择行程日">' + ''.join(f'<a href="#day-{i}">第 {i} 天<span>{text(next((r[1] for r in day.get("rows", []) if len(r) > 1), "当日安排"))}</span></a>' for i, day in enumerate(days, 1)) + '</nav></header>')
    groups['overview'].append('<details class="guide-detail snapshot-info"><summary>方案详情与依据</summary><dl class="snapshot-facts"><dt>版本</dt><dd>' + text(guide.get('version', '—')) + '</dd><dt>保存时间</dt><dd>' + text(guide.get('saved_at', '未记录')) + '</dd><dt>已列费用</dt><dd>' + text(meta.get('cost', '请参见预算明细')) + '</dd></dl><p>' + text(guide.get('notice', '')) + '</p>' + ''.join(details) + '</details>')
    for key, title, description, empty in (
        ('lodging', '住宿推荐', '先选顺路片区，再选合适的住处。', '本版尚无住宿建议，可在对话中补充预算与住宿偏好。'),
        ('food', '当地美食', '跟着路线吃，少绕路，也给用餐留点时间。', '本版尚无美食建议，可在对话中补充口味与忌口。'),
        ('pitfalls', '避坑指南', '把预约、交通与消费的关键提醒提前看清。', '本版未保存专项避坑建议，请结合每日安排与行前准备确认预约和交通。')):
        groups[key].insert(0, ('<span class="lodging-eyebrow">01 / 片区优先</span>' if key == 'lodging' else '') + '<header class="daily-heading"><h2>' + title + '</h2><p>' + description + '</p></header>')
        if len(groups[key]) == 1:
            groups[key].append('<p class="daily-empty">' + empty + '</p>')
    groups['food'] = [food_panel([s for s, _ in sections if s['kind'] == 'food'], days, text, inline_images)]
    groups['pitfalls'] = [pitfalls_panel(guide, sections, text, inline_images)]
    if not days:
        groups['days'].append('<p class="daily-empty">暂无每日行程，请返回对话补充安排。</p>')
    # Historical snapshots have no place metadata; retain their original stop list.
    for i, day in enumerate(days, 1):
        places = (meta.get('places') or [])
        places = places[i-1] if i <= len(places) else [{'name': r[1]} for r in day.get('rows', [])]
        located = [(j, coordinates(p.get('location'))) for j, p in enumerate(places, 1)]
        located = [(j, xy) for j, xy in located if xy is not None]
        groups['map'].append(f'<section class="card"><h2>第 {i} 天 · 地点与顺序</h2>')
        if located:
            xs, ys = [p[0] for _, p in located], [p[1] for _, p in located]
            points = [(j, 50 + (xy[0]-min(xs))/(max(xs)-min(xs) or 1)*700, 250-(xy[1]-min(ys))/(max(ys)-min(ys) or 1)*200) for j, xy in located]
            groups['map'].append('<svg class="route-map" viewBox="0 0 800 300" role="img" aria-label="地点坐标示意图"><polyline points="' + ' '.join(f'{x},{y}' for _, x, y in points) + '"/>' + ''.join(f'<circle cx="{x}" cy="{y}" r="17"/><text x="{x}" y="{y+5}" text-anchor="middle">{j}</text>' for j, x, y in points) + '</svg>')
        groups['map'].append('<p class="muted">按日程顺序连线，仅作地点示意，不代表真实导航路线。未查询到坐标的地点仅列出名称。</p><div class="map-stops">')
        for j, place in enumerate(places, 1):
            groups['map'].append(f'<a href="#day-{i}">{j}. {text(place["name"])} · 查看日程</a>')
            xy = coordinates(place.get('location'))
            if xy:
                url = 'https://uri.amap.com/marker?' + urlencode({'position': f'{xy[0]},{xy[1]}', 'name': place['name']})
                groups['map'].append(f'<a href="{text(url)}" target="_blank" rel="noopener noreferrer">高德地图 ↗</a>')
        groups['map'].append('</div></section>')
    if selected_date:
        groups['days'].insert(1, '<details class="guide-detail daily-weather"><summary>每日天气 · 展开查看</summary>' + weather_panel(meta, days, selected_date, text) + '</details>')
    if groups['map']:
        groups['days'].append('<details class="guide-detail"><summary>景点地图</summary>' + ''.join(groups['map']) + '</details>')
    for key, title in views:
        out.append(f'<section id="panel-{key}" class="panel panel-{key}" aria-label="{title}">' + ''.join(groups[key]) + '</section>')
    return ''.join(out) + '</div>'


def split_expenses(ledger):
    """旧版只拆明确的构成段，分项之和必须与综合费用完全一致。"""
    result = []
    for row in ledger:
        parts = []
        if row['category'] == '综合费用' and row['amount'] is not None:
            match = re.search(r'构成[：:](.+?)(?:合计|总计|$)', row['name'], re.S)
            if match:
                for section in re.split(r'[；;]', match[1]):
                    price = re.search(r'按\s*(\d+(?:\.\d{1,2})?)\s*元', section)
                    if not price:
                        parts = []
                        break
                    name = section[:price.start()].strip(' ，。:：')
                    category = ('酒店住宿' if '住宿' in name else '交通费用' if any(w in name for w in ('机票', '交通', '高铁', '车票')) else '餐饮费用' if any(w in name for w in ('餐', '小吃')) and '机动' not in name else '综合费用')
                    parts.append(dict(row, name=name or '其他支出', category=category,
                                      amount=float(price[1]), detail=section.strip(), split=True))
        if parts and sum(Decimal(str(p['amount'])) for p in parts) == Decimal(str(row['amount'])):
            result.extend(parts)
        else:
            result.append(row)
    return result


def budget_panel(meta, days, text):
    ledger = meta.get('ledger')
    if ledger is None:
        return '<section class="card"><h2>逐项费用</h2><p>历史方案未保存可计算的费用分项，以下保留原有费用表；重新保存方案后可使用分类试算。</p></section>'
    from travelmate.budget_ui import panel
    return panel(dict(meta, ledger=split_expenses(ledger)), text)


RESULT_JS = r"""for (const button of document.querySelectorAll('[data-carousel-target]')) {
  button.addEventListener('click', () => {
    const radio = document.getElementById(button.dataset.carouselTarget);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event('change', {bubbles:true}));
      radio.focus({preventScroll:true});
    }
  });
}

"""

from base64 import b64encode
from hashlib import sha256
from travelmate.budget_ui import CSS as BUDGET_CSS, JS as BUDGET_JS
RESULT_CSS += BUDGET_CSS
RESULT_CSS += """
html{scrollbar-gutter:stable}
body{background:radial-gradient(ellipse at top right,#f3efdf55,transparent 60%),#faf8f3}
body main{max-width:1600px;padding:14px 24px 32px}
.result{position:relative}
.budget-brand-mark{display:inline-block;width:58px;height:36px;margin-right:12px;vertical-align:middle}
.budget-header-art{position:absolute;right:0;top:0;width:320px;height:105px;opacity:.25;pointer-events:none}
.result .daily-masthead{position:relative;z-index:1;padding:0 12px 12px;border:0}
.daily-masthead strong{font-size:36px}
.daily-masthead .actions .btn{background:#fffdf9;color:#165b50;border:1px solid #65958a;border-radius:10px}
.result .result-nav{position:relative;z-index:1;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:12px;overflow:visible;padding:0;margin:0 0 22px;border-bottom:1px solid #bcc8be}
.result .result-nav a{display:flex;align-items:center;justify-content:center;min-width:0;min-height:48px;font-size:19px;padding:10px 8px;text-align:center}
@media(max-width:760px){
body main{padding:12px}
.budget-header-art{display:none}
.budget-brand-mark{width:40px;margin-right:8px}
.result .daily-masthead{gap:12px;padding:0 0 12px}
.daily-masthead strong{font-size:28px}
.daily-masthead span{border:0;padding-left:0;font-size:16px}
.daily-masthead .actions{margin-left:0;width:100%}
.result .result-nav{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:18px;padding:8px 0 12px}
.result .result-nav a{font-size:15px;min-height:44px;padding:8px 4px;background:#f0f3eb;border:1px solid #d8dfd1;border-radius:9px}
.result .result-nav a[aria-current=page]{background:#f9e7d9;border-color:#ba5931;color:#a63c17}
.panel-days .day-picker{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));width:100%;gap:8px;overflow:visible;padding-bottom:0}
.panel-days .day-picker a{padding:8px;min-width:0;min-height:44px}
.day-picker span{max-width:none;min-width:0}
.weather-dates{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));overflow:visible}
.weather-date{min-width:0}
}
@media print{.result .result-nav,.budget-header-art{display:none}}
"""
RESULT_JS += r"""
const resultNav = document.querySelector('.result-nav');
if (resultNav) {
  const updateNavigation = () => {
    const target = document.getElementById(location.hash.slice(1));
    const panel = target?.closest('.panel');
    const current = panel ? '#' + panel.id : '#panel-overview';
    for (const link of resultNav.querySelectorAll('a')) {
      if (link.getAttribute('href') === current) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  };
  window.addEventListener('hashchange', updateNavigation);
  updateNavigation();
}
"""
RESULT_JS += BUDGET_JS
RESULT_CSS += PITFALL_CSS
RESULT_JS += CAROUSEL_JS
RESULT_JS += PREPARATION_JS
RESULT_SCRIPT_HASH = b64encode(sha256(RESULT_JS.encode('utf-8')).digest()).decode('ascii')
