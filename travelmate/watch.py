"""行前保鲜：出发前按同一 context_key 重跑查询，只报告哪条变了、差多少。

复用已有的 versions 快照与 evidence.expires_at：依据还没过期就不查，过期且用得上的
才查，因此每版每次复核控制在 2–3 次检索调用以内。
"""
import logging
import os
import re
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from threading import Event, Thread

from langchain_core.messages import AIMessage

from travelmate.evidence import context_key, same_label

CHINA = timezone(timedelta(hours=8))
PRICE = re.compile(r"(?:门票|票价|成人票|全价票|通票|套票|观光票)[^0-9]{0,8}(\d{1,4}(?:\.\d{1,2})?)")
ANY_PRICE = re.compile(r"[¥￥]\s*(\d{1,4}(?:\.\d{1,2})?)")
HOURS = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)\s*(?:-|–|—|~|～|至|到)\s*"
                   r"([01]?\d|2[0-3])[:：]([0-5]\d)")
HISTORY_LIMIT = 5


def lead_days():
    return max(0, int(os.getenv("WATCH_LEAD_DAYS") or 3))


def max_queries():
    return max(1, min(6, int(os.getenv("WATCH_MAX_QUERIES") or 3)))


def interval_hours():
    return max(0.0, float(os.getenv("WATCH_INTERVAL_HOURS") or 24))


def scheduler_minutes():
    return max(1.0, float(os.getenv("WATCH_SCHEDULER_MINUTES") or 60))


def scheduler_enabled():
    return (os.getenv("WATCH_SCHEDULER") or "1").strip().lower() not in ("0", "off", "false", "no")


def today():
    return datetime.now(CHINA).date()


def _moment(value):
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _money(value):
    return f"¥{float(value):g}"


def _number(value):
    try:
        return float(str(value).replace(",", "").replace("元", "").strip())
    except (TypeError, ValueError):
        return None


def _clock(raw):
    return f"{int(raw[0]):02d}:{raw[1]}-{int(raw[2]):02d}:{raw[3]}"


def current_version(workflow):
    versions = workflow.get("versions") or []
    if not versions:
        return None
    number = workflow.get("version")
    found = next((item for item in versions if item.get("version") == number), None)
    return found or versions[-1]


def eligible(workflow, now=None):
    """出发日在前 lead_days 天内的已保存版本才需要复核。"""
    version = current_version(workflow)
    if not version or not (version.get("plan") or {}).get("days"):
        return None
    start = (version.get("requirements") or {}).get("start_date")
    try:
        departure = date.fromisoformat(str(start))
    except (TypeError, ValueError):
        return None
    days_left = (departure - (now.astimezone(CHINA).date() if now else today())).days
    return version if 0 <= days_left <= lead_days() else None


def recently_checked(workflow, version, now=None):
    last = workflow.get("watch") or {}
    if last.get("version") != version.get("version"):
        return False
    checked = _moment(last.get("checked_at"))
    now = now or datetime.now(timezone.utc)
    return bool(checked and now - checked < timedelta(hours=interval_hours()))


def is_due(workflow, now=None):
    now = now or datetime.now(timezone.utc)
    version = eligible(workflow, now)
    return bool(version and not recently_checked(workflow, version, now))


def pick_price(text):
    """先找门票口径的数字，找不到才退回任何带币种的金额。"""
    for pattern in (PRICE, ANY_PRICE):
        for match in pattern.finditer(text or ""):
            value = _number(match.group(1))
            if value is not None and 0 < value <= 5000:
                return value
    return None


def hours_in(text):
    found = []
    for match in HOURS.finditer(text or ""):
        clock = _clock(match.groups())
        if clock not in found:
            found.append(clock)
    return found


def _stale(expires_at, now):
    moment = _moment(expires_at)
    return moment is None or moment < now


def _item(target, field, before, after, changed, delta=None, note="", source=None, unverified=False):
    return {"label": target["label"], "day": target.get("day"), "field": field,
            "before": before, "after": after, "delta": delta, "changed": bool(changed),
            "note": note, "source": source, "unverified": bool(unverified)}


