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
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from travelmate.public import public_data
from travelmate.evidence import merge_evidence, validate_evidence, check_reference

TIME_NOTICE = "以下按大致时段安排，游玩与交通时间均为估算。可按实际到达时间、预约和体力调整顺序、删减景点或进一步细化；已订安排与返程时限优先。"
PERIOD_START = {"清晨": 0, "上午": 6 * 60, "中午": 11 * 60, "下午": 14 * 60, "晚上": 18 * 60, "全天": 0, "机动安排": 0}


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


def amount(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")



class Stop(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    place: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    period: Literal["清晨", "上午", "中午", "下午", "晚上", "全天", "机动安排"] | None = None
    suggested_window: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d[–-](?:[01]\d|2[0-3]):[0-5]\d$", description="分时段方案的可选参考窗口，例如09:00–11:00；仅用于不依赖未确认班次或营业时段的活动。")
    travel_minutes: int | None = Field(default=None, ge=0, le=1440, description="活动开始前的交通分钟数；未知时留空，不编造精确值。分时段安排仅作估算，不用于硬时间校验。")
    travel_estimate: str | None = Field(default=None, max_length=200, description="交通耗时估算范围或待确认说明，例如约30至60分钟，含候车缓冲。")
    cost: float = Field(ge=0, le=1e8, description="全员费用，人民币")
    cost_category: Literal["景点门票", "酒店住宿", "餐饮费用", "交通费用", "活动费用"] = Field(default="活动费用", description="仅分类该活动自身的cost，不重复计入其他费用；混合或无法细分时用活动费用。")
    cost_estimated: bool = Field(default=False, description="有合理估算依据时为true，并在notes写明口径；金额未知时为false且cost填0。")
    notes: str = Field(default="", max_length=1000)
    activities: list[Literal["walking", "climbing", "museum", "food", "rest", "other"]] = Field(default_factory=list, max_length=10)
    fact_refs: dict[Literal["place", "cost", "opening_hours", "travel_minutes"], str] = Field(default_factory=dict)
    opening_hours: str | None = None
    transport_mode: Literal["unknown", "driving", "walking", "transit", "rail", "flight", "ferry"] = "unknown"
    source: str = Field(default="未核实", max_length=1000, description="仅说明资料来源，不包含已核实字样；字段核实由fact_refs和程序判定，票价等无依据部分标待核实。")


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


class Food(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400, description="介绍当地菜品或小吃的口味、特点，不编造价格、餐厅或营业信息。")
    area: str = Field(default="", max_length=120, description="建议结合当日游玩片区顺路用餐；不是已核实的门店地址。")
    tips: str = Field(default="", max_length=300, description="结合用户忌口、过敏和饮食偏好给出点单提醒。")
    day: int | None = Field(default=None, ge=1, le=30, description="顺路安排在第几天；未确定时留空。")
    meal: Literal["早餐", "午餐", "晚餐", "加餐", "不限"] = "不限"


class BudgetTier(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: Literal["经济档", "舒适档", "品质档"]
    lodging: str = Field(min_length=1, max_length=120, description="住宿档次与单价区间，例如连锁中端350元/晚")
    transport: str = Field(min_length=1, max_length=120, description="交通方式与票价，例如高铁二等座553元×4")
    dining: str = Field(min_length=1, max_length=120, description="餐饮标准，例如人均205元/天")
    total: float | None = Field(default=None, ge=0, le=1e8, description="该档全员总费用；没有算法依据时留空")
    note: str = Field(default="", max_length=200)


class Pitfall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["严重", "注意", "技巧"] = "注意"
    text: str = Field(min_length=1, max_length=300, description="具体到店名、环节或时段的踩坑提醒，写清原因或替代做法")


class VerifyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1, max_length=120)
    channel: str = Field(min_length=1, max_length=120, description="官方核验渠道，例如12306、景区公众号、大众点评")


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    time_granularity: Literal["precise", "period"] = Field(default="precise", description="交通或到离时刻不确定时用period，按上午/中午/下午等安排；precise兼容已有精确行程。")
    days: list[Day] = Field(min_length=1, max_length=30)
    other_cost: float = Field(ge=0, le=1e8, description="仅用户预算包含范围内、尚未计入活动的全员费用；明确排除的住宿或往返交通不计入，没有额外项目时为0。cost_notes说明构成及合计算式。")
    other_cost_estimated: bool = Field(default=False, description="有依据且已在cost_notes列明费用构成和算式时为true。")
    alternatives: list[Alternative] = Field(default_factory=list, max_length=30)
    reminders: list[str] = Field(default_factory=list, max_length=30)
    foods: list[Food] = Field(default_factory=list, max_length=8, description="新攻略必须包含3至5项目的地特色美食介绍；空列表仅兼容历史行程。")
    summary: str = Field(default="", max_length=600, description="先给玩法判断，说明如何围绕兴趣顺路安排；没有价格依据不能断言预算够用。")
    key_call: str = Field(default="", max_length=600, description="开篇关键判断：这笔钱够不够、主要花在哪、必须取舍什么。只能基于已列费用与查询依据，禁止无依据断言预算充足。")
    hard_rules: list[str] = Field(default_factory=list, max_length=4, description="由预算和路线推出、可直接执行的三条以内硬规则，例如只买某一价位的车次、不住某片区。")
    budget_tiers: list[BudgetTier] = Field(default_factory=list, max_length=3, description="经济档、舒适档、品质档并列对照；差异要落到具体住宿、交通与餐标。")
    pitfalls: list[Pitfall] = Field(default_factory=list, max_length=12, description="至少5条真实会踩的坑，分严重、注意、技巧三级；不写注意安全这类空话。")
    verify_items: list[VerifyItem] = Field(default_factory=list, max_length=10, description="出发前必须复核的项目与官方渠道，对应正文中标注待核实的信息。")
    lodging: list[str] = Field(default_factory=list, max_length=5, description="住宿片区、交通与订房筛选建议；不编造酒店报价、房态或星级。")
    rail_segments: list[RailSegment] = Field(default_factory=list, max_length=30)
    cost_notes: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent_timing(self):
        for day in self.days:
            for stop in day.stops:
                if self.time_granularity == "precise" and (stop.start is None or stop.end is None):
                    raise ValueError("精确行程需同时提供start和end；时间不确定请使用period行程")
                if self.time_granularity == "period" and (stop.period is None or stop.start is not None or stop.end is not None):
                    raise ValueError("分时段行程需填写period，start和end必须留空")
        return self


def period_plan(plan):
    data = deepcopy(plan)
    data["time_granularity"] = "period"
    for day in data["days"]:
        for stop in day["stops"]:
            if not stop.get("period"):
                hour = int(stop["start"][:2]) if stop.get("start") else None
                stop["period"] = ("机动安排" if hour is None else "清晨" if hour < 6 else "上午" if hour < 11
                                  else "中午" if hour < 14 else "下午" if hour < 18 else "晚上")
            # 降级成时段安排时把原来的时刻留成建议窗口，别让"几点到几点"直接消失。
            if stop.get("start") and stop.get("end") and not stop.get("suggested_window"):
                stop["suggested_window"] = f"{stop['start']}–{stop['end']}"
            stop["start"] = stop["end"] = None
    return data


def adapt_timing(requirements, plan, evidence):
    if plan.get("time_granularity") == "period":
        return plan
    problems, _ = validate_plan(requirements, plan)
    # Never erase a known conflict with the user's booked departure or deadline.
    if any("时限" in problem for problem in problems):
        return plan
    uncertain = any(stop.get("transport_mode") != "driving" or
                    check_reference(evidence, stop.get("fact_refs", {}).get("travel_minutes"),
                                    "driving_minutes", stop.get("travel_minutes"), requirements)
                    for day in plan["days"] for stop in day["stops"])
    return period_plan(plan) if uncertain or any("时间" in problem for problem in problems) else plan


def time_label(plan, stop):
    if plan.get("time_granularity") != "period":
        return f"{stop['start']}–{stop['end']}"
    period = stop.get('period') or '机动安排'
    window = stop.get('suggested_window')
    return f'{window}（{period}）' if window else period


def cost_label(stop, requirements, evidence, now=None):
    ref = stop.get('fact_refs', {}).get('cost')
    if check_reference(evidence, ref, 'price', stop.get('cost'), requirements, now):
        return f"约¥{stop['cost']:.2f}（估算）" if stop.get('cost_estimated') else '无法查询'
    return f"¥{stop['cost']:.2f}"


def total_cost_label(stops, requirements, evidence, other_cost=0, now=None, *, other_cost_estimated=False):
    if other_cost and not other_cost_estimated and not any(stop.get('cost_estimated') for stop in stops):
        return '无法查询'
    labels = [cost_label(stop, requirements, evidence, now) for stop in stops]
    amounts = [stop['cost'] for stop, label in zip(stops, labels) if label != '无法查询']
    if other_cost_estimated:
        amounts.append(other_cost)
    incomplete = '无法查询' in labels or (other_cost and not other_cost_estimated)
    if not amounts and incomplete:
        return '无法查询'
    estimated = incomplete or other_cost_estimated or any(label.startswith('约') for label in labels)
    return (('约' if estimated else '') + f"¥{sum(amounts):.2f}"
            + ('（部分项目待核实）' if incomplete else '（估算）' if estimated else ''))


def travel_label(stop):
    return stop.get("travel_estimate") or (f"约{stop['travel_minutes']}分钟（估算）" if stop.get("travel_minutes") is not None else "耗时待确认，预留弹性")


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
        issues.append(f"全员总费用 {amount(total)} 元超过预算 {amount(limit)} 元，"
                      f"超出 {amount(total - limit)} 元")
    for food in plan.foods:
        if food.day and food.day > req.days:
            issues.append(f'美食{food.name}安排在第{food.day}天，超出行程天数')
    for day in plan.days:
        previous = 0
        for stop in day.stops:
            if plan.time_granularity == "precise":
                start, end = [int(t[:2]) * 60 + int(t[3:]) for t in (stop.start, stop.end)]
                if stop.travel_minutes is None:
                    issues.append(f"{day.date} {stop.place} 交通时间待确认，请改用分时段估算")
                elif end <= start or start < previous + stop.travel_minutes:
                    issues.append(f"{day.date} {stop.place} 时间重叠或交通时间不足")
                previous = end
            if stop.city != req.destination:
                issues.append(f"{stop.place} 所在城市与目的地不一致，请调整目的地或地点")
    for index, day in enumerate(plan.days, 1):
        deadlines = [b.departure for b in req.bookings if b.day == index and b.departure]
        if index == req.days and req.return_deadline:
            deadlines.append(req.return_deadline)
        for deadline in deadlines:
            cutoff = int(deadline[:2]) * 60 + int(deadline[3:])
            if any((stop.end > deadline if plan.time_granularity == "precise" else
                    PERIOD_START[stop.period] >= cutoff) for stop in day.stops):
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
    if not changed and provisional == old.get("assumptions", {}) and old.get("schema_version") == 2 and old.get("missing", []) == missing:
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
