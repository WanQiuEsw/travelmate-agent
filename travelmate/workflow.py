"""Checkpointed planning state and deterministic itinerary checks."""
import json
from copy import deepcopy
from datetime import date as CalendarDate, timedelta, datetime, timezone
from typing import NotRequired, Literal, Annotated

from langchain.agents import AgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, ConfigDict, Field, create_model
from travelmate.public import public_data
from travelmate.evidence import merge_evidence, validate_evidence


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    origin: str | None = Field(default=None, min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    start_date: CalendarDate | None = None
    transport: Literal["不限", "高铁", "动车", "火车", "飞机", "自驾", "其他"] = "不限"
    days: int = Field(ge=1, le=30)
    travelers: int = Field(ge=1, le=100)
    budget: float = Field(gt=0, le=1e8)
    preferences: str = Field(default="无特殊偏好", max_length=1000)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=10)
    budget_scope: Literal["per_person", "total"] | None = None
    budget_includes: str | None = Field(default=None, min_length=1, max_length=1000)
    interests: list[str] = Field(default_factory=list, max_length=30)
    exclusions: list[str] = Field(default_factory=list, max_length=30)
    mobility: str | None = Field(default=None, max_length=1000)
    accommodation: str | None = Field(default=None, max_length=1000)
    dietary: str | None = Field(default=None, max_length=1000)
    date_flexibility: str | None = Field(default=None, max_length=1000)
    return_deadline: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    day_exclusions: dict[int, list[str]] = Field(default_factory=dict, description="第几天到排除项的映射，修改时保留其他天")
    bookings: list["Booking"] = Field(default_factory=list, max_length=30)


class Booking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=1000)
    day: int | None = Field(default=None, ge=1, le=30)
    departure: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    nonrefundable: bool | None = None


Requirements.model_rebuild()
partial_fields = {}
for key, field in Requirements.model_fields.items():
    if field.is_required():
        optional_field = deepcopy(field)
        optional_field.default = None
        partial_fields[key] = (field.annotation | None, optional_field)
PartialRequirements = create_model("PartialRequirements", __base__=Requirements, **partial_fields)


def budget_total(requirements):
    # Legacy checkpoints used total CNY; new conditions must explicitly supply scope.
    return requirements["budget"] * (requirements["travelers"]
        if requirements.get("budget_scope") == "per_person" else 1)



class Stop(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    place: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    travel_minutes: int = Field(ge=0, le=1440, description="本活动开始前、从上一活动到达本地点的交通分钟数；上一活动end加此数不得晚于本活动start。交通不属于本活动start/end内的停留时间。")
    cost: float = Field(ge=0, le=1e8, description="全员费用，人民币")
    notes: str = Field(default="", max_length=1000)
    activities: list[Literal["walking", "climbing", "museum", "food", "rest", "other"]] = Field(default_factory=list, max_length=10)
    fact_refs: dict[Literal["place", "cost", "opening_hours", "travel_minutes"], str] = Field(default_factory=dict)
    opening_hours: str | None = None
    transport_mode: Literal["unknown", "driving", "walking", "transit", "rail"] = "unknown"
    source: str = Field(default="未核实", max_length=1000)


class Day(BaseModel):
    date: CalendarDate | None = Field(default=None, description="未提供出发日期时为 null，按列表顺序表示第几天")
    stops: list[Stop] = Field(min_length=1, max_length=20)


class RailSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    ticket: dict


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    trigger: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=1000)
    extra_cost: float | None = Field(default=None, ge=0, le=1e8)


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    days: list[Day] = Field(min_length=1, max_length=30)
    other_cost: float = Field(ge=0, le=1e8, description="全员住宿、往返交通等未计入活动的费用")
    alternatives: list[Alternative] = Field(default_factory=list, max_length=30)
    reminders: list[str] = Field(default_factory=list, max_length=30)
    rail_segments: list[RailSegment] = Field(default_factory=list, max_length=30)
    cost_notes: str = Field(min_length=1, max_length=2000)


