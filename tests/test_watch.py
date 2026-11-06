from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from travelmate import watch
from travelmate.agent import conversation, open_agent
from travelmate.api import create_app
from travelmate.workflow import save_workflow
from test_travelmate import BudgetModel

NOW = datetime(2026, 11, 6, 4, 0, tzinfo=timezone.utc)  # 北京时间 12:00


def iso(days_from_now):
    return (watch.today() + timedelta(days=days_from_now)).isoformat()


def trip(days_from_now=2, version=3):
    start = iso(days_from_now)
    return start, {
        "version": version,
        "requirements": {"destination": "北京", "origin": "厦门", "start_date": start, "days": 2,
                         "travelers": 2, "budget": 3000, "budget_scope": "total",
                         "budget_currency": "CNY", "budget_includes": "全部费用"},
        "plan": {
            "time_granularity": "period", "other_cost": 500, "cost_notes": "住宿与往返交通估算",
            "days": [
                {"date": None, "stops": [{"place": "故宫博物院", "city": "北京", "period": "上午", "cost": 60,
                                          "cost_estimated": True, "opening_hours": "08:30-17:00",
                                          "fact_refs": {"place": "place:0", "cost": "price:0"}}]},
                {"date": None, "stops": [{"place": "颐和园", "city": "北京", "period": "上午", "cost": 30,
                                          "fact_refs": {"cost": "price:1"}}]}],
            "rail_segments": [{"evidence_id": "rail:0", "ticket": {
                "start_train_code": "G3001", "from_station": "厦门北", "to_station": "北京南",
                "start_date": start, "start_time": "07:00", "arrive_time": "14:00",
                "prices": [{"seat_name": "二等座", "price": "780"}]}}],
        },
        "evidence": {
            "place:0": {"kind": "place", "value": "故宫博物院", "address": "景山前街4号",
                        "expires_at": "2020-01-01T00:00:00+00:00"},
            "price:0": {"kind": "document", "value": "故宫门票60", "expires_at": "2020-01-01T00:00:00+00:00"},
            "price:1": {"kind": "document", "value": "颐和园门票30", "expires_at": "2020-01-01T00:00:00+00:00"},
            "rail:0": {"kind": "train", "value": {"start_train_code": "G3001"},
                       "expires_at": "2020-01-01T00:00:00+00:00",
                       "query": {"origin": "厦门", "destination": "北京",
                                 "departure_date": start, "transport": "高铁"}},
        },
    }


class Tool:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        return self.data


def tools():
    return {
        "search_train_tickets": Tool({"results": [{
            "start_train_code": "G3001", "start_time": "07:20", "arrive_time": "14:10",
            "prices": [{"seat_name": "二等座", "price": "830"}]}]}),
        "search_web": Tool({"results": [{"title": "故宫门票", "url": "https://example.com/gugong",
                                        "content": "故宫博物院门票 80 元，开放时间 08:30-17:00"}]}),
        "search_places": Tool({"results": [{"name": "故宫博物院", "address": "景山前街4号"}]}),
    }


def workflow(days_from_now=2):
    _, version = trip(days_from_now)
    return {"version": version["version"], "versions": [version],
            "requirements": version["requirements"], "plan": version["plan"],
            "plan_requirements": version["requirements"], "status": "review"}


def test_price_and_hours_extraction():
    assert watch.pick_price("成人门票60元，学生票30元") == 60
    assert watch.pick_price("停车 ¥25") == 25
    assert watch.pick_price("暂无价格") is None
    assert watch.hours_in("8:30-17:00，冬季 09:00 至 16:30") == ["08:30-17:00", "09:00-16:30"]


def test_due_window_and_interval():
    assert watch.is_due(workflow(2), NOW)
    assert not watch.is_due(workflow(9), NOW)          # 还早，不复核
    assert not watch.is_due(workflow(-1), NOW)         # 已经出发
    checked = {**workflow(2), "watch": {"version": 3, "checked_at": NOW.isoformat(), "items": []}}
    assert not watch.is_due(checked, NOW + timedelta(hours=3))
    assert watch.is_due(checked, NOW + timedelta(hours=25))
    # 存了新版本就按新版本重新复核
    newer = {**checked, "version": 4, "versions": [*workflow(2)["versions"], {**trip()[1], "version": 4}]}
    assert watch.is_due(newer, NOW + timedelta(hours=3))


def test_targets_prioritise_transport_then_prices_then_places():
    _, version = trip()
    chosen, pending = watch.select_targets(version, version["evidence"], NOW, limit=3)
    assert [target["kind"] for target in chosen] == ["train", "price_hours", "price_hours"]
    assert pending == 4                                 # 地点还有 1 项没排上
    assert chosen[1]["label"] == "故宫博物院"            # 门票贵的先查
    # 依据还在有效期内的不重跑
    fresh = {key: {**value, "expires_at": (NOW + timedelta(days=5)).isoformat()}
             for key, value in version["evidence"].items()}
    assert watch.select_targets(version, fresh, NOW)[0] == []


