"""Serializable questions shared by the planner and chat composer."""
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=2, max_length=5)


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    answers: dict[str, str | int | float] = Field(min_length=1, max_length=10)


FIELDS = {
    "destination": {"label": "目的地", "type": "text", "maxLength": 100},
    "days": {"label": "游玩天数", "type": "number", "min": 1, "max": 30},
    "travelers": {"label": "同行人数", "type": "number", "min": 1, "max": 100},
    "budget": {"label": "可接受预算", "type": "number", "min": 0.01, "max": 100000000, "step": "0.01"},
    "budget_scope": {"label": "预算口径", "type": "select", "options": [
        {"value": "total", "label": "全员总预算"}, {"value": "per_person", "label": "每人预算"}]},
    "budget_currency": {"label": "预算币种", "type": "text", "maxLength": 10, "placeholder": "例如 CNY（人民币）", "suggestions": ["CNY", "USD", "EUR", "HKD", "JPY"]},
    "budget_includes": {"label": "预算包含哪些费用", "type": "text", "maxLength": 1000,
        "placeholder": "例如：交通、住宿、餐饮、门票全部包含"},
    "mobility": {"label": "每天可接受步数 / 行动限制", "type": "text", "maxLength": 1000,
        "placeholder": "选择建议或填写，如每天 8000 步、不爬坡",
        "suggestions": ["每天 5000 步以内，尽量少爬坡", "每天 10000 步以内", "每天 15000 步以内", "无特别步数或行动限制"]},
}


def requirements_interaction(missing):
    return {"id": uuid4().hex, "title": "补充旅行条件", "description": "填写后继续规划，已提供的条件会保留。",
            "fields": [{"key": key, **FIELDS[key]} for key in missing if key in FIELDS]}


def decision_interaction(decision):
    options = list(dict.fromkeys([*decision.options, "暂不执行"]))
    return {"id": uuid4().hex, "title": "需要你确认", "description": "确认前暂停执行相关安排。",
            "fields": [{"key": "decision", "label": decision.question, "type": "select",
                        "options": [{"value": value, "label": value} for value in options]}]}
