"""One frozen public document shared by the preview and exports."""
from base64 import b64encode
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from html import escape
from pathlib import Path

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


def day_span(plan, day):
    """当天出发与结束的钟点；分时段行程取建议窗口的首尾，不编精确时刻。"""
    stops = day['stops']

    def edge(stop, index):
        if index == 0 and stop.get('start'):
            return stop['start']
        if index == 1 and stop.get('end'):
            return stop['end']
        window = stop.get('suggested_window') or ''
        parts = window.split('–') if '–' in window else window.split('-')
        if len(parts) == 2:
            return parts[index].strip()
        return ''

    first, last = edge(stops[0], 0), edge(stops[-1], 1)
    if first and last:
        return f'{first} 出发 · {last} 结束'
    if plan.get('time_granularity') == 'period':
        return f'{time_label(plan, stops[0])}起，{time_label(plan, stops[-1])}结束'
    return ''


def day_travel_note(day):
    """在途时间合计；有缺值时标明几段待确认，不用 0 顶替。"""
    values = [stop.get('travel_minutes') for stop in day['stops']]
    known = [value for value in values if value is not None]
    if not known:
        return ''
    missing = len(values) - len(known)
    return f'在途约 {sum(known)} 分钟' + (f'（{missing} 段待确认）' if missing else '')


def tier_total_label(tier, requirements):
    """档位总额，能算人均就并进同一格，不加列，PDF 宽度不用跟着改。"""
    if tier.get('total') is None:
        return '待核实'
    amount = tier['total']
    text = f'约¥{amount:.0f}'
    travelers = requirements.get('travelers') or 0
    return text + (f'（人均¥{amount / travelers:.0f}）' if travelers > 1 else '')


