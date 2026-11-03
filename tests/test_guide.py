from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from travelmate.api import create_app
from travelmate.agent import chat, conversation
from travelmate.workflow import get_workflow
from travelmate.guide import make_guide, render_guide, version_snapshot, get_version
from travelmate.pdf_export import guide_pdf
from travelmate.evidence import normalize, safe_url
from test_workflow import REQ, PLAN
from test_planner import Model, open_test


def version(plan=None):
    return {"version": 1, "plan": plan or deepcopy(PLAN), "requirements": REQ, "saved_at": datetime.now(timezone.utc).isoformat()}


def test_shared_document_costs_statuses_and_navigation():
    plan = deepcopy(PLAN)
    plan["days"][0]["date"] = None
    req = {**REQ, "start_date": None}
    evidence = normalize("search_places", {}, {"results": [{"name": "西湖", "location": "120.1,30.2"}]}, "map", req)
    plan["days"][0]["stops"][0].update(fact_refs={"place": "map:0"}, transport_mode="walking")
    v = {**version(plan), "requirements": req}
    guide = make_guide(v, evidence)
    assert guide["total"] == 600
    text = str(guide)
    assert "第1天" in text and "无法查询" in text
    assert "地点存在：查询时已核实" not in text and "全员费用：无法查询" in text
    assert "交通耗时：待核实" not in text and "uri.amap.com/marker" in text
    assert guide_pdf(guide).startswith(b"%PDF-")
    for section in guide["sections"]:
        assert section["title"] in render_guide(guide, "/download")


def test_snapshots_dont_change_with_current_evidence():
    snapshot = version_snapshot(version(), {})
    guide = deepcopy(snapshot["guide"])
    state = {"versions": [snapshot], "evidence": {"fake": {"title": "later"}}}
    assert get_version(state, 1) == guide
    assert get_version(state, 9) is None
    old = {"versions": [{"version": 2, "plan": PLAN, "requirements": REQ}]}
    assert get_version(old, 2) == get_version(old, 2)


def test_script_and_unsafe_links_never_execute():
    v = version()
    v["requirements"] = {**REQ, "destination": '<script>alert(1)</script>'}
    v["plan"]["days"][0]["stops"][0]["notes"] = '<img src=x onerror=alert(1)>'
    guide = make_guide(v, {})
    guide["sections"][0]["items"].append({"text": "bad link", "link": "javascript:alert(1)"})
    html = render_guide(guide, "/safe")
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html
    for value in ["https:", "https://user:pass@example.com", "javascript:alert(1)", "https://example.com/\njavascript:bad", "https://[invalid"]:
        assert safe_url(value) is None


def test_api_links_immutable_version_pdf_and_unknown(tmp_path):
    @contextmanager
    def factory():
        with open_test(tmp_path, Model()) as agent:
            yield agent
    with TestClient(create_app(factory)) as client:
        response = client.post("/chat/stream", json={"session_id": "trip", "message": "规划"})
        assert '"plan_version": 1' in response.text
        messages = client.get("/sessions/trip").json()["messages"]
        assert messages[-1]["plan_version"] == 1
        old = client.get("/sessions/trip/plans/1")
        assert old.status_code == 200 and "default-src 'none'" in old.headers["content-security-policy"]
        assert "无法查询" in old.text and "600.00" not in old.text
        pdf = client.get("/sessions/trip/plans/1/pdf")
        assert pdf.content.startswith(b"%PDF-")
        assert client.get("/sessions/other/plans/1").status_code == 404
        assert client.get("/sessions/trip/plans/99").status_code == 404
        client.post("/chat/stream", json={"session_id": "trip", "message": "再规划"})
        assert client.get("/sessions/trip/plans/1").text == old.text
        assert client.get("/sessions/trip/plans/2").status_code == 200
        result = client.put("/sessions/trip/trip", json=PLAN).json()
        assert result["status"] == "needs_review"
        assert client.post("/sessions/trip/trip/confirm", json=PLAN).status_code == 409


def test_pending_and_failed_answers_have_no_new_guide(tmp_path):
    with open_test(tmp_path, Model(intake={"intent": "plan", "conditions": {"destination": "杭州"}})) as agent:
        chat(agent, "trip", "杭州")
        assert "plan_version" not in conversation(agent, "trip")["messages"][-1]
