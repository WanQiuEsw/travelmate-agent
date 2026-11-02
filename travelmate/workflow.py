"""Checkpointed planning state and deterministic itinerary checks."""
import json
from datetime import date, timedelta
from typing import NotRequired

from langchain.agents import AgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field
from travelmate.public import public_data


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    origin: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    start_date: date
    days: int = Field(ge=1, le=30)
    travelers: int = Field(ge=1, le=100)
    budget: float = Field(gt=0, le=1e8)
    preferences: str = Field(default="无特殊偏好", max_length=1000)


class Stop(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    place: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    travel_minutes: int = Field(ge=0, le=1440)
    cost: float = Field(ge=0, le=1e8, description="全员费用，人民币")
    notes: str = Field(default="", max_length=1000)
    source: str = Field(default="未核实", max_length=1000)


class Day(BaseModel):
    date: date
    stops: list[Stop] = Field(min_length=1, max_length=20)


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    days: list[Day] = Field(min_length=1, max_length=30)
    other_cost: float = Field(ge=0, le=1e8, description="全员住宿、往返交通等未计入活动的费用")
    cost_notes: str = Field(min_length=1, max_length=2000)


class PlanningState(AgentState):
    workflow: NotRequired[dict]


def validate_plan(requirements, plan):
    req = Requirements.model_validate(requirements)
    plan = Itinerary.model_validate(plan)
    issues = []
    expected = [req.start_date + timedelta(days=i) for i in range(req.days)]
    if [day.date for day in plan.days] != expected:
        issues.append("行程日期必须连续，且与开始日期、天数一致")
    total = round(plan.other_cost + sum(s.cost for d in plan.days for s in d.stops), 2)
    if total > req.budget:
        issues.append(f"全员总费用 {total} 元超过预算 {req.budget} 元")
    for day in plan.days:
        previous = 0
        for stop in day.stops:
            start, end = [int(t[:2]) * 60 + int(t[3:]) for t in (stop.start, stop.end)]
            if end <= start or start < previous + stop.travel_minutes:
                issues.append(f"{day.date} {stop.place} 时间重叠或交通时间不足")
            if stop.city != req.destination:
                issues.append(f"{stop.place} 所在城市与目的地不一致，请调整目的地或地点")
            previous = end
    return issues, total


def result(runtime, state):
    return Command(update={"workflow": state, "messages": [ToolMessage(
        content=json.dumps(state, ensure_ascii=False), tool_call_id=runtime.tool_call_id)]})


@tool
def update_trip(conditions: dict, runtime: ToolRuntime) -> Command:
    """从用户原话提取/修改旅行条件。仅传用户已给出的字段；缺失项返回追问。字段：origin,destination,start_date(YYYY-MM-DD),days,travelers,budget(全员人民币),preferences。"""
    old = runtime.state.get("workflow", {})
    merged = {**old.get("requirements", {}), **conditions}
    missing = [key for key in ("origin", "destination", "start_date", "days", "travelers", "budget")
               if merged.get(key) in (None, "")]
    if missing:
        return result(runtime, {"requirements": merged, "status": "collecting", "missing": missing})
    try:
        req = Requirements.model_validate(merged).model_dump(mode="json")
    except ValueError as exc:
        return {"error": str(exc)}
    if req == old.get("requirements"):
        return result(runtime, old)
    return result(runtime, {"requirements": req, "status": "researching", "attempts": 0})


@tool
def submit_itinerary(plan: Itinerary, runtime: ToolRuntime) -> Command:
    """提交结构化行程进行预算、日期、城市与时间校验。首次失败后最多修改两次；费用均为全员人民币。"""
    old = runtime.state.get("workflow", {})
    if old.get("status") not in ("researching", "adjusting"):
        return {"error": "先补齐条件；需重新规划时先修改条件。已有有效行程请由用户在页面修改。"}
    data = plan.model_dump(mode="json")
    issues, total = validate_plan(old["requirements"], data)
    attempts = old.get("attempts", 0) + 1
    state = {**old, "plan": data, "issues": issues, "total": total, "attempts": attempts,
             "status": ("blocked" if attempts >= 3 else "adjusting") if issues else "review"}
    return result(runtime, state)


def get_workflow(agent, session_id):
    values = agent.get_state({"configurable": {"thread_id": session_id}}).values
    return public_data(values.get("workflow", {}), values.get("messages", []))


def save_workflow(agent, session_id, state):
    agent.update_state({"configurable": {"thread_id": session_id}}, {"workflow": state})
