"""One frozen public document shared by the preview and PDF."""
import re
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import urlencode

from travelmate.evidence import safe_url, check_reference, context_key
from travelmate.public import public_data
from travelmate.workflow import budget_total, time_label, travel_label, cost_label, total_cost_label, TIME_NOTICE


def map_link(record, name):
    value = record.get("location")
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", value):
        return None
    lon, lat = map(float, value.split(","))
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        return None
    return "https://uri.amap.com/marker?" + urlencode({"position": value, "name": name, "coordinate": "gaode", "callnative": "0"})


def display_time(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M（北京时间）")


def make_guide(version, evidence):
    req, plan = version["requirements"], version["plan"]
    if not version.get("saved_at"):
        evidence = {}
    saved = version.get("saved_at") or "未记录（历史版本）"
    asof = datetime.fromisoformat(version.get("saved_at") or "1970-01-01T00:00:00+00:00")
    if asof.tzinfo is None:
        asof = asof.replace(tzinfo=timezone.utc)
    sections = []
    def section(title, texts, kind="notes"):
        items = [{"text": text} if isinstance(text, str) else text for text in texts]
        sections.append({"title": title, "kind": kind, "items": items})
    total = round(plan["other_cost"] + sum(s["cost"] for d in plan["days"] for s in d["stops"]), 2)
    displayed_total = total_cost_label([s for d in plan['days'] for s in d['stops']], req, evidence, plan['other_cost'], asof)
    scope = "人均" if req.get("budget_scope") == "per_person" else "全员"
    section("旅行概览", [f"{req['days']}天 · {req['travelers']}人 · {req.get('start_date') or '日期未定，按第几天展示'}",
        f"出发地：{req.get('origin') or '待定'}；目的地：{req['destination']}",
        f"用户预算：{scope}{req['budget']:.2f} {req.get('budget_currency') or 'CNY'}；全员预算{budget_total(req):.2f}",
        f"预算包含：{req.get('budget_includes') or '旧方案未记录，请确认'}",
        f"已列项目全员费用：{displayed_total}",
        f"偏好：{req.get('preferences') or '未记录'}"], "overview")
    if plan.get("time_granularity") == "period":
        section("时间安排说明", [TIME_NOTICE])
    costs = []
    for i, day in enumerate(plan["days"], 1):
        items = []
        for stop in day["stops"]:
            link = None
            ref = stop.get("fact_refs", {}).get("place")
            if ref and not check_reference(evidence, ref, "place", stop["place"], req, asof):
                link = map_link(evidence[ref], stop["place"])
            mode = {"unknown": "方式待定", "walking": "步行", "driving": "驾车", "transit": "公交/地铁", "rail": "铁路", "flight": "飞机", "ferry": "轮渡"}[stop.get("transport_mode", "unknown")]
            text = f"{time_label(plan, stop)} {stop['place']}（{stop['city']}）\n交通衔接：{mode}，{travel_label(stop)}；全员费用：{cost_label(stop, req, evidence, asof)}。\n{stop.get('notes', '')}\n"
            if stop.get("opening_hours"):
                text += "\n开放时间参考：" + stop["opening_hours"]
            items.append({"text": text, "link": link, "link_label": "查看地图位置（非路线校验）"})
            costs.append(f"第{i}天 · {stop['place']}：{cost_label(stop, req, evidence, asof)}")
        section(day.get("date") or f"第{i}天", items, "day")
    traffic = []
    for segment in plan.get("rail_segments", []):
        t = segment["ticket"]
        traffic.append(f"{t.get('start_train_code')} {t.get('from_station')} → {t.get('to_station')}，{t.get('start_date')} {t.get('start_time')}出发，{t.get('arrive_time')}到达。第三方MCP查询参考，余票票价以12306下单页面为准，不保证出票。")
    for b in req.get("bookings", []):
        traffic.append("已订安排：" + b["description"] + (f"，第{b['day']}天" if b.get("day") else "") + (f" {b['departure']}出发" if b.get("departure") else ""))
    if req.get("return_deadline"):
        traffic.append("返程时限：最后一天" + req["return_deadline"])
    if not req.get("origin"):
        traffic.append("出发地未定，往返大交通费用与时间未完成校验，当前合计不能视为全旅程预算已满足。")
    section("交通与已订安排", traffic or ["未记录额外交通安排；市内衔接见每日时间线。"])
    section("预算分项", [*costs, "其他费用：无法查询。", f"已列项目合计：{displayed_total}。无法查询不代表免费。"], "budget")
    section("备选安排", [a["trigger"] + " → " + a["action"] + "；额外费用：无法查询" for a in plan.get("alternatives", [])] or ["本版未记录具体备选；高风险安排需在出发前进一步确认。"])
    weather_items = []
    for record in evidence.values():
        if record.get("kind") == "weather_forecast" and record.get("context") == context_key(req):
            row = record["value"]
            weather_items.append(f"{row.get('date')}：白天{row.get('dayweather') or '未提供'}，夜间{row.get('nightweather') or '未提供'}；温度{row.get('nighttemp') or '未知'}至{row.get('daytemp') or '未知'}℃。预报发布时间：{row.get('reporttime') or '未提供'}；预报不代表保证。")
    if weather_items:
        section("天气预报", weather_items + ["未列日期未获得预报；出发前重新查询，遇雨按备选调整。"])
    section("行前提醒", plan.get("reminders", []) or ["开放时间、预约、天气与票价请在出发前重新核实。"])
    report = version.get("review", {})
    section("检查与仍待确认事项", [x["location"] + "：" + x["basis"] + "；" + x["suggestion"] for x in report.get("issues", [])] or ["保存时未记录阻塞问题；这不代表未查询事实已被核实。"])
    sources = []
    seen = set()
    for record in evidence.values():
        if record.get("context") != context_key(req):
            continue
        label = {"success": "查询匹配" if record["verification"] == "matched" else "文档参考", "empty": "无结果", "failed": "查询失败", "out_of_range": "超查询范围"}[record["query_status"]]
        key = (record["title"], label, record.get("url"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({"text": f"{record['title']} · {label} · 查询时间{display_time(record['queried_at'])}；核验有效期截至{display_time(record['expires_at'])}",
                        "link": safe_url(record.get("url")), "link_label": "公开来源"})
    section("来源与核实状态", sources or ["本版无可用查询记录，相关信息待核实。"], "sources")
    return public_data({"title": f"{req['destination']}旅行攻略", "version": version["version"], "saved_at": display_time(saved) if version.get("saved_at") else saved,
        "notice": "这是保存时的方案快照；查询时已核实不表示当前仍有效，出发前需再次确认。", "total": total, "sections": sections})


def version_snapshot(version, evidence):
    copy = deepcopy(version)
    copy["evidence"] = {k: deepcopy(v) for k, v in evidence.items() if v.get("context") == context_key(version["requirements"])}
    copy["guide"] = make_guide(copy, copy["evidence"])
    return copy


def get_version(state, number):
    version = next((v for v in state.get("versions", []) if v["version"] == number), None)
    if not version:
        return None
    return version.get("guide") or make_guide(version, version.get("evidence", {k: v for k, v in state.get("evidence", {}).items() if k in version.get("evidence_ids", [])}))


GUIDE_CSS = """*{box-sizing:border-box}body{margin:0;background:#f4f5ef;color:#243b35;font-family:system-ui,'Microsoft YaHei',sans-serif;line-height:1.7}main{max-width:1000px;margin:auto;padding:36px 24px}header{margin-bottom:28px}h1{font-size:clamp(28px,5vw,42px);line-height:1.25}h2{font-size:21px;margin:0 0 16px}p{margin:8px 0}section{background:white;border:1px solid #dce3d9;border-radius:16px;padding:24px;margin:20px 0;min-width:0}ul{list-style:none;margin:0;padding:0}li{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0;margin:12px 0;padding-bottom:12px;border-bottom:1px solid #edf0e9}li:last-child{border:0;padding-bottom:0}.overview ul,.budget ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.overview li,.budget li{background:#f1f5ee;border:0;border-radius:10px;padding:14px;margin:0}.day li{border-left:3px solid #67927e;padding-left:16px}a{color:#236d57;overflow-wrap:anywhere}a:focus-visible,summary:focus-visible{outline:3px solid #b05e14;outline-offset:4px}.download{display:inline-block;background:#245b49;color:white;padding:10px 18px;border-radius:10px;text-decoration:none}.muted{color:#53645b}summary{cursor:pointer;font-size:21px;font-weight:600}@media(max-width:600px){main{padding:20px 16px}section{padding:18px 16px}.overview ul,.budget ul{grid-template-columns:minmax(0,1fr)}}"""


def render_guide(guide, pdf_url):
    def text(value):
        return escape(str(value), quote=True)
    parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(guide["title"])}</title><style>{GUIDE_CSS}</style></head><body><main>',
        f'<header><p>TRAVELMATE · 旅行规划</p><h1>{text(guide["title"])}</h1><p class="muted">版本 {guide["version"]} · 保存于 {text(guide["saved_at"])}</p><p>{text(guide["notice"])}</p><a class="download" href="{text(pdf_url)}">下载这版攻略 PDF</a></header>']
    for section in guide["sections"]:
        parts.append(f'<section class="{text(section["kind"])}">')
        if section["kind"] == "sources":
            parts.append(f'<details><summary>{text(section["title"])}</summary>')
        else:
            parts.append(f'<h2>{text(section["title"])}</h2>')
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
