"""Tool-owned evidence, with field-level references and conservative expiry."""
import json
import re
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from urllib.parse import urlparse

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.types import Command


def merge_evidence(left, right):
    return {**(left or {}), **(right or {})}


def context_key(requirements):
    return sha256(json.dumps(requirements, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def safe_url(value):
    if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def normalize(name, args, data, call_id, requirements, now=None):
    now = now or datetime.now(timezone.utc)
    rows = data.get("results", data.get("paths", []))
    status = "failed" if data.get("error") else "success" if rows else "empty"
    if data.get("status") == "out_of_range":
        status = "out_of_range"
    base = dict(tool=name, tool_call_id=call_id, queried_at=now.isoformat(),
                context=context_key(requirements), query=args,
                applicable_date=args.get("departure_date"), query_status=status)
    records = {}
    def add(kind, value, title, url=None, reference=False):
        key = f"{call_id}:{len(records)}"
        ttl = timedelta(minutes=15) if name == "search_train_tickets" else timedelta(days=30) if name == "search_places" else timedelta(hours=1)
        records[key] = {**base, "id": key, "kind": kind, "value": value,
                        "title": title, "url": safe_url(url),
                        "verification": "reference" if reference else "matched",
                        "expires_at": (now + ttl).isoformat()}
    if status != "success":
        add("query", None, name)
    elif name == "search_weather":
        for row in rows:
            add("weather_forecast", row, "高德天气预报（非天气保证）", data.get("url"), reference=True)
            records[next(reversed(records))]["applicable_date"] = row.get("date")
    elif name == "search_places":
        for row in rows:
            add("place", row.get("name"), "高德地图地点搜索")
            records[next(reversed(records))].update(location=row.get("location"), address=row.get("address"))
    elif name == "search_route":
        for row in rows:
            if row.get("duration") is not None:
                add("driving_minutes", round(float(row["duration"]) / 60), "高德地图驾车路线")
    elif name == "search_train_tickets":
        for row in rows:
            add("train", {k: row.get(k) for k in ("start_train_code", "from_station", "to_station", "start_date", "start_time", "arrive_time", "prices")},
                "第三方开源 MCP 铁路查询，以12306下单页面为准", data.get("url"))
    else:
        for row in rows:
            add("document", row.get("content", ""), row.get("title") or row.get("source") or "参考资料",
                row.get("url"), reference=True)
    return records


PLACE_NOISE = re.compile(r"[\s·•・、，,。.()（）\[\]【】「」『』\-—_/|:：;；'\"“”‘’~～]+")


def same_label(left, right):
    """全半角括号、空白和分隔符差异不算不同地点；高德返回半角括号，模型常写全角。"""
    def clean(value):
        return PLACE_NOISE.sub("", str(value or "")).lower()
    return clean(left) == clean(right)


def check_reference(evidence, ref, kind, value, requirements, now=None):
    record = evidence.get(ref)
    if not record:
        return "引用无对应工具记录"
    if record["context"] != context_key(requirements):
        return "引用不属于当前旅行条件"
    if record["query_status"] != "success" or record["verification"] != "matched":
        return "查询失败、空结果或文档参考不能作为已核实依据"
    if datetime.fromisoformat(record["expires_at"]) < (now or datetime.now(timezone.utc)):
        return "依据已过期，请重新查询"
    if record["kind"] != kind:
        return f"依据类型是{record['kind']}，不能核实{kind}"
    if kind == "place":
        if not same_label(record["value"], value):
            return f"地点与查询记录不一致，记录为「{record['value']}」"
    elif record["value"] != value:
        return f"数值与查询记录不一致，记录为{record['value']}"
    return None


def validate_evidence(requirements, plan, evidence):
    issues = []
    for day_no, day in enumerate(plan.get("days", []), 1):
        for stop in day["stops"]:
            refs = stop.get("fact_refs", {})
            for field, ref in refs.items():
                kind = {"place": "place", "cost": "price", "opening_hours": "opening_hours",
                        "travel_minutes": "driving_minutes"}.get(field)
                problem = check_reference(evidence, ref, kind, stop.get(field), requirements)
                if field == "travel_minutes" and stop.get("transport_mode") != "driving":
                    problem = "驾车依据不能核实其他交通方式"
                if problem:
                    issues.append(f"第{day_no}天 {stop['place']} {field}: {problem}")
            if "已核实" in stop.get("source", ""):
                issues.append(f"第{day_no}天 {stop['place']}: 来源文字不能笼统声明已核实，请使用字段级引用")
    for segment in plan.get("rail_segments", []):
        problem = check_reference(evidence, segment["evidence_id"], "train", segment["ticket"], requirements)
        record = evidence.get(segment["evidence_id"], {})
        start = requirements.get("start_date")
        query = record.get("query", {})
        direction = (query.get("origin"), query.get("destination"))
        outbound = (requirements.get("origin"), requirements.get("destination"))
        expected = start
        if start and direction == outbound[::-1] and direction != outbound:
            expected = (datetime.fromisoformat(start).date() + timedelta(days=requirements["days"] - 1)).isoformat()
        if (not expected or direction not in (outbound, outbound[::-1])
                or record.get("applicable_date") != expected or segment["ticket"].get("start_date") != expected):
            problem = "铁路查询日期不匹配旅行日期"
        if problem:
            issues.append("铁路: " + problem)
    supported_trains = {str(segment["ticket"].get("start_train_code")) for segment in plan.get("rail_segments", [])}
    text = json.dumps(plan, ensure_ascii=False)
    for code in set(re.findall(r"(?<![A-Za-z0-9])[GDCZTK]\d{1,5}(?![A-Za-z0-9])", text)) - supported_trains:
        issues.append(f"车次{code}缺少关联的铁路查询结果")
    return issues


@wrap_tool_call
def capture_evidence(request, handler):
    output = handler(request)
    name = request.tool_call["name"]
    if name not in {"search_places", "search_route", "search_train_tickets", "search_knowledge", "search_web", "search_weather"} or not isinstance(output, ToolMessage):
        return output
    data = {}
    try:
        data = json.loads(output.content)
        if not isinstance(data, dict):
            data = {"error": "invalid_result"}
        records = normalize(name, request.tool_call["args"], data, request.tool_call["id"],
                            request.state.get("workflow", {}).get("requirements", {}))
    except (ValueError, TypeError, KeyError):
        records = normalize(name, request.tool_call["args"], {"error": "invalid_result"}, request.tool_call["id"],
                            request.state.get("workflow", {}).get("requirements", {}))
    output.content = json.dumps({**data, "evidence": records}, ensure_ascii=False)
    return Command(update={"evidence": records, "messages": [output]})