def test_snapshot_evidence_follows_context_key():
    from travelmate.evidence import context_key
    _, version = trip()
    key = context_key(version["requirements"])
    scoped = {name: {**record, "context": key} for name, record in version["evidence"].items()}
    assert set(watch.snapshot_evidence({**version, "evidence": scoped}, {})) == set(scoped)
    foreign = {name: {**record, "context": "other"} for name, record in version["evidence"].items()}
    # 全都不匹配时退回原始快照，至少还能标出「依据不属于当前条件」
    assert watch.snapshot_evidence({**version, "evidence": foreign}, {}) == foreign
    mixed = {**scoped, "old:0": {**version["evidence"]["place:0"], "context": "other"}}
    assert "old:0" not in watch.snapshot_evidence({**version, "evidence": mixed}, {})


def test_report_is_a_diff_with_amounts():
    _, version = trip()
    report = watch.build_report(version, {**workflow()}, tools(), NOW)
    assert report["calls"] == 3
    assert "重跑 3 次查询" in report["summary"]
    changed = {(item["label"], item["field"]): item for item in report["changed"]}
    assert changed[("厦门北 → 北京南 G3001", "二等座票价")]["delta"] == "涨 ¥50"
    assert changed[("故宫博物院", "门票（原为估算）")]["before"] == "¥60"
    assert changed[("故宫博物院", "门票（原为估算）")]["after"] == "¥80"
    text = watch.markdown(report)
    assert "| 项目 | 变动前 | 变动后 | 差额 |" in text
    assert "涨 ¥20" in text and "涨 ¥50" in text
    assert report["skipped"] == 1
    assert "出发前 3 天" in text


def test_unchanged_and_missing_data_are_reported_honestly():
    _, version = trip()
    fake = tools()
    fake["search_web"] = Tool({"results": [{"title": "故宫", "url": "https://example.com/a",
                                            "content": "故宫博物院门票 60 元，开放时间 08:30-17:00"}]})
    report = watch.build_report(version, {**workflow()}, fake, NOW)
    gu = [item for item in report["items"] if item["label"] == "故宫博物院"]
    assert not any(item["changed"] for item in gu)
    assert any("一致" in item["note"] for item in gu)
    empty = tools()
    empty["search_web"] = Tool({"results": []})
    blank = watch.build_report(version, {**workflow()}, empty, NOW)
    assert blank["unverified"] and any(item["unverified"] for item in blank["items"])
    assert "没查到可对比的数据" in watch.markdown(blank)


def test_scheduler_pass_stores_diff_and_writes_a_message(tmp_path):
    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=tmp_path / "watch.sqlite") as agent:
            yield agent

    with factory() as agent:
        save_workflow(agent, "trip-watch", workflow(2))
        done = watch.scheduler_pass(agent, None, tools())
        assert [session for session, _ in done] == ["trip-watch"]
        state = agent.get_state({"configurable": {"thread_id": "trip-watch"}}).values
        assert state["workflow"]["watch"]["summary"] == "重跑 3 次查询，6 项有变动"
        assert state["workflow"]["watch_history"][-1]["version"] == 3
        # 同一版本 24 小时内不再重复查（不花钱）
        assert watch.scheduler_pass(agent, None, tools()) == []
        assert "行前复核" in conversation(agent, "trip-watch")["messages"][-1]["content"]


def test_watch_endpoints_report_and_refuse_early_trips(tmp_path, monkeypatch):
    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=BudgetModel(), database=tmp_path / "api.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory, auth_enabled=False)) as client:
        save_workflow(client.app.state.agent, "soon", workflow(2))
        save_workflow(client.app.state.agent, "later", workflow(20))
        status = client.get("/sessions/soon/watch").json()
        assert status["due"] is True and status["version"] == 3 and status["report"] is None
        assert client.get("/sessions/later/watch").json()["due"] is False
        assert client.post("/sessions/later/watch/check").status_code == 409
        monkeypatch.setattr(watch, "query_target", lambda target, tools: {
            "results": [{"title": target["label"], "url": "https://example.com/x",
                         "content": f"{target['label']} 门票 90 元，开放时间 09:00-16:00"}]})
        response = client.post("/sessions/soon/watch/check")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["report"]["calls"] == 3
        assert "变动前" in body["markdown"]
        assert client.get("/sessions/soon/watch").json()["report"]["version"] == 3
        # 复核结果同时留在会话里，用户下次打开就能看到
        assert "行前复核" in client.get("/sessions/soon").json()["messages"][-1]["content"]
