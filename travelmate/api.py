"""Local single-user HTTP service. Bind to loopback only."""
import logging
import json
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from threading import Lock
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator, StringConstraints

from travelmate.rail import search_train_tickets
from travelmate.agent import chat, conversation, conversations, open_agent, stream_chat, pin_sessions, delete_sessions
from travelmate.evidence import validate_evidence
from travelmate.workflow import Itinerary, get_workflow, save_workflow, validate_plan
from travelmate.pdf_export import itinerary_pdf, answer_pdf


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1, max_length=8000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("消息不能为空")
        return value.strip()


class ChatResponse(BaseModel):
    session_id: str
    answer: str


SessionKey = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]


class SessionSelection(BaseModel):
    session_ids: list[SessionKey] = Field(min_length=1, max_length=500)


class SessionPin(SessionSelection):
    pinned: bool = Field(strict=True)


class RailRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    transport: Literal["高铁", "动车", "火车"] = "火车"


def create_app(agent_factory=open_agent):
    @asynccontextmanager
    async def lifespan(app):
        with agent_factory() as agent:
            app.state.agent = agent
            yield

    app = FastAPI(title="TravelMate (local)", lifespan=lifespan)
    # Serialize checkpoint updates, including concurrent requests for the same session.
    lock = Lock()

    @contextmanager
    def trip_lock():
        if not lock.acquire(timeout=1):
            raise HTTPException(409, "正在生成回复或处理其他请求，请稍后再保存行程")
        try:
            yield
        finally:
            lock.release()

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/assets/markdown.js", include_in_schema=False)
    def markdown_script():
        return FileResponse(Path(__file__).with_name("markdown.js"), media_type="text/javascript")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/transport/trains")
    def train_search(request: RailRequest):
        return search_train_tickets.invoke(request.model_dump())

    @app.get("/sessions")
    def list_sessions():
        with lock:
            return {"sessions": conversations(app.state.agent)}

    @app.get("/sessions/{session_id}")
    def history(session_id: Annotated[str, PathParam(min_length=1, max_length=100,
                                                   pattern=r"^[a-zA-Z0-9_-]+$")]):
        with lock:
            return conversation(app.state.agent, session_id)

    @app.post("/chat", response_model=ChatResponse)
    def respond(request: ChatRequest):
        try:
            with lock:
                answer = chat(app.state.agent, request.session_id, request.message)
            return ChatResponse(session_id=request.session_id, answer=answer)
        except Exception:
            logging.getLogger(__name__).warning("Agent request failed")
            raise HTTPException(502, "智能体请求失败，请检查服务配置或稍后重试") from None

    SessionId = Annotated[str, PathParam(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]

    @app.post("/sessions/delete")
    def remove_selected(request: SessionSelection):
        with trip_lock():
            delete_sessions(app.state.agent, request.session_ids)
        return {"deleted": list(dict.fromkeys(request.session_ids))}

    @app.delete("/sessions/{session_id}")
    def remove_session(session_id: SessionId):
        with trip_lock():
            delete_sessions(app.state.agent, [session_id])
        return {"deleted": [session_id]}

    @app.post("/sessions/pin")
    def pin_selected(request: SessionPin):
        with trip_lock():
            existing = {item["session_id"] for item in conversations(app.state.agent)}
            if any(key not in existing for key in request.session_ids):
                raise HTTPException(404, "所选对话不存在，请刷新列表")
            pin_sessions(app.state.agent, request.session_ids, request.pinned)
        return {"pinned": request.pinned}

    @app.get("/sessions/{session_id}/trip")
    def trip(session_id: SessionId):
        with lock:
            return get_workflow(app.state.agent, session_id)

    @app.get("/sessions/{session_id}/answers/{message_id}/pdf")
    def export_answer(session_id: SessionId,
                      message_id: Annotated[str, PathParam(pattern=r"^[a-f0-9]{32}$")]):
        with trip_lock():
            messages = conversation(app.state.agent, session_id)["messages"]
            answer = next((m for m in messages if m.get("message_id") == message_id), None)
            if answer is None:
                raise HTTPException(404, "这条回答不存在或尚未完成，请刷新对话后重试")
            text = answer["content"]
        return Response(answer_pdf(text), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="travelmate-{message_id[:8]}.pdf"'})

    @app.put("/sessions/{session_id}/trip")
    def edit_trip(session_id: SessionId, plan: Itinerary):
        with trip_lock():
            state = get_workflow(app.state.agent, session_id)
            if "plan" not in state:
                raise HTTPException(409, "请先生成行程")
            data = plan.model_dump(mode="json")
            issues, total = validate_plan(state["requirements"], data)
            issues += validate_evidence(state["requirements"], data, state.get("evidence", {}))
            if issues:
                state = {**state, "candidate": data, "issues": issues, "status": "blocked"}
            else:
                versions = list(state.get("versions", []))
                if not versions:
                    versions.append({"version": 1, "plan": state["plan"], "requirements": state.get("plan_requirements", state["requirements"]), "total": state.get("total")})
                version = len(versions) + 1
                versions.append({"version": version, "plan": data, "requirements": state["requirements"], "total": total})
                state = {**state, "plan": data, "plan_requirements": state["requirements"], "versions": versions,
                         "version": version, "issues": [], "total": total, "status": "review"}
            save_workflow(app.state.agent, session_id, state)
            return state

    @app.post("/sessions/{session_id}/trip/confirm")
    def confirm_trip(session_id: SessionId, plan: Itinerary):
        with trip_lock():
            state = get_workflow(app.state.agent, session_id)
            if state.get("status") != "review" or state.get("plan") != plan.model_dump(mode="json"):
                raise HTTPException(409, "行程已变更或尚未通过校验，请重新查看并确认")
            issues, total = validate_plan(state["requirements"], state["plan"])
            issues += validate_evidence(state["requirements"], state["plan"], state.get("evidence", {}))
            if issues:
                raise HTTPException(409, "行程未通过校验")
            state = {**state, "status": "confirmed", "total": total}
            save_workflow(app.state.agent, session_id, state)
            return state

    @app.get("/sessions/{session_id}/trip/pdf")
    def export_trip(session_id: SessionId):
        with lock:
            state = get_workflow(app.state.agent, session_id)
            if state.get("status") != "confirmed":
                raise HTTPException(409, "请先确认有效行程")
            content = itinerary_pdf(state)
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="travelmate.pdf"'})

    @app.post("/chat/stream")
    def respond_stream(request: ChatRequest):
        def events():
            with lock:
                try:
                    yield 'event: status\ndata: {"text":"正在理解你的旅行需求…"}\n\n'
                    for event, data in stream_chat(app.state.agent, request.session_id, request.message):
                        yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except Exception:
                    logging.getLogger(__name__).warning("Agent stream failed")
                    yield 'event: error\ndata: {"text":"回复中断，请检查配置或网络后重试"}\n\n'
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()
