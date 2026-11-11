"""Accessible result navigation over the frozen guide; no scripts or remote assets."""
from math import isfinite
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

RESULT_CSS = """
.result-nav a{text-decoration:none;white-space:nowrap;padding:12px 4px;border-bottom:3px solid transparent;color:#63736c}
.result:not(:has(:target)) a[href="#panel-overview"],.result:has(#panel-overview:target) a[href="#panel-overview"],.result:has(#panel-budget:target) a[href="#panel-budget"],.result:has(#panel-map:target) a[href="#panel-map"],.result:has(#panel-days:target,.day-anchor:target) a[href="#panel-days"],.result:has(#panel-weather:target) a[href="#panel-weather"]{border-color:#b94d2a;color:#193c38;font-weight:700}
body{background:#faf8f3;color:#193c38}main{max-width:1240px;padding:28px 28px 60px}
.hero img{height:280px}.hero{box-shadow:none}.card{box-shadow:none;border-color:#dedfd5}
.result{background:#f2f0e8;border:1px solid #dedfd5;border-radius:24px;padding:24px}
.result-nav{display:flex;gap:24px;overflow-x:auto;border-bottom:1px solid #ccd4cb;margin-bottom:24px}
.panel{display:none}.panel-overview{display:block}.result:has(.panel:target,.day-anchor:target) .panel{display:none}.result .panel:target,.result:has(.day-anchor:target) .panel-days{display:block!important}
.highlights{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.highlight{display:block;text-decoration:none;background:#fff;border:1px solid #dedfd5;border-radius:18px;overflow:hidden;color:#193c38}.highlight-body{padding:18px}.highlight strong{font-size:20px;display:block}.highlight small{color:#b94d2a}.place-art{height:110px;background:linear-gradient(135deg,#dbece2,#eff2df);display:flex;align-items:center;padding:24px;font-size:36px;color:#087f7a}.highlight p{font-size:14px;margin:8px 0 0}.result-intro{color:#63736c}.day-anchor{scroll-margin-top:20px}.budget-summary{background:#193c38;color:#fff;border-radius:18px;padding:24px;display:flex;gap:36px;flex-wrap:wrap}.budget-summary strong{display:block;font-size:26px}.budget-summary p{margin:0}.weather-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.weather-day{background:#eaf3ee;border:1px solid #cadbd1;padding:24px;border-radius:18px}.weather-day h3{font-size:20px}.route-map{width:100%;height:300px;background:#eaf3ee;border-radius:18px;border:1px solid #cadbd1}.route-map text{font:16px sans-serif;fill:#fff}.route-map circle{fill:#087f7a}.route-map polyline{stroke:#b94d2a;stroke-width:3;fill:none;stroke-dasharray:8 6}.map-stops{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}.map-stops a{background:#fff;border:1px solid #dedfd5;padding:8px 14px;border-radius:12px}.result .card:first-child{margin-top:0}
.carousel{max-width:780px;margin:0 auto 24px;text-align:center}.carousel>input{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.carousel:has(>input:focus-visible){outline:3px solid #b94d2a;outline-offset:4px}.carousel-slide{display:none;text-align:left}.carousel .place-art{height:180px}.carousel .highlight-body{padding:24px}.carousel .highlight strong{font-size:26px}.carousel-controls{display:flex;justify-content:space-between;align-items:center;padding:16px 0;color:#63736c}.carousel-controls button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;cursor:pointer;border:1px solid #a8c9bd;border-radius:999px;padding:10px 18px;background:#fff;color:#087f7a;font:inherit;font-size:14px;font-weight:600;box-shadow:0 3px 8px #193c3808;transition:background .15s,color .15s}.carousel-controls button:hover{background:#087f7a;border-color:#087f7a;color:#fff}.carousel-controls button:focus-visible{outline:3px solid #b94d2a;outline-offset:3px}.carousel-controls button:active{transform:translateY(1px)}.day-picker{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}.day-picker a{padding:8px 18px;border:1px solid #cadbd1;border-radius:999px;background:#fff;text-decoration:none}.day-detail{margin-bottom:18px}.day-detail>summary{background:#eaf3ee;padding:16px 20px;border:1px solid #cadbd1;border-radius:16px}.day-detail .card{margin-top:10px}.day-anchor:target>.day-detail>summary{border-color:#b94d2a}.result a:focus-visible,.carousel input:focus-visible{outline:3px solid #b94d2a;outline-offset:4px}
@media print{.carousel-slide{display:block!important}.carousel-controls,.carousel>input,.day-picker{display:none}}
.carousel{max-width:none;overflow:hidden;padding:10px 20px 24px;background:#eaf3ee;border:1px solid #cadbd1;border-radius:22px}.carousel-stage{position:relative;height:540px;margin:30px 0 0 20%;perspective:1200px}.carousel-slide{position:absolute;top:0;left:0;width:48%;transform-origin:left center;transition:transform .45s ease;}.carousel-slide .highlight{box-shadow:0 18px 36px #193c3826}.carousel .place-art{height:240px;display:flex;flex-direction:column;align-items:flex-start;justify-content:space-between;background:linear-gradient(145deg,#adcfc2,#e5edcd);position:relative;overflow:hidden}.place-art:after{content:"";position:absolute;width:220px;height:220px;border:1px solid #ffffff70;border-radius:50%;right:-70px;top:-60px}.place-art span{font-size:14px;letter-spacing:.16em}.place-art b{font-size:32px;line-height:1.3}.place-art small{font-size:12px}.carousel .highlight-body{background:#fff;min-height:180px}.carousel .highlight-body p:first-of-type{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.carousel-controls{display:none}.budget-workspace{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:20px;align-items:start;margin-bottom:20px}.budget-table,.budget-totals{background:#fff;border:1px solid #dedfd5;border-radius:18px;padding:20px}.budget-toolbar{display:flex;gap:14px;flex-wrap:wrap;border-bottom:1px solid #dedfd5;padding-bottom:16px}.budget-toolbar select{max-width:170px;border:1px solid #ccd4cb;border-radius:8px;padding:6px;color:#193c38;background:#faf8f3}.budget-table td,.budget-table th{border:0;border-bottom:1px solid #dedfd5}.budget-table input[type=number]{width:108px;max-width:100%;border:1px solid #ccd4cb;border-radius:7px;padding:6px;color:#193c38;background:#faf8f3}.budget-totals{position:sticky;top:20px;background:#193c38;color:#fff}.budget-totals h3{font-size:24px;font-weight:400;margin:0}.ledger-total{font-size:42px;overflow-wrap:anywhere;line-height:1.3;margin:18px 0}.category-totals{display:grid;grid-template-columns:1fr 1fr;gap:16px}.category-totals p{margin:0;border-top:1px solid #ffffff30;padding-top:12px;font-size:13px}.category-totals strong{display:block;font-size:22px;color:#f1c5a7}.budget-totals .muted{color:#d3dfd8}.budget-status{font-size:12px;color:#63736c}.expense-explanation{margin-top:8px;max-width:420px}.expense-explanation summary{font-size:13px;font-weight:500;color:#087f7a;cursor:pointer}.expense-explanation p{margin:8px 0 0;padding:12px;background:#eaf3ee;border-radius:10px;font-size:13px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.budget-table td:nth-child(3){min-width:180px;width:100%}.budget-table td:not(:nth-child(3)){white-space:nowrap}.budget-table tr:has(input[type=checkbox]:not(:checked)){opacity:.55}
@media(prefers-reduced-motion:reduce){.carousel-slide{transition:none}}
@media(max-width:700px){.carousel-stage{height:510px;margin-left:4%}.carousel-slide{width:80%}.carousel .place-art{height:200px}.budget-workspace{grid-template-columns:1fr}.budget-totals{position:static}}
@media print{.carousel-stage{height:auto;margin:0}.carousel-slide{position:static;transform:none!important;width:100%;margin-bottom:20px}.budget-workspace{display:block}.budget-totals{position:static}}
@media(max-width:700px){main{padding:12px}.result{padding:14px;border-radius:18px}.result-nav{gap:20px}.highlights,.weather-grid{grid-template-columns:1fr}.hero img{height:230px}.budget-summary{gap:18px}.place-art{height:80px}}
@media print{.result-nav,.result>input{display:none}.panel,.result:has(.day-anchor:target) .panel{display:block!important}.result{padding:0;border:0}.highlight,.weather-day,.card{break-inside:avoid}}
"""