SOURCE_NAMES = {'search_knowledge': '本地知识库', 'search_web': '网页资料搜索',
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
    overview_rows = [
        ['路线', route], ['人数与天数', f'{req["travelers"]}人 · {req["days"]}天'],
        ['日期', req.get('start_date') or '日期未定，按第几天展示'],
        ['预算', f'{scope} {req["budget"]:.2f} {req.get("budget_currency") or "CNY"}；全员预算{budget_total(req):.2f}'],
        ['预算包含', req.get('budget_includes') or '旧方案未记录，请先确认范围'],
        ['旅行偏好', req.get('preferences') or '未说明'],
        ['行动与饮食', f'{req.get("mobility") or "行动限制未说明，先预留休息"}；{req.get("dietary") or "忌口未说明，点单前确认"}']]
    if req.get('budget') and (req.get('budget_currency') or 'CNY') == 'CNY' and '无法查询' not in displayed_total:
        balance = round(budget_total(req) - total, 2)
        overview_rows.append(['预算余量（按已列金额）',
                              f'约¥{balance:.2f}' if balance >= 0 else f'已超约¥{-balance:.2f}，需减项目或降档'])
    section('旅行概览', kind='overview', columns=['项目', '安排'], rows=overview_rows)
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
                 tier_total_label(tier, req),
                 tier.get('note') or '按档位替换住宿与餐标，行程不用重做'] for tier in tiers]
        section('预算三档对照', ['三档只换住宿、交通和餐标，行程顺序不变；金额为全员估算，标注待核实的以官方渠道为准。']
                + ([note] if note else []),
                'budget', ['档位', '住宿', '交通', '餐饮', '全员总计', '说明'], rows)
    segments = [segment['ticket'] for segment in plan.get('rail_segments', [])]
    if segments:
        rows = []
        for t in segments:
            price = t.get('prices') or ''
            if isinstance(price, (list, dict)):
                price = str(price)
            rows.append([f'{t.get("from_station") or ""} → {t.get("to_station") or ""}',
                         t.get('start_train_code') or '待定',
                         t.get('start_date') or '待定',
                         t.get('start_time') or '待核实',
                         t.get('arrive_time') or '待核实',
                         price or '待核实'])
        section('交通班次', ['第三方 MCP 查询的参考班次，余票、票价与是否可购买以 12306 下单页面为准。'],
                'traffic', ['行程', '车次', '日期', '出发', '到达', '参考票价'], rows)
    traffic = []
    if not segments:
        traffic.append('未绑定具体车次或航班；日期与交通方式确定后查询，不把历史时刻或价格当作本次可购买方案。')
    traffic += ['已订安排：' + booking['description'] + (f'，第{booking["day"]}天' if booking.get('day') else '') + (f' {booking["departure"]}出发' if booking.get('departure') else '') for booking in req.get('bookings', [])]
    if req.get('return_deadline'):
        traffic.append('最后一天返程时限：' + req['return_deadline'] + '，提前取行李并预留交通与进站时间。')
    if traffic:
        section('交通与已订安排', traffic)
    section('住哪里更顺路', plan.get('lodging') or ['优先结合当日游玩片区选择交通方便的住宿，核对到站交通、取消条款和房型；未查到房态与价格时不指定可订酒店。'])
    if plan.get('time_granularity') == 'period':
        section('时间安排说明', [TIME_NOTICE])
    for i, day in enumerate(plan['days'], 1):
        modes = {'unknown': '方式待定', 'walking': '步行', 'driving': '驾车', 'transit': '公交/地铁', 'rail': '铁路', 'flight': '飞机', 'ferry': '轮渡'}
        rows = [[time_label(plan, stop), stop['place'], stop.get('notes') or '按预约和体力调整', modes[stop.get('transport_mode', 'unknown')] + '，' + travel_label(stop), cost_label(stop, req, evidence, asof)] for stop in day['stops']]
        meals = [f'{food.get("meal", "不限")}：{food["name"]}' for food in plan.get('foods', []) if food.get('day') == i]
        # 表格里时段列很窄（PDF 只有 44pt），把当天起止与在途时间放到表格下面一行汇总。
        summary = [f'本日 {len(day["stops"])} 个安排']
        span = day_span(plan, day)
        if span:
            summary.append(span)
        travel = day_travel_note(day)
        if travel:
            summary.append(travel)
        summary.append('已列费用 ' + total_cost_label(day['stops'], req, evidence, now=asof))
        notes = [' · '.join(summary)] + (['当日美食：' + '；'.join(meals)] if meals else [])
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
    sources, seen, used_knowledge = [], set(), False
    for record in evidence.values():
        if record.get('context') != context_key(req):
            continue
        label = {'success': '查询匹配' if record['verification'] == 'matched' else '文档参考', 'empty': '无结果', 'failed': '查询失败', 'out_of_range': '超查询范围'}[record['query_status']]
        key = (record['title'], label, record.get('url'))
        if key in seen:
            continue
        seen.add(key)
        tool = record.get('tool')
        if tool == 'search_knowledge':
            name = f'本地知识库「{record["title"]}」'
            used_knowledge = used_knowledge or record['query_status'] == 'success'
        elif tool == 'search_web':
            name = f'网页资料「{record["title"]}」'
        else:
            name = {'search_places': '高德地点查询', 'search_weather': '天气预报查询',
                    'search_train_tickets': '铁路车次查询'}.get(tool, record['title'])
        sources.append({'text': f'{name} · {label} · 查询时间{display_time(record["queried_at"])}', 'link': safe_url(record.get('url')), 'link_label': '公开来源'})
    intro = ['本版参考了本地知识库文档，其余为联网检索与工具查询结果。'] if used_knowledge else []
    section('参考来源', intro + (sources or ['本版没有可追溯的公开查询结果，不将具体报价或营业状态标为已核实。']), 'sources')
    return public_guide(public_data({'title': f'{route} · {req["days"]}天旅行攻略', 'version': version['version'],
        'saved_at': display_time(version['saved_at']) if version.get('saved_at') else '未记录（历史版本）',
        'hero': hero_image(req, plan),
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


GUIDE_CSS = """*{box-sizing:border-box}body{margin:0;background:#f4f7f4;color:#1f2d2a;
font:16px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}main{max-width:860px;margin:0 auto;padding:20px 16px 56px}
.hero{position:relative;border-radius:24px;overflow:hidden;color:#fff;margin-bottom:18px;box-shadow:0 12px 32px rgba(16,40,32,.16)}
.hero img{display:block;width:100%;height:300px;object-fit:cover}
.hero-body{position:relative;margin-top:-118px;padding:0 26px 26px;
background:linear-gradient(180deg,rgba(6,26,22,0) 0%,rgba(6,26,22,.55) 40%,rgba(6,26,22,.88) 100%)}
.eyebrow{margin:0;font-size:12px;letter-spacing:.16em;opacity:.85}
h1{font-size:clamp(24px,4.6vw,34px);line-height:1.26;margin:6px 0 8px}
.lede{margin:0 0 12px;font-size:14px;opacity:.92}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px;padding:0}
.chips span{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:3px 12px;font-size:13px}
.actions{display:flex;gap:10px;flex-wrap:wrap}
.btn{background:#fff;color:#0f5d55;text-decoration:none;padding:9px 18px;border-radius:999px;font-size:14px;font-weight:600}
.btn.ghost{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.5)}
.card{background:#fff;border:1px solid #e2e8e3;border-radius:18px;padding:20px;margin:16px 0;
box-shadow:0 1px 2px rgba(16,40,32,.06),0 12px 32px rgba(16,40,32,.06);min-width:0}
h2{font-size:19px;margin:0 0 14px;padding-left:12px;border-left:4px solid #0f766e;line-height:1.3}
ul{list-style:none;margin:0;padding:0}
li{margin:10px 0;padding-bottom:10px;border-bottom:1px dashed #e2e8e3;white-space:pre-wrap;overflow-wrap:anywhere;min-width:0}
li:last-child{border:0;padding-bottom:0}
.overview ul,.budget ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.overview li,.budget li{background:#f1f5f1;border:0;border-radius:12px;padding:14px;margin:0}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px;margin-top:10px}
th,td{border:1px solid #e2e8e3;padding:10px;text-align:left;vertical-align:top;min-width:88px;overflow-wrap:anywhere}
th{background:#eef4f1;font-weight:600}
tbody tr:nth-child(even){background:#fafbf9}
a{color:#0f5d55;overflow-wrap:anywhere}
a:focus-visible,summary:focus-visible{outline:3px solid #b45309;outline-offset:4px}
.muted{color:#5c6b64}
.pitfalls{background:#fff6f5;border-color:#f2c9c4}.pitfalls h2{color:#a02a20;border-left-color:#dc2626}
.verify{background:#fffdf5}.verify h2{border-left-color:#d97706}
.sources{background:#f7f9f7}
summary{cursor:pointer;font-size:19px;font-weight:600}
.section-notes{margin-top:12px}
.section-notes summary{font-size:14px;color:#0f5d55;padding:8px 0}
.section-notes[open] summary{margin-bottom:6px}
footer{margin-top:26px;text-align:center;font-size:13px;color:#5c6b64}
.tl{list-style:none;margin:0;padding:0}
.tl-item{display:grid;grid-template-columns:92px minmax(0,1fr);gap:12px;margin:0;padding:0;border:0}
.tl-time{margin:0;font-size:13px;font-weight:600;color:#0f5d55;white-space:pre-wrap}
.tl-body{position:relative;padding:0 0 14px 16px;border-left:2px solid #d7e3dd}
.tl-body:before{content:"";position:absolute;left:-6px;top:6px;width:10px;height:10px;border-radius:50%;background:#0f766e}
.tl-item:last-child .tl-body{border-left-color:transparent;padding-bottom:0}
.tl-place{margin:0 0 4px;font-weight:600}
.tl-body p{margin:0 0 4px;font-size:14px}
.tl-meta{color:#5c6b64;font-size:13px}
.tiers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.tier{background:#f1f5f1;border-radius:14px;padding:14px;min-width:0}
.tier:first-child{background:#e8f3ee;box-shadow:inset 0 0 0 1px #bcd9cc}
.tier-name{margin:0;font-size:13px;letter-spacing:.06em;color:#0b4f48}
.tier-price{margin:2px 0 10px;font-size:20px;font-weight:700;color:#0f5d55}
.tier dl{margin:0;font-size:13px}
.tier dt{color:#5c6b64;margin-top:8px}
.tier dd{margin:0}
.tier-note{margin:10px 0 0;font-size:12px;color:#5c6b64}
@media(max-width:640px){main{padding:14px 12px 40px}.hero img{height:210px}.hero-body{margin-top:-96px;padding:0 16px 18px}
.card{padding:16px;border-radius:16px}.overview ul,.budget ul{grid-template-columns:minmax(0,1fr)}
.tiers{grid-template-columns:minmax(0,1fr)}.tl-item{grid-template-columns:74px minmax(0,1fr);gap:10px}}"""

DESTINATION_IMAGES = (
    ('mountains.webp', ('九寨', '黄龙', '山', '峰', '沟', '雪', '高原', '草原', '峡', '瀑布')),
    ('coast.webp', ('海', '岛', '沙滩', '厦门', '三亚', '青岛', '大连', '舟山', '鼓浪屿', '湾', '湖')),
    ('town.webp', ('古镇', '老街', '巷', '城', '寺', '庙', '园林', '村', '胡同')),
)


def hero_image(requirements, plan=None):
    """按目的地挑一张内置示意图；没匹配就用城镇图，绝不外链图片。"""
    text = ' '.join(str(value) for value in (
        requirements.get('destination'), requirements.get('preferences'),
        requirements.get('interests'), (plan or {}).get('summary')) if value)
    for name, keywords in DESTINATION_IMAGES:
        if any(word in text for word in keywords):
            return '/assets/visual/' + name
    return '/assets/visual/town.webp'


def day_timeline(section, text):
    """日程表在网页里换成时间轴：同一份数据，纵向读比 5 列横表快。PDF 仍用表格。"""
    out = ['<ol class="tl">']
    for row in section['rows']:
        when, place, detail, travel, cost = (list(row) + [''] * 5)[:5]
        out.append(f'<li class="tl-item"><p class="tl-time">{text(when)}</p><div class="tl-body">'
                   f'<p class="tl-place">{text(place)}</p>'
                   + (f'<p>{text(detail).replace(chr(10), "<br>")}</p>' if detail else '')
                   + f'<p class="tl-meta">{text(travel)} · {text(cost)}</p></div></li>')
    return ''.join(out) + '</ol>'


def tier_cards(section, text):
    """三档对照在网页里换成并排卡片，价格单独立字号，差额一眼能比。"""
    out = ['<div class="tiers">']
    for row in section['rows']:
        cell = dict(zip(section['columns'], row))
        out.append('<div class="tier">'
                   f'<p class="tier-name">{text(cell.get("档位", ""))}</p>'
                   f'<p class="tier-price">{text(cell.get("全员总计", ""))}</p>'
                   '<dl>'
                   + ''.join(f'<dt>{label}</dt><dd>{text(cell.get(label, ""))}</dd>'
                             for label in ('住宿', '交通', '餐饮'))
                   + '</dl>'
                   + (f'<p class="tier-note">{text(cell.get("说明", ""))}</p>' if cell.get('说明') else '')
                   + '</div>')
    return ''.join(out) + '</div>'


def render_guide(guide, pdf_url=None):
    guide = public_guide(guide)
    def text(value):
        return escape(str(value), quote=True)
    hero = guide.get('hero') or '/assets/visual/town.webp'
    actions = ''
    if pdf_url is None:
        image = Path(__file__).with_name('images') / Path(hero).name
        hero = 'data:image/webp;base64,' + b64encode(image.read_bytes()).decode('ascii')
    else:
        path = pdf_url.removesuffix('/pdf')
        actions = (f'<div class="actions"><a class="btn" href="{text(pdf_url)}">下载这版 PDF</a>'
                   f'<a class="btn ghost" href="{text(path)}/md">下载 Markdown</a>'
                   f'<a class="btn ghost" href="{text(path)}/html">下载 HTML</a></div>')
    parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(guide["title"])}</title><style>{GUIDE_CSS}</style></head><body><main>',
        f'<header class="hero"><img src="{text(hero)}" alt="目的地风景示意图"><div class="hero-body">',
        f'<p class="eyebrow">TRAVELMATE · 图文攻略</p><h1>{text(guide["title"])}</h1>',
        f'<p class="lede">{text(guide["notice"])}</p>',
        f'<p class="chips"><span>版本 {text(guide["version"])}</span><span>{text(guide["saved_at"])}</span>'
        f'<span>合计 {text(guide["total"])}</span></p>',
        actions, '</div></header>']
    for section in guide["sections"]:
        parts.append(f'<section class="card {text(section["kind"])}">')
        if section["kind"] == "sources":
            parts.append(f'<details><summary>{text(section["title"])}</summary>')
        else:
            title = text(section['title'])
            if section['kind'] == 'day':
                title = title.replace(' · 天气', '<br>天气', 1)
            parts.append(f'<h2>{title}</h2>')
        if section.get('columns'):
            if section['kind'] == 'day' and section['columns'][0] == '时段':
                parts.append(day_timeline(section, text))
            elif section['title'] == '预算三档对照':
                parts.append(tier_cards(section, text))
            else:
                parts.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th scope="col">' + text(value) + '</th>' for value in section['columns']) + '</tr></thead><tbody>')
                for row in section['rows']:
                    parts.append('<tr>' + ''.join('<td>' + text(value).replace('\n', '<br>') + '</td>' for value in row) + '</tr>')
                parts.append('</tbody></table></div>')
        fold_notes = section['kind'] == 'budget' and section['items']
        if fold_notes:
            parts.append('<details class="section-notes"><summary>注意事项</summary>')
        parts.append('<ul>')
        for item in section["items"]:
            parts.append('<li>' + text(item["text"]))
            url = safe_url(item.get("link"))
            if url:
                parts.append(f'<br><a href="{text(url)}" target="_blank" rel="noopener noreferrer">{text(item.get("link_label", "公开来源"))}</a>')
            parts.append('</li>')
        parts.append('</ul>')
        if fold_notes or section["kind"] == "sources":
            parts.append('</details>')
        parts.append('</section>')
    parts.append('<footer>图为目的地示意图，非实景；价格与开放状态以出行时官方信息为准</footer>')
    return ''.join(parts) + '</main></body></html>'
