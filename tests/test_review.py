from copy import deepcopy
from langchain_core.runnables import RunnableLambda
from travelmate.review import program_review
from travelmate.workflow import get_workflow
from travelmate.agent import chat
from test_workflow import REQ, PLAN
from test_planner import Model, open_test


PROBLEM = {"rule_id": "PREF-CLIMB", "dimension": "preferences", "severity": "error",
           "location": "第1天/活动1", "basis": "用户不爬山，方案安排登高", "suggestion": "改为平地游览", "blocking": True}


class ReviewedModel(Model):
    def __init__(self, reports, **kwargs):
        super().__init__(**kwargs)
        self.reports = reports
    def with_structured_output(self, schema, **kwargs):
        if schema.__name__ != "ReviewReport":
            return super().with_structured_output(schema, **kwargs)
        def run(messages):
            self.calls.append("ReviewReport")
            report = self.reports.pop(0) if len(self.reports) > 1 else self.reports[0]
            if report is None:
                raise RuntimeError("secret")
            return schema.model_validate({"issues": report})
        return RunnableLambda(run)


def test_program_detects_money_time_booking_and_climbing():
    plan = deepcopy(PLAN)
    plan["other_cost"] = 99999
    plan["days"][0]["stops"][0].update(end="08:00", activities=["climbing"])
    req = {**REQ, "exclusions": ["爬山"], "bookings": [{"description": "返程车票", "day": 1, "departure": "07:00"}]}
    issues, _ = program_review(req, plan, {})
    assert len(issues) >= 4
    assert any(i["rule_id"] == "PREFERENCE-NO-CLIMB" and "活动1" in i["location"] for i in issues)


def test_model_pass_cannot_override_program_error(tmp_path):
    bad = {**PLAN, "other_cost": 99999}
    model = ReviewedModel([[]], plans=[bad])
    with open_test(tmp_path, model) as agent:
        chat(agent, "review", "规划")
        state = get_workflow(agent, "review")
        assert state["status"] == "blocked" and state["attempts"] == 3
        assert model.calls.count("ReviewReport") == 3
        assert all(r["issues"] for r in state["review_history"])


def test_semantic_recheck_is_for_current_candidate(tmp_path):
    revised = deepcopy(PLAN)
    revised["days"][0]["stops"][0]["notes"] = "改成平地游览"
    model = ReviewedModel([[PROBLEM], []], plans=[PLAN, revised])
    with open_test(tmp_path, model) as agent:
        chat(agent, "review", "不爬山")
        state = get_workflow(agent, "review")
        assert state["status"] == "review" and state["attempts"] == 2
        assert len(state["review_history"]) == 2
        assert state["review_history"][0]["candidate_hash"] != state["review_history"][1]["candidate_hash"]
        assert state["versions"][0]["review"]["issues"] == []


def test_reviewer_failure_preserves_old_plan(tmp_path):
    with open_test(tmp_path, Model()) as agent:
        chat(agent, "trip", "规划")
        old = get_workflow(agent, "trip")["plan"]
    with open_test(tmp_path, ReviewedModel([None])) as agent:
        text = chat(agent, "trip", "修改")
        state = get_workflow(agent, "trip")
        assert state["status"] == "failed" and state["plan"] == old
        assert "secret" not in text


def test_no_source_train_stays_blocked_even_with_model_pass(tmp_path):
    plan = deepcopy(PLAN)
    plan["days"][0]["stops"][0]["notes"] = "乘坐G9999抵达"
    with open_test(tmp_path, ReviewedModel([[]], plans=[plan])) as agent:
        chat(agent, "trip", "规划")
        state = get_workflow(agent, "trip")
        assert state["status"] == "blocked" and "plan" not in state
        assert any("G9999" in message for message in state["issues"])