def coordinates(value):
    try:
        x, y = map(float, value.split(','))
        return (x, y) if isfinite(x) and isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90 else None
    except (AttributeError, TypeError, ValueError):
        return None


def result_panels(guide, sections, text):
    days = [s for s, _ in sections if s['kind'] == 'day']
    meta = guide.get('result', {})
    out = ['<div class="result" aria-label="旅行方案">']
    views = [('overview', '行程概览'), ('budget', '预算明细'), ('map', '景点地图'), ('days', '每日行程'), ('weather', '天气信息')]
    out.append('<nav class="result-nav" aria-label="结果板块">' + ''.join(f'<a href="#panel-{key}">{title}</a>' for key, title in views) + '</nav>')
    groups = {key: [] for key, _ in views}
    for index, (section, html) in enumerate(sections):
        kind = section['kind']
        group = 'budget' if kind == 'budget' else 'days' if kind in ('day', 'food', 'traffic') or section['title'] in ('交通与已订安排', '住哪里更顺路', '时间安排说明', '下雨、排队或约不上时怎么换') else 'overview'
        if kind == 'day':
            number = sum(s['kind'] == 'day' for s, _ in sections[:index]) + 1
            html = f'<div id="day-{number}" class="day-anchor"><details class="day-detail" open><summary>第 {number} 天 · 查看或收起安排</summary>{html}</details></div>'
        groups[group].append(html)
    slides = [(i, j, row) for i, day in enumerate(days, 1) for j, row in enumerate(day.get('rows', []), 1)]
    cards = ['<h2>把期待，排进每一天</h2><p class="result-intro">切换查看重点安排，点击卡片进入当日日程。也可用方向键切换景点。</p><div class="carousel" role="region" aria-label="景点轮播">']
    for n, (i, j, row) in enumerate(slides, 1):
        cards.append(f'<input type="radio" name="highlight" id="highlight-{n}" aria-label="景点 {n}：{text(row[1])}" {"checked" if n == 1 else ""}>')
    rules = ''
    for n in range(1, len(slides)+1):
        for offset in range(min(4, len(slides))):
            target = (n + offset - 1) % len(slides) + 1
            rules += f'.carousel:has(#highlight-{n}:checked) .slide-{target}' + '{display:block;transform:translateX(' + str(offset*51) + '%) scale(' + str(1-offset*.12) + ');z-index:' + str(5-offset) + ';}'
        rules += f'.carousel:has(#highlight-{n}:checked) .slide-{n} .carousel-controls' + '{display:flex}'
    cards.append('<style>' + rules + '</style><div class="carousel-stage">')
    for n, (i, j, row) in enumerate(slides, 1):
        previous, following = (n-2) % len(slides)+1, n % len(slides)+1
        cards.append(f'<article class="carousel-slide slide-{n}"><a class="highlight" href="#day-{i}"><div class="place-art" aria-hidden="true"><span>DAY {i:02d} / {j:02d}</span><b>{text(row[1])}</b><small>景点封面待补充</small></div><div class="highlight-body"><small>第 {i} 天 · {text(row[0])}</small><strong>{text(row[1])}</strong><p>{text(row[2])}</p><p>查看当日日程 ↗</p></div></a><div class="carousel-controls"><button type="button" data-carousel-target="highlight-{previous}" aria-label="上一个景点"><span aria-hidden="true">←</span> 上一个</button><span>{n} / {len(slides)}</span><button type="button" data-carousel-target="highlight-{following}" aria-label="下一个景点">下一个 <span aria-hidden="true">→</span></button></div></article>')
    if not slides:
        cards.append('<p>本版暂无景点安排，请返回对话补充旅行需求。</p>')
    groups['overview'].insert(0, ''.join(cards) + '</div></div>')
    overview = next((s for s, _ in sections if s['kind'] == 'overview'), {})
    budget_facts = [r for r in overview.get('rows', []) if '预算' in r[0]]
    groups['budget'].insert(0, budget_panel(meta, days, text) + '<details class="card"><summary>预算口径</summary><ul>' + ''.join('<li>' + text('：'.join(r)) + '</li>' for r in budget_facts) + '<li>综合费用不拆成未经核实的餐饮、酒店报价。</li></ul></details>')
    groups['days'].insert(0, '<nav class="day-picker" aria-label="选择行程日">' + ''.join(f'<a href="#day-{i}">第 {i} 天</a>' for i in range(1, len(days)+1)) + '</nav>')
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
    selected_date = meta.get('start_date') if 'start_date' in meta else next((r[1] for r in overview.get('rows', []) if r[0] == '日期' and '未定' not in r[1]), None)
    groups['weather'].append('<h2>出行天气</h2>')
    if not selected_date:
        groups['weather'].append('<div class="weather-day" role="status"><h3>尚未选择出行日期</h3><p>请先在快速规划中选择出发日期，或在对话中补充具体日期。确认并保存新方案后，才能查看对应日期的天气。</p><p>当前按第几天展示行程，不提供具体日期的天气预报。</p></div>')
    else:
        groups['weather'].append('<p class="result-intro">出发日期：' + text(selected_date) + '。以下为保存时取得的天气信息。</p><div class="weather-grid">')
        for i, day in enumerate(days, 1):
            groups['weather'].append(f'<article class="weather-day"><span>第 {i} 天</span><h3>{text(day["title"])}</h3><p>出发前复查预报；遇雨可选择室内备选，户外活动预留调整时间。</p></article>')
        groups['weather'].append('</div><p class="muted">预报查询时间：' + text('；'.join(meta.get('weather_times', [])) or '本版未记录可用查询时间；缺失的温度、降水和风力不作推测。') + '</p>')
    for key, title in views:
        out.append(f'<section id="panel-{key}" class="panel panel-{key}" aria-label="{title}">' + ''.join(groups[key]) + '</section>')
    return ''.join(out) + '</div>'