class PlanningState(AgentState):
    workflow: NotRequired[dict]
    evidence: Annotated[dict, merge_evidence]
    intake_result: NotRequired[dict]
    candidate: NotRequired[dict | None]
    areas: NotRequired[dict]
    research_data: NotRequired[list]


def validate_plan(requirements, plan):
    req = Requirements.model_validate(requirements)
    plan = Itinerary.model_validate(plan)
    issues = []
    expected = [req.start_date + timedelta(days=i) if req.start_date else None for i in range(req.days)]
    if [day.date for day in plan.days] != expected:
        issues.append("行程日期与天数必须一致；未指定开始日期时，各天日期应留空")
    total = round(plan.other_cost + sum(s.cost for d in plan.days for s in d.stops), 2)
    limit = budget_total(req.model_dump())
    if req.budget_currency not in (None, "CNY"):
        issues.append("当前校验仅支持 CNY，请确认人民币预算，不自动换汇")
    if total > limit:
        issues.append(f"全员总费用 {total} 元超过预算 {limit} 元")
    for day in plan.days:
        previous = 0
        for stop in day.stops:
            start, end = [int(t[:2]) * 60 + int(t[3:]) for t in (stop.start, stop.end)]
            if end <= start or start < previous + stop.travel_minutes:
                issues.append(f"{day.date} {stop.place} 时间重叠或交通时间不足")
            if stop.city != req.destination:
                issues.append(f"{stop.place} 所在城市与目的地不一致，请调整目的地或地点")
            previous = end
    for index, day in enumerate(plan.days, 1):
        deadlines = [b.departure for b in req.bookings if b.day == index and b.departure]
        if index == req.days and req.return_deadline:
            deadlines.append(req.return_deadline)
        for deadline in deadlines:
            if any(stop.end > deadline for stop in day.stops):
                issues.append(f"第{index}天活动超过已订出发或返程时限 {deadline}，请调整并预留交通时间")
    return issues, total


def result(runtime, state):
    return Command(update={"workflow": state, "messages": [ToolMessage(
        content=json.dumps(state, ensure_ascii=False), tool_call_id=runtime.tool_call_id)]})


