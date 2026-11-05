from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import json

from langchain_core.messages import ToolMessage
from travelmate.evidence import normalize, check_reference, validate_evidence, capture_evidence
from test_workflow import REQ, PLAN


def place(now=None):
    return normalize("search_places", {"keyword": "西湖", "city": "杭州"},
                     {"results": [{"name": "西湖"}]}, "lookup", REQ, now)


def test_field_level_support_and_forgery():
    evidence = place()
    assert check_reference(evidence, "lookup:0", "place", "西湖", REQ) is None
    assert check_reference(evidence, "lookup:0", "price", 100, REQ)
    assert check_reference(evidence, "lookup:0", "opening_hours", "09:00", REQ)
    assert check_reference(evidence, "invented", "place", "西湖", REQ)
    plan = deepcopy(PLAN)
    plan["days"][0]["stops"][0]["fact_refs"] = {"cost": "lookup:0"}
    assert validate_evidence(REQ, plan, evidence)


def test_expiry_and_context():
    assert check_reference(place(datetime.now(timezone.utc) - timedelta(days=31)), "lookup:0", "place", "西湖", REQ)
    assert check_reference(place(), "lookup:0", "place", "西湖", {**REQ, "destination": "北京"})


def test_query_states_distinct():
    for data, expected in [({"error": "timeout"}, "failed"), ({"results": []}, "empty"),
                           ({"error": "future", "status": "out_of_range"}, "out_of_range")]:
        records = normalize("search_train_tickets", {}, data, "rail", REQ)
        assert records["rail:0"]["query_status"] == expected
        assert check_reference(records, "rail:0", "train", None, REQ)


def test_documents_are_reference_and_links_safe():
    records = normalize("search_knowledge", {}, {"results": [{"source": "攻略", "content": "票价100", "url": "javascript:alert(1)"}]}, "kb", REQ)
    assert records["kb:0"]["verification"] == "reference"
    assert records["kb:0"]["url"] is None
    assert check_reference(records, "kb:0", "price", 100, REQ)


def test_middleware_creates_tool_owned_records():
    request = SimpleNamespace(tool_call={"name": "search_places", "args": {}, "id": "actual"}, state={"workflow": {"requirements": REQ}})
    result = capture_evidence.wrap_tool_call(request, lambda request: ToolMessage(name="search_places", tool_call_id="actual", content='{"results":[{"name":"西湖"}]}'))
    assert result.update["evidence"]["actual:0"]["tool_call_id"] == "actual"
    assert "evidence" in json.loads(result.update["messages"][0].content)


def test_driving_is_not_walking():
    evidence = normalize("search_route", {}, {"paths": [{"duration": "1800"}]}, "route", REQ)
    plan = deepcopy(PLAN)
    plan["days"][0]["stops"][0].update(fact_refs={"travel_minutes": "route:0"}, transport_mode="walking")
    assert validate_evidence(REQ, plan, evidence)
    plan["days"][0]["stops"][0]["transport_mode"] = "driving"
    assert not validate_evidence(REQ, plan, evidence)


def test_train_date_and_unbacked_text():
    row = {"start_train_code": "G123", "from_station": "上海虹桥", "to_station": "杭州东",
           "start_date": "2026-12-01", "start_time": "08:00", "arrive_time": "09:00", "prices": []}
    evidence = normalize("search_train_tickets", {"departure_date": "2026-12-02"}, {"results": [row]}, "rail", REQ)
    plan = {**PLAN, "rail_segments": [{"ticket": row, "evidence_id": "rail:0"}]}
    assert validate_evidence(REQ, plan, evidence)
    plan = deepcopy(PLAN)
    plan["days"][0]["stops"][0]["notes"] = "乘坐G9999"
    assert validate_evidence(REQ, plan, {})


def test_return_train_must_match_direction_and_last_day():
    req = {**REQ, "origin": "北京", "destination": "杭州", "days": 3}
    args = {"origin": "杭州", "destination": "北京", "departure_date": "2026-12-03"}
    row = {"start_train_code": "G10", "from_station": "杭州东", "to_station": "北京南",
           "start_date": "2026-12-03", "start_time": "08:00", "arrive_time": "13:00", "prices": []}
    evidence = normalize("search_train_tickets", args, {"results": [row]}, "rail", req)
    plan = {**PLAN, "rail_segments": [{"ticket": row, "evidence_id": "rail:0"}]}
    assert not validate_evidence(req, plan, evidence)
    evidence["rail:0"]["query"] = {**args, "origin": "上海"}
    assert validate_evidence(req, plan, evidence)