def budget_panel(meta, days, text):
    ledger = meta.get('ledger')
    if ledger is None:
        return '<section class="card"><h2>逐项费用</h2><p>历史方案未保存可计算的费用分项，以下保留原有费用表；重新保存方案后可使用分类试算。</p></section>'
    categories = list(dict.fromkeys(['景点门票', '酒店住宿', '餐饮费用', '交通费用', '活动费用', '综合费用'] + [r['category'] for r in ledger]))
    cents = lambda value: int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    totals = {category: sum(cents(r['amount']) for r in ledger if r['category'] == category and r['amount'] is not None) for category in categories}
    unknown = sum(r['amount'] is None for r in ledger)
    amount = sum(totals.values())
    travelers = meta.get('travelers') or 1
    out = [f'<div class="budget-workspace" data-travelers="{travelers}"><section class="budget-table"><h2>逐项费用</h2><div class="budget-toolbar"><label>筛选 <select data-budget-filter aria-label="筛选费用类型"><option value="">全部类型</option>' + ''.join(f'<option>{text(c)}</option>' for c in categories) + '</select></label><label>排序 <select data-budget-sort aria-label="排序费用"><option value="original">日程顺序</option><option value="desc">金额从高到低</option><option value="asc">金额从低到高</option></select></label></div><p class="budget-status">金额为全员人民币费用。可修改金额、取消勾选进行本页试算；筛选不改变总额。试算不保存到方案或导出文件。</p><div class="table-scroll"><table><thead><tr><th scope="col">类型</th><th scope="col">天数</th><th scope="col">项目</th><th scope="col">金额（元）</th><th scope="col">计入</th></tr></thead><tbody data-ledger>']
    for index, row in enumerate(ledger):
        description = row['name'].replace('other_cost', '其他费用')
        name = '其他综合费用' if row['category'] == '综合费用' else description
        explanation = (f'<details class="expense-explanation"><summary>费用说明</summary><p>{text(description)}</p></details>'
                       if row['category'] == '综合费用' or len(description) > 80 else '')
        if len(name) > 80:
            name = name[:60] + '…'

        value = f'{cents(row["amount"])/100:.2f}' if row['amount'] is not None else ''
        day = f'第 {row["day"]} 天' if row.get('day') else '全程'
        out.append(f'<tr data-category="{text(row["category"])}" data-order="{index}"><td>{text(row["category"])}</td><td>{day}</td><td>{text(name)}{explanation}<div class="budget-status">{text(row["status"])}</div></td><td><input type="number" min="0" max="100000000" step="0.01" value="{value}" placeholder="待核实" aria-label="{text(name)}全员费用"></td><td><input type="checkbox" checked aria-label="计入{text(name)}"></td></tr>')
    label = f'¥{amount/100:.2f}' if amount or not unknown else '待核实'
    out.append('</tbody></table></div><noscript>启用 JavaScript 后可筛选、排序和试算；当前显示保存时金额。</noscript></section><aside class="budget-totals" aria-label="费用汇总"><h3>预算明细</h3><p class="ledger-total" data-total>' + label + '</p><p>人均已列费用 <strong data-person>' + (f'¥{(Decimal(amount) / travelers / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):.2f}' if amount or not unknown else '待核实') + '</strong></p><p class="muted" data-budget-notice role="status">已列金额小计；' + str(unknown) + ' 项金额待核实</p><div class="category-totals">')
    for category in categories:
        present = any(r['category'] == category for r in ledger)
        category_unknown = any(r['category'] == category and r['amount'] is None for r in ledger)
        value = ('待核实' if totals[category] == 0 else f'¥{totals[category]/100:.2f} + 待核实') if category_unknown else f'¥{totals[category]/100:.2f}' if present else '未单列'
        out.append(f'<p>{text(category)}<strong data-category-total="{text(category)}">{value}</strong></p>')
    return ''.join(out) + '</div><p class="muted">综合费用只计一次；未知金额不按免费处理。</p><button type="button" data-budget-reset>恢复方案金额</button></aside></div>'


