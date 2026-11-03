"""Independent semantic review plus program-owned gates."""
import json
import re
from hashlib import sha256
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from travelmate.workflow import validate_plan
from travelmate.evidence import validate_evidence


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str = Field(min_length=1, max_length=80)
    dimension: Literal["facts", "space_time", "budget", "risk", "readability", "navigation", "preferences"]
    severity: Literal["error", "warning"]
    location: str = Field(min_length=1, max_length=200)
    basis: str = Field(min_length=1, max_length=1000)
    suggestion: str = Field(min_length=1, max_length=1000)
    blocking: bool
    time_basis: Literal["estimate", "booking", "return_deadline"] = "estimate"


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=50)


def plan_key(plan):
    return sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def program_review(requirements, plan, evidence):
    problems, total = validate_plan(requirements, plan)
    problems += validate_evidence(requirements, plan, evidence)
    issues = [ReviewIssue(rule_id=f"PROGRAM-{i+1}", dimension="budget" if "预算" in text or "费用" in text else "facts" if any(x in text for x in ("引用", "车次", "依据")) else "space_time",
                         severity="error", location=re.split(r"[:：]", text)[0][:200], basis=text,
                         suggestion="调整对应费用或安排后重新规划", blocking=True).model_dump()
              for i, text in enumerate(problems)]
    for day, data in enumerate(plan["days"], 1):
        exclusions = requirements.get("exclusions", []) + requirements.get("day_exclusions", {}).get(str(day), [])
        if not any("爬山" in x or "登山" in x for x in exclusions):
            continue
        for index, stop in enumerate(data["stops"], 1):
            text = stop.get("notes", "")
            climbing = "climbing" in stop.get("activities", []) or re.search(r"(?<!不)(?<!无需)(?<!避免)爬山|(?<!不)登山", text)
            if climbing:
                issues.append(ReviewIssue(rule_id="PREFERENCE-NO-CLIMB", dimension="preferences", severity="error",
                    location=f"第{day}天/活动{index}/{stop['place']}", basis="用户排除爬山，但活动含登山安排",
                    suggestion="更换为无登山活动，并保留其他旅行条件", blocking=True).model_dump())
    return issues, total


def blocking_messages(issues):
    return [f"{x['location']}：{x['basis']}；建议：{x['suggestion']}" for x in issues if x["blocking"]]


def timing_warnings(issues, requirements, plan):
    """Estimated timing guides refinement; only actual user time anchors can block it."""
    result = []
    for issue in issues:
        anchored = (issue.get("time_basis") == "return_deadline" and requirements.get("return_deadline") or
                    issue.get("time_basis") == "booking" and any(b.get("departure") for b in requirements.get("bookings", [])))
        if (plan.get("time_granularity") == "period" and issue["dimension"] in ("space_time", "navigation")
                and not issue["rule_id"].startswith("PROGRAM-") and not anchored):
            issue = {**issue, "severity": "warning", "blocking": False}
        result.append(issue)
    return result
