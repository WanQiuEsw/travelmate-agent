"""One frozen public document shared by the preview and PDF."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from html import escape

from travelmate.evidence import safe_url, context_key
from travelmate.public import public_data, public_answer, internal_title
from travelmate.workflow import budget_total, time_label, travel_label, cost_label, total_cost_label, TIME_NOTICE


def day_heading(value, index, requirements, evidence, asof=None):
    if not value:
        return f"第{index}天 · 天气：出发日期未定"
    day = date.fromisoformat(str(value))
    label = f"{day.year}年{day.month}月{day.day}日 · 星期{'一二三四五六日'[day.weekday()]}"
    asof = asof or datetime.now(timezone.utc)
    if asof.tzinfo is None:
        asof = asof.replace(tzinfo=timezone.utc)
    forecasts = []
    for record in evidence.values():
        if (record.get('kind') != 'weather_forecast' or record.get('context') != context_key(requirements)
                or record.get('query_status') != 'success' or record.get('applicable_date') != day.isoformat()):
            continue
        try:
            queried = datetime.fromisoformat(record['queried_at'])
            expires = datetime.fromisoformat(record['expires_at'])
            if queried <= asof <= expires and record.get('value', {}).get('date') == day.isoformat():
                forecasts.append(record)
        except (KeyError, TypeError, ValueError):
            continue
    if forecasts:
        row = max(forecasts, key=lambda item: datetime.fromisoformat(item['queried_at']))['value']
        weather = f"白天{row.get('dayweather') or '未提供'}，夜间{row.get('nightweather') or '未提供'}"
        if row.get('nighttemp') is not None and row.get('daytemp') is not None:
            weather += f"，{row['nighttemp']}至{row['daytemp']}℃"
        return label + ' · 天气预报：' + weather
    local_today = asof.astimezone(timezone(timedelta(hours=8))).date()
    weather = '超出预报范围' if day > local_today + timedelta(days=3) else '暂无预报'
    return label + ' · 天气：' + weather


def food_items(plan, requirements):
    items = []
    for food in plan.get('foods', []):
        text = f"{food['name']}：{food['description']}"
        if food.get('area'):
            text += '\n用餐建议：' + food['area']
        if food.get('tips'):
            text += '\n点单提醒：' + food['tips']
        items.append(public_answer(text))
    if requirements.get('dietary'):
        items.append('饮食要求：' + requirements['dietary'] + '；点单时与商家确认食材及交叉接触情况。')
    return items


def preliminary_brief(req):
    if not all(req.get(key) for key in ('destination', 'days', 'travelers')):
        return '先按目的地与兴趣选择相邻片区，确认人数、天数和预算后细化路线。'
    route = (req.get('origin') + ' → ' if req.get('origin') else '') + req['destination']
    lines = [f'## {route} · {req["days"]}天玩法草案', '', f'{req["travelers"]}人同行，偏好：{req.get("preferences") or "按已知兴趣顺路安排"}。',
             '', '### 先给建议', '把用餐与景点安排在相邻片区，首末日保留交通弹性，完整游玩日再安排重点活动。', '', '### 每天怎么安排']
    for i in range(1, req['days'] + 1):
        action = '抵达后先放行李，在住宿附近轻量游览、尝当地小吃' if i == 1 else '顺路早餐、轻量游览，取行李并提前前往车站或机场' if i == req['days'] else '围绕同片区安排早午晚餐，穿插游览、休息与排队缓冲'
        if req['days'] == 1:
            action = '按实际到达与返程时间选择一个片区，顺路用餐，避免赶场'
        lines.append(f'- 第{i}天：{action}。')
    lines += ['', '### 预算先确认口径']
    if req.get('budget'):
        scope = {'total': '全员总预算', 'per_person': '每人预算'}.get(req.get('budget_scope'), '尚未确认是全员还是每人预算')
        lines.append(f'你给出的金额为 {req["budget"]:g} {req.get("budget_currency") or "（币种待确认）"}，{scope}。')
    lines.append('确认是否包含往返交通和住宿后再算账；不把未查询的票价或酒店价格当作可购买报价。')
    if not req.get('start_date'):
        lines += ['', '### 日期与天气', '日期未定时先按第几天规划；确定日期后再查询车次及覆盖日期内的天气预报。']
    return '\n'.join(lines)


def budget_allocation(req):
    """A spending envelope from the user's budget, never a service-provider quote."""
    includes = req.get('budget_includes') or ''
    if req.get('budget_currency') != 'CNY' or includes not in ('全部费用', '往返交通、住宿、餐饮、门票及市内交通全部费用'):
        return []
    total = round(budget_total(req) * 100)
    portions = [('往返交通', 40), ('住宿', 20), ('餐饮与小吃', 25), ('门票与市内交通', 5)]
    allocated = [(name, total * percent // 100) for name, percent in portions]
    allocated.append(('机动资金', total - sum(value for _, value in allocated)))
    return [[name, f'¥{value / 100:.2f}'] for name, value in allocated]


def public_guide(guide):
    guide = deepcopy(guide)
    guide['sections'] = [section for section in guide['sections'] if not internal_title(section['title'])]
    for section in guide['sections']:
        if section.get('rows'):
            section['rows'] = [[public_answer(str(value)) for value in row] for row in section['rows']]
        for item in section['items']:
            item['text'] = public_answer(item['text'])
            if '查看地图' in item.get('link_label', '') or 'uri.amap.com/marker' in (item.get('link') or ''):
                item.pop('link', None)
                item.pop('link_label', None)
    return guide


def display_time(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M（北京时间）")


SOURCE_NAMES = {'search_knowledge': '旅游参考资料', 'search_web': '网页资料搜索',
                'search_places': '高德地点查询', 'search_weather': '天气预报', 'search_train_tickets': '铁路车次查询'}


def source_note(requirements, evidence, asof):
    """金额结论后面标明来自哪类网上资料、哪天查的，方便判断时效。"""
    found = {}
    for record in evidence.values():
        if record.get('context') != context_key(requirements) or record.get('query_status') != 'success':
            continue
        if record.get('kind') not in ('document', 'train', 'weather_forecast'):
            continue
        name = SOURCE_NAMES.get(record.get('tool'), record.get('title'))
        try:
            day = datetime.fromisoformat(record['queried_at']).astimezone(
                timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
        except (KeyError, TypeError, ValueError):
            continue
        found[name] = max(found.get(name, ''), day)
    if not found:
        return None
    order = list(SOURCE_NAMES.values())
    parts = [f'{name} · {found[name]} 查询'
             for name in sorted(found, key=lambda item: order.index(item) if item in order else 99)]
    return ('金额来源：' + '；'.join(parts)
            + '。以上是网上公开资料，价格会变；没有标注来源的金额是估算，⏳ 项目请在出行前按官方渠道复核。')


def make_guide(version, evidence):
    req, plan = version['requirements'], version['plan']
    if not version.get('saved_at'):
        evidence = {}
    asof = datetime.fromisoformat(version.get('saved_at') or '1970-01-01T00:00:00+00:00')
    if asof.tzinfo is None:
        asof = asof.replace(tzinfo=timezone.utc)
    sections = []

    def section(title, texts=(), kind='notes', columns=(), rows=()):
        items = [{'text': text} if isinstance(text, str) else text for text in texts]
        sections.append({'title': title, 'kind': kind, 'items': items,
                         **({'columns': list(columns), 'rows': rows} if columns else {})})

    stops = [stop for day in plan['days'] for stop in day['stops']]
    total = round(plan['other_cost'] + sum(stop['cost'] for stop in stops), 2)
    other_estimated = plan.get('other_cost_estimated', False)
    displayed_total = total_cost_label(stops, req, evidence, plan['other_cost'], asof, other_cost_estimated=other_estimated)
    scope = '人均' if req.get('budget_scope') == 'per_person' else '全员'
    route = (req.get('origin') + ' → ' if req.get('origin') else '') + req['destination']
    judgment = ('当前报价未齐，不能确认预算是否足够；先落实往返交通和住宿，再安排餐饮及机动资金。'
                if displayed_total == '无法查询' else f'已列项目合计{displayed_total}；仍需按预算范围核对是否覆盖全部支出。')
    opening = [plan.get('key_call') or plan.get('summary')
               or f'建议围绕{req.get("preferences") or "你的旅行偏好"}按相邻片区游玩，首末日保留交通弹性。']
    if plan.get('hard_rules'):
        opening.append('由此推出的硬规则：\n'
                       + '\n'.join(f'{index}. {rule}' for index, rule in enumerate(plan['hard_rules'], 1)))
    section('先说结论', [*opening, judgment])
    note = source_note(req, evidence, asof)
    section('旅行概览', kind='overview', columns=['项目', '安排'], rows=[
        ['路线', route], ['人数与天数', f'{req["travelers"]}人 · {req["days"]}天'],
        ['日期', req.get('start_date') or '日期未定，按第几天展示'],
        ['预算', f'{scope} {req["budget"]:.2f} {req.get("budget_currency") or "CNY"}；全员预算{budget_total(req):.2f}'],
        ['预算包含', req.get('budget_includes') or '旧方案未记录，请先确认范围'],
        ['旅行偏好', req.get('preferences') or '未说明'],
        ['行动与饮食', f'{req.get("mobility") or "行动限制未说明，先预留休息"}；{req.get("dietary") or "忌口未说明，点单前确认"}']])
    budget_rows = [[f'第{i}天已列活动', total_cost_label(day['stops'], req, evidence, now=asof)] for i, day in enumerate(plan['days'], 1)]
    other_label = (f"约¥{plan['other_cost']:.2f}（估算）" if other_estimated else
                   '无法查询' if plan['other_cost'] else '未单列，不能据此判断免费')
    budget_rows += [['其他费用', other_label], ['已列项目合计', displayed_total]]
    allocation = budget_allocation(req)
    if allocation:
        section('预算怎么用', ['以下只是从用户总预算中分配的可调整预留额度，不是票价、房价或餐费查询结果。拿到真实报价后再调整比例；机动资金也属于总预算，不重复相加。'],
                'budget', ['用途', '建议预留额度（非报价）'], allocation)
    budget_notes = ['此表汇总已列项目；估算与实时查询分开标注，未知金额不计入小计。',
                    '先预留往返交通、预算范围内的住宿及机动资金，再决定餐饮档次。']
    if note:
        budget_notes.append(note)
    if other_estimated:
        budget_notes.append(plan['cost_notes'])
    section('已列费用与报价状态' if allocation else '预算怎么用', budget_notes,
        'budget', ['项目', '全员费用'], budget_rows)
    tiers = plan.get('budget_tiers') or []
    if tiers:
        rows = [[tier['name'], tier['lodging'], tier['transport'], tier['dining'],
                 f"约¥{tier['total']:.0f}" if tier.get('total') is not None else '待核实',
                 tier.get('note') or '按档位替换住宿与餐标，行程不用重做'] for tier in tiers]
        section('预算三档对照', ['三档只换住宿、交通和餐标，行程顺序不变；金额为全员估算，标注待核实的以官方渠道为准。']
                + ([note] if note else []),
                'budget', ['档位', '住宿', '交通', '餐饮', '全员总计', '说明'], rows)
    traffic = []
    for segment in plan.get('rail_segments', []):
        t = segment['ticket']
        traffic.append(f'{t.get("start_train_code")} {t.get("from_station")} → {t.get("to_station")}，{t.get("start_date")} {t.get("start_time")}出发，{t.get("arrive_time")}到达。第三方MCP查询参考，余票与票价以12306购票时为准。')
    if not traffic:
        traffic.append('未绑定具体车次或航班；日期与交通方式确定后查询，不把历史时刻或价格当作本次可购买方案。')
    traffic += ['已订安排：' + booking['description'] + (f'，第{booking["day"]}天' if booking.get('day') else '') + (f' {booking["departure"]}出发' if booking.get('departure') else '') for booking in req.get('bookings', [])]
    if req.get('return_deadline'):
        traffic.append('最后一天返程时限：' + req['return_deadline'] + '，提前取行李并预留交通与进站时间。')
    section('交通与已订安排', traffic)
    section('住哪里更顺路', plan.get('lodging') or ['优先结合当日游玩片区选择交通方便的住宿，核对到站交通、取消条款和房型；未查到房态与价格时不指定可订酒店。'])
    if plan.get('time_granularity') == 'period':
        section('时间安排说明', [TIME_NOTICE])
    for i, day in enumerate(plan['days'], 1):
        modes = {'unknown': '方式待定', 'walking': '步行', 'driving': '驾车', 'transit': '公交/地铁', 'rail': '铁路', 'flight': '飞机', 'ferry': '轮渡'}
        rows = [[time_label(plan, stop), stop['place'], stop.get('notes') or '按预约和体力调整', modes[stop.get('transport_mode', 'unknown')] + '，' + travel_label(stop), cost_label(stop, req, evidence, asof)] for stop in day['stops']]
        meals = [f'{food.get("meal", "不限")}：{food["name"]}' for food in plan.get('foods', []) if food.get('day') == i]
        notes = ['当日美食：' + '；'.join(meals)] if meals else []
        section(day_heading(day.get('date'), i, req, evidence, asof), notes, 'day', ['时段', '顺路安排', '吃什么 / 怎么玩', '交通预留', '全员费用'], rows)
    foods = plan.get('foods', [])
    if foods:
        rows = [[food['name'], food['description'], (f'第{food["day"]}天 · ' if food.get('day') else '') + food.get('meal', '不限'), food.get('area') or '结合当日片区顺路选择', food.get('tips') or '点单前确认食材与忌口'] for food in foods]
        section('当地特色美食', ['推荐用于选择菜品与用餐片区，不代表餐厅房态、实时价格或过敏安全保证。'] + ([f'饮食要求：{req["dietary"]}；点单时向商家确认。'] if req.get('dietary') else []), 'food', ['美食', '特色', '安排在哪顿', '顺路建议', '点单提醒'], rows)
    pitfalls = plan.get('pitfalls') or []
    if pitfalls:
        icons = {'严重': '❌', '注意': '⚠️', '技巧': '💡'}
        section('避坑', [f"{icons.get(item['level'], '⚠️')} {item['text']}" for item in pitfalls]
                + ['以上涉及营业时间、票价与开放状态的条目，出行前请按下方清单通过官方渠道复核。'], 'pitfalls')
    alternatives = plan.get('alternatives', [])
    if alternatives:
        rows = [[a['trigger'], a['action'],
                 f"约¥{a['extra_cost']:.2f}（估算）" if a.get('extra_cost') is not None else '待核实'] for a in alternatives]
        section('下雨、排队或约不上时怎么换', ['应急方案 · 增加费用按全员计算。'],
                columns=['触发情况', '立即怎么换', '预计增加费用'], rows=rows)
    else:
        section('下雨、排队或约不上时怎么换', ['遇雨可减少室外步行、选择同片区室内活动；餐馆排队时优先换附近同类菜品，是否开放及能否入场以当日公告为准。'])
    section('行前准备', plan.get('reminders', []) or ['确定日期后查询往返交通与天气；确认酒店取消条款、场馆规则、餐馆营业信息和饮食限制。'])
    if plan.get('verify_items'):
        section('待核实清单', ['以下内容本次没有取得可核实的实时数据，出发前按对应渠道确认，不要按记忆出发。'], 'verify',
                ['项目', '核验渠道'], [[item['item'], item['channel']] for item in plan['verify_items']])
    sources, seen = [], set()
    for record in evidence.values():
        if record.get('context') != context_key(req):
            continue
        label = {'success': '查询匹配' if record['verification'] == 'matched' else '文档参考', 'empty': '无结果', 'failed': '查询失败', 'out_of_range': '超查询范围'}[record['query_status']]
        key = (record['title'], label, record.get('url'))
        if key in seen:
            continue
        seen.add(key)
        name = {'search_knowledge': '旅游参考资料检索', 'search_places': '高德地点查询', 'search_web': '网页资料搜索', 'search_weather': '天气预报查询', 'search_train_tickets': '铁路车次查询'}.get(record['title'], record['title'])
        sources.append({'text': f'{name} · {label} · 查询时间{display_time(record["queried_at"])}', 'link': safe_url(record.get('url')), 'link_label': '公开来源'})
    section('参考来源', sources or ['本版没有可追溯的公开查询结果，不将具体报价或营业状态标为已核实。'], 'sources')
    return public_guide(public_data({'title': f'{route} · {req["days"]}天旅行攻略', 'version': version['version'],
        'saved_at': display_time(version['saved_at']) if version.get('saved_at') else '未记录（历史版本）',
        'notice': '这是保存时的方案快照，天气为当时取得的预报；出发前重新确认天气、场馆规则和价格。', 'total': total, 'sections': sections}))


def guide_markdown(guide):
    guide = public_guide(guide)

    def cell(value):
        return str(value).replace('|', '／').replace('\n', '；').replace('\r', ' ')

    lines = [f'# {guide["title"]}', '', f'> 版本 {guide["version"]} · 保存于 {guide["saved_at"]}', f'> {guide["notice"]}', '']
    for section in guide['sections']:
        lines += ['## ' + section['title'], '']
        if section.get('columns'):
            lines += ['| ' + ' | '.join(map(cell, section['columns'])) + ' |', '| ' + ' | '.join('---' for _ in section['columns']) + ' |']
            lines += ['| ' + ' | '.join(map(cell, row)) + ' |' for row in section['rows']]
            lines.append('')
        for item in section['items']:
            text = item['text']
            url = safe_url(item.get('link'))
            if url:
                text += f' [公开来源]({url})'
            if text.strip():
                lines += ['- ' + text.replace('\n', '\n  ')]
        lines.append('')
    return public_answer('\n'.join(lines)) + '\n'


def version_snapshot(version, evidence):
    copy = deepcopy(version)
    copy["evidence"] = {k: deepcopy(v) for k, v in evidence.items() if v.get("context") == context_key(version["requirements"])}
    copy["guide"] = make_guide(copy, copy["evidence"])
    return copy


def get_version(state, number):
    version = next((v for v in state.get("versions", []) if v["version"] == number), None)
    if not version:
        return None
    return make_guide(version, version.get("evidence", {k: v for k, v in state.get("evidence", {}).items() if k in version.get("evidence_ids", [])}))


GUIDE_CSS = """*{box-sizing:border-box}body{margin:0;background:#f4f5ef;color:#243b35;font-family:system-ui,'Microsoft YaHei',sans-serif;line-height:1.7}main{max-width:1000px;margin:auto;padding:36px 24px}header{margin-bottom:28px}h1{font-size:clamp(28px,5vw,42px);line-height:1.25}h2{font-size:21px;margin:0 0 16px}p{margin:8px 0}section{background:white;border:1px solid #dce3d9;border-radius:16px;padding:24px;margin:20px 0;min-width:0}ul{list-style:none;margin:0;padding:0}li{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0;margin:12px 0;padding-bottom:12px;border-bottom:1px solid #edf0e9}li:last-child{border:0;padding-bottom:0}.overview ul,.budget ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.overview li,.budget li{background:#f1f5ee;border:0;border-radius:10px;padding:14px;margin:0}.day li{border-left:3px solid #67927e;padding-left:16px}a{color:#236d57;overflow-wrap:anywhere}a:focus-visible,summary:focus-visible{outline:3px solid #b05e14;outline-offset:4px}.download{display:inline-block;background:#245b49;color:white;padding:10px 18px;border-radius:10px;text-decoration:none}.muted{color:#53645b}summary{cursor:pointer;font-size:21px;font-weight:600}@media(max-width:600px){main{padding:20px 16px}section{padding:18px 16px}.overview ul,.budget ul{grid-template-columns:minmax(0,1fr)}}"""
GUIDE_CSS += '.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dce3d9;padding:10px;text-align:left;vertical-align:top;min-width:85px;overflow-wrap:anywhere}th{background:#f1f5ee}'
GUIDE_CSS += '.pitfalls{background:#fff5f4;border-color:#f0c4c0}.pitfalls h2{color:#a02a20}.verify td:first-child{min-width:120px}'


def render_guide(guide, pdf_url):
    guide = public_guide(guide)
    def text(value):
        return escape(str(value), quote=True)
    parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(guide["title"])}</title><style>{GUIDE_CSS}</style></head><body><main>',
        f'<header><p>TRAVELMATE · 旅行规划</p><h1>{text(guide["title"])}</h1><p class="muted">版本 {guide["version"]} · 保存于 {text(guide["saved_at"])}</p><p>{text(guide["notice"])}</p><a class="download" href="{text(pdf_url)}">下载这版攻略 PDF</a> <a href="{text(pdf_url.removesuffix("/pdf") + "/md")}">下载 Markdown</a></header>']
    for section in guide["sections"]:
        parts.append(f'<section class="{text(section["kind"])}">')
        if section["kind"] == "sources":
            parts.append(f'<details><summary>{text(section["title"])}</summary>')
        else:
            title = text(section['title'])
            if section['kind'] == 'day':
                title = title.replace(' · 天气', '<br>天气', 1)
            parts.append(f'<h2>{title}</h2>')
        if section.get('columns'):
            parts.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th scope="col">' + text(value) + '</th>' for value in section['columns']) + '</tr></thead><tbody>')
            for row in section['rows']:
                parts.append('<tr>' + ''.join('<td>' + text(value).replace('\n', '<br>') + '</td>' for value in row) + '</tr>')
            parts.append('</tbody></table></div>')
        parts.append('<ul>')
        for item in section["items"]:
            parts.append('<li>' + text(item["text"]))
            url = safe_url(item.get("link"))
            if url:
                parts.append(f'<br><a href="{text(url)}" target="_blank" rel="noopener noreferrer">{text(item.get("link_label", "公开来源"))}</a>')
            parts.append('</li>')
        parts.append('</ul>')
        if section["kind"] == "sources":
            parts.append('</details>')
        parts.append('</section>')
    return ''.join(parts) + '</main></body></html>'