RESULT_JS = r"""for (const button of document.querySelectorAll('[data-carousel-target]')) {
  button.addEventListener('click', () => {
    const radio = document.getElementById(button.dataset.carouselTarget);
    if (radio) { radio.checked = true; radio.focus({preventScroll:true}); }
  });
}
const workspace = document.querySelector('.budget-workspace');
if (workspace) {
  const rows = [...workspace.querySelectorAll('[data-ledger] tr')];
  const filter = workspace.querySelector('[data-budget-filter]');
  const sort = workspace.querySelector('[data-budget-sort]');
  const money = cents => '¥' + (cents / 100).toFixed(2);
  const amount = row => {
    const input = row.querySelector('input[type=number]');
    if (!/^\d+(?:\.\d{1,2})?$/.test(input.value) || !input.validity.valid) return null;
    const [whole, fraction = ''] = input.value.split('.');
    return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  };
  function update() {
    let total = 0, unknown = 0;
    const categories = new Map();
    for (const row of rows) {
      row.hidden = Boolean(filter.value && row.dataset.category !== filter.value);
      if (!row.querySelector('input[type=checkbox]').checked) continue;
      const value = amount(row);
      const item = categories.get(row.dataset.category) || {total: 0, unknown: 0};
      if (value === null) { unknown++; item.unknown++; }
      else { total += value; item.total += value; }
      categories.set(row.dataset.category, item);
    }
    workspace.querySelector('[data-total]').textContent = !total && unknown ? '待核实' : money(total);
    workspace.querySelector('[data-person]').textContent = !total && unknown ? '待核实' : money(Math.round(total / Number(workspace.dataset.travelers)));
    workspace.querySelector('[data-budget-notice]').textContent = '本页试算小计；' + unknown + ' 项金额待核实（未保存）';
    for (const node of workspace.querySelectorAll('[data-category-total]')) {
      const item = categories.get(node.dataset.categoryTotal);
      node.textContent = !item ? '未单列' : item.unknown ? (item.total ? money(item.total) + ' + 待核实' : '待核实') : money(item.total);
    }
    const ordered = [...rows].sort((a,b) => {
      if (sort.value === 'original') return Number(a.dataset.order)-Number(b.dataset.order);
      const x = amount(a), y = amount(b);
      if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
      return sort.value === 'asc' ? x-y : y-x;
    });
    const body = workspace.querySelector('[data-ledger]');
    for (const row of ordered) body.append(row);
  }
  workspace.addEventListener('change', update);
  workspace.querySelector('[data-budget-reset]').addEventListener('click', () => {
    for (const row of rows) {
      const input = row.querySelector('input[type=number]'); input.value = input.defaultValue;
      row.querySelector('input[type=checkbox]').checked = true;
    }
    filter.value = ''; sort.value = 'original'; update();
  });
}
"""

from base64 import b64encode
from hashlib import sha256
RESULT_SCRIPT_HASH = b64encode(sha256(RESULT_JS.encode('utf-8')).digest()).decode('ascii')
