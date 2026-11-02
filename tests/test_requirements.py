"""Step-one constraint regression; models below do not call external services."""
from types import SimpleNamespace

from travelmate.workflow import update_trip, validate_plan, budget_total, save_workflow, get_workflow
from travelmate.agent import open_agent, PROMPT, PROMPT_VERSION
from test_workflow import call, REQ, PLAN
from test_travelmate import BudgetModel


def error(state, **conditions):
    return update_trip.func(conditions=conditions,
        runtime=SimpleNamespace(state={"workflow": state}, tool_call_id="test"))


def test_sparse_and_invalid_conditions():
    state = call(update_trip, {}, conditions={"destination": "杭州"})
    assert state["requirements"] == {"destination": "杭州"}
    assert state["status"] == "collecting"
    assert "origin" not in state["missing"] and "start_date" not in state["missing"]
    assert state["condition_status"]["destination"] == "given"
    assert "error" in error(state, days=-1)
    assert "error" in error(state, unknown="ignored?")


def test_budget_scope_and_assumptions():
    state = call(update_trip, {}, conditions={"destination": "杭州", "budget": 3000},
                 assumptions={"days": 3})
    assert "budget_scope" in state["missing"]
    assert state["condition_status"]["days"] == "assumed"
    assert "days" not in state["requirements"]
    state = call(update_trip, state, conditions={**REQ, "budget": 3000, "budget_scope": "per_person"})
    assert budget_total(state["requirements"]) == 6000
    assert state["requirements"]["budget"] == 3000
    assert not state["missing"] and not state["assumptions"]
    assert call(update_trip, state, conditions={}) == state
    assert not validate_plan(state["requirements"], {**PLAN, "other_cost": 4000})[0]
    assert validate_plan({**state["requirements"], "budget_scope": "total"},
                         {**PLAN, "other_cost": 4000})[0]


def test_day_change_preserves_conditions_and_other_days():
    state = call(update_trip, {}, conditions={**REQ, "days": 3,
        "day_exclusions": {"1": ["购物"]}})
    old = state["requirements"].copy()
    state = call(update_trip, state, conditions={"day_exclusions": {"2": ["爬山"]}})
    assert state["affected_days"] == [2]
    assert state["requirements"]["day_exclusions"] == {"1": ["购物"], "2": ["爬山"]}
    assert all(state["requirements"][k] == v for k, v in old.items() if k != "day_exclusions")
    assert state["changes"][-1]["at"]
    assert "error" in error(state, day_exclusions={"4": ["爬山"]})
    assert state["requirements"]["mobility"] is None


def test_bookings_protected_and_deadline_checked():
    booking = {"description": "已订返程车票", "day": 1, "departure": "10:00", "nonrefundable": True}
    state = call(update_trip, {}, conditions={**REQ, "bookings": [booking]})
    state = call(update_trip, state, conditions={"preferences": "带老人"})
    assert state["requirements"]["bookings"] == [booking]
    assert state["requirements"]["mobility"] is None
    assert "error" in error(state, bookings=[])
    assert any("时限" in issue for issue in validate_plan(state["requirements"], PLAN)[0])
    state = call(update_trip, state, conditions={"bookings": []}, allow_booking_change=True)
    assert state["requirements"]["bookings"] == []


def test_old_and_new_checkpoint_restart(tmp_path):
    legacy = {k: v for k, v in REQ.items() if not k.startswith("budget_")}
    assert not validate_plan(legacy, PLAN)[0]
    new = call(update_trip, {}, conditions={**REQ, "budget_scope": "per_person"})
    db = tmp_path / "compat.sqlite"
    with open_agent(model=BudgetModel(), database=db, knowledge=tmp_path) as agent:
        save_workflow(agent, "old", {"requirements": legacy, "plan": PLAN, "status": "review"})
        save_workflow(agent, "new", new)
    with open_agent(model=BudgetModel(), database=db, knowledge=tmp_path) as agent:
        assert get_workflow(agent, "old")["requirements"] == legacy
        assert get_workflow(agent, "new")["requirements"] == new["requirements"]
        upgraded = call(update_trip, get_workflow(agent, "old"), conditions={"preferences": "美食"})
        assert "budget_scope" in upgraded["missing"]


def test_prompt_contract_and_formatting():
    rendered = PROMPT.format(today="2026-11-03")
    assert PROMPT_VERSION == "advisor-v1/tools-v1"
    assert "最多三个" in rendered and "普通问答" in rendered
    assert "带老人不等于体力差" in rendered
    assert "不生成行程" not in rendered
