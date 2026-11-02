"""Local single-user HTTP service. Bind to loopback only."""
import logging
import json
from pathlib import Path
from contextlib import asynccontextmanager
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator

from travelmate.agent import chat, conversation, conversations, open_agent, stream_chat
from travelmate.workflow import Itinerary, get_workflow, save_workflow, validate_plan
from travelmate.pdf_export import itinerary_pdf


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


def create_app(agent_factory=open_agent):
    @asynccontextmanager
    async def lifespan(app):
        with agent_factory() as agent:
            app.state.agent = agent
            yield

    app = FastAPI(title="TravelMate (local)", lifespan=lifespan)
    # Serialize checkpoint updates, including concurrent requests for the same session.
    lock = Lock()

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/assets/markdown.js", include_in_schema=False)
    def markdown_script():
        return FileResponse(Path(__file__).with_name("markdown.js"), media_type="text/javascript")

    @app.get("/health")
    def health():
        return {"status": "ok"}

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

    @app.get("/sessions/{session_id}/trip")
    def trip(session_id: SessionId):
        with lock:
            return get_workflow(app.state.agent, session_id)

    @app.put("/sessions/{session_id}/trip")
    def edit_trip(session_id: SessionId, plan: Itinerary):
        with lock:
            state = get_workflow(app.state.agent, session_id)
            if "plan" not in state:
                raise HTTPException(409, "请先生成行程")
            data = plan.model_dump(mode="json")
            issues, total = validate_plan(state["requirements"], data)
            state = {**state, "plan": data, "issues": issues, "total": total,
                     "status": "blocked" if issues else "review"}
            save_workflow(app.state.agent, session_id, state)
            return state

    @app.post("/sessions/{session_id}/trip/confirm")
    def confirm_trip(session_id: SessionId, plan: Itinerary):
        with lock:
            state = get_workflow(app.state.agent, session_id)
            if state.get("status") != "review" or state.get("plan") != plan.model_dump(mode="json"):
                raise HTTPException(409, "行程已变更或尚未通过校验，请重新查看并确认")
            issues, total = validate_plan(state["requirements"], state["plan"])
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