@tool
def update_trip(conditions: dict, runtime: ToolRuntime, assumptions: dict | None = None,
                allow_booking_change: bool = False) -> Command:
    """更新用户明确条件，保留其他字段。budget为原始金额，budget_scope(per_person/total)、budget_currency(CNY等)、budget_includes必需澄清。可选day_exclusions(第几天到排除列表的映射)、interests/exclusions列表、mobility/accommodation/dietary/date_flexibility/return_deadline(HH:MM)、bookings(description/day/departure/nonrefundable)。assumptions仅暂定；已有预订修改须用户明确要求并设置allow_booking_change。"""
    old = runtime.state.get("workflow", {})
    previous = old.get("requirements", {})
    if "bookings" in conditions and previous.get("bookings") and conditions["bookings"] != previous["bookings"] and not allow_booking_change:
        return {"error": "已有预订不能无声覆盖，请先说明冲突并取得用户明确修改要求"}
    if "day_exclusions" in conditions and isinstance(conditions["day_exclusions"], dict):
        conditions = {**conditions, "day_exclusions": {**previous.get("day_exclusions", {}),
                      **{str(k): v for k, v in conditions["day_exclusions"].items()}}}
    merged = {**previous, **conditions}
    for key in ("origin", "start_date"):
        if merged.get(key) == "":
            merged[key] = None
    try:
        parsed = PartialRequirements.model_validate(merged)
        if assumptions is not None:
            PartialRequirements.model_validate(assumptions)
    except ValueError as exc:
        return {"error": str(exc)}
    merged = parsed.model_dump(mode="json", exclude_unset=True)
    missing = [key for key in ("destination", "days", "travelers", "budget",
               "budget_scope", "budget_currency", "budget_includes") if merged.get(key) in (None, "")]
    if any(not 1 <= int(day) <= (merged.get("days") or 30) for day in merged.get("day_exclusions", {})):
        return {"error": "按天排除项必须在行程天数内"}
    if any(b.get("day") and b["day"] > (merged.get("days") or 30) for b in merged.get("bookings", [])):
        return {"error": "已订安排超出新行程天数，请先说明冲突并明确修改预订"}
    changed = [key for key in conditions if merged.get(key) != previous.get(key)]
    provisional = {**old.get("assumptions", {}), **(assumptions or {})}
    provisional = {key: value for key, value in provisional.items() if merged.get(key) in (None, "")}
    if not changed and provisional == old.get("assumptions", {}) and old.get("schema_version") == 2:
        return result(runtime, old)
    affected_days = list(range(1, (merged.get("days") or 0) + 1))
    if changed == ["day_exclusions"]:
        affected_days = sorted(int(day) for day, value in merged["day_exclusions"].items()
                               if previous.get("day_exclusions", {}).get(day) != value)
    given = set(old.get("given_fields", previous)) | set(conditions)
    state = {**old, "schema_version": 2, "requirements": merged, "assumptions": provisional,
             "missing": missing, "status": "collecting" if missing else "researching", "attempts": 0,
             "changed_fields": changed, "affected_days": affected_days,
             "given_fields": sorted(given),
             "condition_status": {**{k: "given" for k in given if merged.get(k) is not None},
                                  **{k: "missing" for k in missing},
                                  **{k: "assumed" for k in provisional}},
             "changes": [*old.get("changes", []), {"at": datetime.now(timezone.utc).isoformat(),
                         "before": {k: previous.get(k) for k in changed},
                         "after": {k: merged.get(k) for k in changed}}]}
    if not missing:
        state["requirements"] = Requirements.model_validate(merged).model_dump(mode="json")
    return result(runtime, state)


@tool
def submit_itinerary(plan: Itinerary, runtime: ToolRuntime) -> Command:
    """提交结构化行程进行预算、日期、城市与时间校验。首次失败后最多修改两次；费用均为全员人民币。"""
    old = runtime.state.get("workflow", {})
    # A follow-up can revise the same conditions; keep the retry limit within each user turn.
    messages = runtime.state.get("messages", [])
    latest_user = next((i for i in range(len(messages) - 1, -1, -1)
                        if isinstance(messages[i], HumanMessage)), None)
    if latest_user is not None:
        submissions = sum(call["name"] == "submit_itinerary" for message in messages[latest_user + 1:]
                          if isinstance(message, AIMessage) for call in message.tool_calls)
        if submissions <= 1 and old.get("status") in ("review", "confirmed", "blocked"):
            old = {**old, "status": "researching", "attempts": 0}
    if old.get("status") not in ("researching", "adjusting"):
        return {"error": "请先补齐旅行条件；本轮调整达到上限时停止，并请用户补充或修改需求。"}
    data = plan.model_dump(mode="json")
    issues, total = validate_plan(old["requirements"], data)
    issues += validate_evidence(old["requirements"], data, runtime.state.get("evidence", {}))
    attempts = old.get("attempts", 0) + 1
    state = {**old, "plan": data, "issues": issues, "total": total, "attempts": attempts,
             "status": ("blocked" if attempts >= 3 else "adjusting") if issues else "review"}
    return result(runtime, state)


def get_workflow(agent, session_id):
    values = agent.get_state({"configurable": {"thread_id": session_id}}).values
    return public_data({**values.get("workflow", {}), **({"evidence": values["evidence"]} if values.get("evidence") else {})}, values.get("messages", []))


def save_workflow(agent, session_id, state):
    agent.update_state({"configurable": {"thread_id": session_id}}, {"workflow": state})