def _delta(before, after):
    if before is None or after is None:
        return None
    change = after - before
    if abs(change) < 0.005:
        return None
    return ("涨 " if change > 0 else "降 ") + _money(abs(change))


def select_targets(version, evidence, now=None, limit=None):
    """按「车次 > 票价/开放时间 > 地点」排优先级，只挑依据过期的项，最多 limit 个。"""
    now = now or datetime.now(timezone.utc)
    limit = limit or max_queries()
    req = version.get("requirements") or {}
    plan = version.get("plan") or {}
    city = (req.get("destination") or "").strip()
    candidates = []

    def add(target, weight=0.0):
        record = evidence.get(target.pop("ref", None)) or {}
        target["expires_at"] = record.get("expires_at")
        target["weight"] = weight
        target["stale"] = _stale(target["expires_at"], now)
        candidates.append(target)

    for segment in plan.get("rail_segments") or []:
        ticket = segment.get("ticket") or {}
        query = (evidence.get(segment.get("evidence_id")) or {}).get("query") or {}
        if not (query.get("origin") and query.get("destination") and query.get("departure_date")):
            continue
        label = "{} → {} {}".format(ticket.get("from_station") or query["origin"],
                                   ticket.get("to_station") or query["destination"],
                                   ticket.get("start_train_code") or "").strip()
        add({"kind": "train", "tool": "search_train_tickets", "label": label, "day": None,
             "priority": 0, "baseline": ticket,
             "query": {key: query[key] for key in ("origin", "destination", "departure_date", "transport")
                       if query.get(key)},
             "ref": segment.get("evidence_id")}, 1e6)

    for day_no, day in enumerate(plan.get("days") or [], 1):
        for stop in day.get("stops") or []:
            refs = stop.get("fact_refs") or {}
            cost = float(stop.get("cost") or 0)
            if cost > 0 or stop.get("opening_hours") or refs.get("cost") or refs.get("opening_hours"):
                add({"kind": "price_hours", "tool": "search_web", "label": stop["place"], "day": day_no,
                     "priority": 1,
                     "query": {"query": f"{city}{stop['place']} 门票 开放时间".strip()},
                     "baseline": {"cost": cost, "cost_estimated": bool(stop.get("cost_estimated")),
                                  "opening_hours": stop.get("opening_hours")},
                     "ref": refs.get("cost") or refs.get("opening_hours")}, cost)
            if refs.get("place"):
                record = evidence.get(refs["place"]) or {}
                add({"kind": "place", "tool": "search_places", "label": stop["place"], "day": day_no,
                     "priority": 2,
                     "query": {"keyword": stop["place"], "city": city},
                     "baseline": {"name": record.get("value"), "address": record.get("address"),
                                  "location": record.get("location")},
                     "ref": refs["place"]}, 0.0)

    pending = [target for target in candidates if target.pop("stale")]
    pending.sort(key=lambda target: (target["priority"], -target["weight"]))
    chosen, seen = [], set()
    for target in pending:
        key = (target["kind"], target["label"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(target)
        if len(chosen) >= limit:
            break
    return chosen, len(pending)


def _train_items(target, data):
    ticket = target["baseline"]
    rows = [row for row in data.get("results") or [] if isinstance(row, dict)]
    code = str(ticket.get("start_train_code") or "")
    if not rows:
        return [_item(target, "车次", code or "未记录", "本次没有查到车次", True,
                      note="可能尚未开售、停运或查询失败，请到12306确认。")]
    same = [row for row in rows if str(row.get("start_train_code") or "") == code]
    if not same:
        return [_item(target, "车次", f"{code} {ticket.get('start_time') or ''}".strip(),
                      "本次未查到该车次", True,
                      note="同期还有其它车次在售，原车次可能改点或停运，请到12306确认。")]
    row = same[0]
    source = data.get("url")
    items = []
    for field, key, label in (("start_time", "start_time", "发车时刻"), ("arrive_time", "arrive_time", "到达时刻")):
        before, after = ticket.get(field), row.get(key)
        if before and after and str(before) != str(after):
            items.append(_item(target, label, str(before), str(after), True, note="车次时刻已调整。", source=source))
    old_prices = {str(seat.get("seat_name")): _number(seat.get("price"))
                  for seat in ticket.get("prices") or [] if isinstance(seat, dict)}
    new_prices = {str(seat.get("seat_name")): _number(seat.get("price"))
                  for seat in row.get("prices") or [] if isinstance(seat, dict)}
    for seat, before in old_prices.items():
        after = new_prices.get(seat)
        if after is None or before is None:
            continue
        if abs(after - before) >= 0.5:
            items.append(_item(target, f"{seat}票价", _money(before), _money(after), True,
                               delta=_delta(before, after), note="余票与票价以下单页为准。", source=source))
    if not items:
        items.append(_item(target, "车次", code, code, False, note="车次、时刻与票价与保存时一致。", source=source))
    return items


def _price_hours_items(target, data):
    rows = [row for row in data.get("results") or [] if isinstance(row, dict)]
    text = " ".join(str(row.get("content") or "") for row in rows)
    source = next((row.get("url") for row in rows if row.get("url")), None)
    base = target["baseline"]
    items = []
    price = pick_price(text)
    if price is None:
        items.append(_item(target, "门票", _money(base["cost"]) if base.get("cost") else "未记录",
                           "本次未取到价格", False, unverified=True,
                           note="公开资料里没有可对比的价格，请按官方购票页确认。", source=source))
    else:
        before = base.get("cost") or 0
        tolerance = max(5.0, before * 0.1)
        changed = (not before) or abs(price - before) >= tolerance
        label = "门票（原为估算）" if base.get("cost_estimated") else "门票"
        items.append(_item(target, label, _money(before) if before else "未记录", _money(price), changed,
                           delta=_delta(before or None, price),
                           note="原方案没有价格，本次取到参考价。" if not before
                           else "与保存时一致。" if not changed else "票价已变化，请以官方购票页为准。",
                           source=source))
    found = hours_in(text)
    old = hours_in(base.get("opening_hours"))
    if found:
        if old and set(found) != set(old):
            items.append(_item(target, "开放时间", " / ".join(old), " / ".join(found), True,
                               note="开放时段已变化，请以景区当日公告为准。", source=source))
        elif not old:
            items.append(_item(target, "开放时间", "未记录", " / ".join(found), True,
                               note="原方案没有开放时间，本次取到参考时段。", source=source))
        else:
            items.append(_item(target, "开放时间", " / ".join(old), " / ".join(found), False,
                               note="开放时段与保存时一致。", source=source))
    elif base.get("opening_hours"):
        items.append(_item(target, "开放时间", base["opening_hours"], "本次未取到", False, unverified=True,
                           note="没有可对比的开放时间，请按景区公告确认。", source=source))
    return items


def _place_items(target, data):
    base = target["baseline"]
    rows = [row for row in data.get("results") or [] if isinstance(row, dict)]
    if not rows:
        return [_item(target, "地点", base.get("name") or target["label"], "高德查不到该地点", True,
                      note="可能已改名、停业或关键词过窄，请在高德地图确认后再出发。")]
    row = rows[0]
    items = []
    name = row.get("name") or ""
    if name and base.get("name") and name != base["name"]:
        same = same_label(name, base["name"])
        items.append(_item(target, "地点名称", base["name"], name, not same,
                           note="写法不同但指向同一地点。" if same
                           else "地图上的地点名称已变化，请确认是否仍是同一处。"))
    address = row.get("address") or ""
    if address and base.get("address") and address != base["address"]:
        items.append(_item(target, "地址", base["address"], address, True, note="地址已变化，导航请用新地址。"))
    if not items:
        items.append(_item(target, "地点", base.get("name") or target["label"],
                           name or target["label"], False, note="地点仍在，地址与保存时一致。"))
    return items


EVALUATORS = {"train": _train_items, "price_hours": _price_hours_items, "place": _place_items}


def query_target(target, tools):
    tool = (tools or {}).get(target["tool"])
    if tool is None:
        return {"error": "查询工具不可用"}
    try:
        data = tool.invoke(target["query"])
    except Exception:
        logging.getLogger(__name__).info("Trip watch query %s failed", target["tool"])
        return {"error": "查询失败"}
    return data if isinstance(data, dict) else {"error": "返回格式异常"}


def evaluate(target, data):
    if data.get("error"):
        return [_item(target, "查询", "—", "本次未查到", False, unverified=True,
                      note=f"复核没有取到数据（{data['error']}），出发前请人工确认。")]
    return EVALUATORS[target["kind"]](target, data)


def snapshot_evidence(version, workflow):
    """只认与这一版条件同源的依据：context_key 不同说明是别的需求的查询结果。"""
    key = context_key(version.get("requirements") or {})
    source = version.get("evidence") or workflow.get("evidence") or {}
    scoped = {item: record for item, record in source.items()
              if not record.get("context") or record.get("context") == key}
    return scoped or source


def build_report(version, workflow, tools, now=None, force=False):
    now = now or datetime.now(timezone.utc)
    if not force and recently_checked(workflow, version, now):
        return None
    targets, pending = select_targets(version, snapshot_evidence(version, workflow), now)
    items, calls = [], 0
    for target in targets:
        items.extend(evaluate(target, query_target(target, tools)))
        calls += 1
    changed = [item for item in items if item["changed"]]
    unverified = [item for item in items if item["unverified"]]
    return {"version": version.get("version"), "checked_at": now.isoformat(),
            "start_date": (version.get("requirements") or {}).get("start_date"),
            "calls": calls, "items": items, "changed": changed, "unverified": unverified,
            "skipped": pending - len(targets),
            "summary": (f"重跑 {calls} 次查询，{len(changed)} 项有变动" if calls
                        else "依据仍在有效期内，本次没有需要重跑的查询")}


def _cn_time(value):
    moment = _moment(value)
    if moment is None:
        return "时间未记录"
    return moment.astimezone(CHINA).strftime("%m月%d日 %H:%M（北京时间）")


def _cell(value):
    return str("" if value is None else value).replace("|", "／").replace("\n", " ")


def markdown(report):
    if not report:
        return ""
    lines = [f"## 行前复核 · 出发前 {lead_days()} 天", "",
             f"版本 {report.get('version')} · {report.get('start_date') or '日期未定'} 出发 · "
             f"复核于 {_cn_time(report.get('checked_at'))}", ""]
    changed = report.get("changed") or []
    if changed:
        lines += [f"**{len(changed)} 项有变动，出发前请按新信息调整。**", "",
                  "| 项目 | 变动前 | 变动后 | 差额 |", "| --- | --- | --- | --- |"]
        for item in changed:
            where = f"第{item['day']}天 " if item.get("day") else ""
            lines.append(f"| {_cell(where)}{_cell(item['label'])} · {_cell(item['field'])} | "
                         f"{_cell(item['before'])} | {_cell(item['after'])} | {_cell(item['delta'] or '—')} |")
        lines.append("")
    else:
        lines += ["**本次复核没有发现变动。**", ""]
    stable = [item for item in report.get("items") or [] if not item["changed"] and not item["unverified"]]
    if stable:
        names = list(dict.fromkeys(f"{item['label']}（{item['field']}）" for item in stable))
        lines += ["未变：" + "、".join(names[:8]) + ("等" if len(names) > 8 else ""), ""]
    unverified = report.get("unverified") or []
    if unverified:
        names = list(dict.fromkeys("第%d天 %s" % (item["day"], item["label"]) if item.get("day") else item["label"]
                                   for item in unverified))
        lines += ["没查到可对比的数据：" + "、".join(names[:8]) + "；这几项仍按待核实处理。", ""]
    if report.get("skipped"):
        lines += [f"另有 {report['skipped']} 项本轮没有重跑（每次最多 {max_queries()} 次检索），"
                  "出发前一天会再复核一次。", ""]
    sources = list(dict.fromkeys(item["source"] for item in report.get("items") or [] if item.get("source")))
    if sources:
        lines += ["核对来源：" + "、".join(f"[来源{index}]({url})" for index, url in enumerate(sources[:3], 1)), ""]
    lines.append("复核只比较公开资料与保存时的记录，最终以官方购票页和景区公告为准。")
    return "\n".join(lines)


def record(workflow, report):
    history = [*workflow.get("watch_history", []), report][-HISTORY_LIMIT:]
    return {**workflow, "watch": report, "watch_history": history}


def status(workflow):
    version = current_version(workflow)
    number = (version or {}).get("version")
    report = workflow.get("watch") or None
    # 只展示当前版本的复核结果：换了版本，旧的 diff 就不该再显示。
    if report and report.get("version") != number:
        report = None
    return {"due": is_due(workflow), "eligible": bool(eligible(workflow)),
            "version": number,
            "start_date": ((version or {}).get("requirements") or {}).get("start_date"),
            "lead_days": lead_days(),
            "report": ({**report, "markdown": markdown(report)} if report else None)}


def check_session(agent, session_id, tools=None, lock=None, force=False, now=None):
    """先算（联网），再抢锁写回；期间换了版本就放弃，让下一轮复核新版本。"""
    config = {"configurable": {"thread_id": session_id}}
    workflow = agent.get_state(config).values.get("workflow") or {}
    version = eligible(workflow, now)
    if version is None:
        return None
    report = build_report(version, workflow, tools, now, force)
    if report is None:
        return None
    if lock is None:
        _store(agent, config, session_id, workflow, report)
        return report
    if not lock.acquire(blocking=False):
        return None
    try:
        fresh = agent.get_state(config).values.get("workflow") or {}
        if fresh.get("version") != version.get("version"):
            return None
        _store(agent, config, session_id, fresh, report)
    finally:
        lock.release()
    return report


def _store(agent, config, session_id, workflow, report):
    update = {"workflow": record(workflow, report)}
    if report["changed"]:
        # 复用会话消息：用户下次打开就在对话里看到这份 diff，不需要额外推送通道。
        update["messages"] = [AIMessage(content=markdown(report))]
    agent.update_state(config, update)
    logging.getLogger(__name__).info("Trip watch %s: %s", session_id, report["summary"])


def due_sessions(agent, now=None):
    now = now or datetime.now(timezone.utc)
    seen, sessions = set(), []
    with closing(agent.checkpointer.list(None)) as checkpoints:
        for checkpoint in checkpoints:
            session_id = checkpoint.config["configurable"]["thread_id"]
            if session_id in seen:
                continue
            seen.add(session_id)
            workflow = (checkpoint.checkpoint.get("channel_values") or {}).get("workflow") or {}
            if is_due(workflow, now):
                sessions.append(session_id)
    return sessions


def scheduler_pass(agent, lock=None, tools=None, now=None):
    done = []
    for session_id in due_sessions(agent, now):
        report = check_session(agent, session_id, tools=tools, lock=lock, now=now)
        if report:
            done.append((session_id, report))
    return done


def start_scheduler(agent, lock=None, tools=None, stop=None, minutes=None):
    """行前复核的定时任务；默认每小时看一次，已经有 24 小时间隔兜底，不会重复查。"""
    if not scheduler_enabled():
        return None
    stop = stop or Event()
    interval = (minutes or scheduler_minutes()) * 60

    def loop():
        # 启动 30 秒后先跑一轮，重启也能补上漏掉的复核；之后按间隔重复。
        if stop.wait(min(30.0, interval)):
            return
        while True:
            try:
                scheduler_pass(agent, lock, tools)
            except Exception:
                logging.getLogger(__name__).warning("Trip watch scheduler pass failed")
            if stop.wait(interval):
                return

    thread = Thread(target=loop, name="trip-watch", daemon=True)
    thread.start()
    return thread
