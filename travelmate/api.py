"""Invitation-only HTTP service with account-owned conversations."""
import logging
import json
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from threading import Lock, Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from time import time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator, StringConstraints

from travelmate.rail import search_train_tickets
from travelmate.interaction import InteractionResponse
from travelmate.agent import chat, conversation, conversations, open_agent, stream_chat, pin_sessions, delete_sessions, rename_session
from travelmate.evidence import validate_evidence
from travelmate.workflow import Itinerary, get_workflow, save_workflow, validate_plan
from travelmate.pdf_export import itinerary_pdf, answer_pdf, guide_pdf
from travelmate.guide import get_version, render_guide
from travelmate.accounts import Accounts
from travelmate.auth import install_auth, require_access


class ChatRequest(BaseModel):
    interaction_response: InteractionResponse | None = None
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


class SessionRename(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class RailRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    transport: Literal["高铁", "动车", "火车"] = "火车"


def create_app(agent_factory=open_agent, *, auth_enabled=True):
    @asynccontextmanager
    async def lifespan(app):
        with agent_factory() as agent, ThreadPoolExecutor(max_workers=2) as executor:
            app.state.agent = agent
            app.state.executor = executor
            app.state.auth_enabled = auth_enabled
            if auth_enabled:
                database = agent.checkpointer.conn.execute('PRAGMA database_list').fetchone()[2]
                if not database:
                    raise ValueError('邀请登录需要持久化 SQLite 数据库')
                app.state.accounts = Accounts(database)
            yield

    app = FastAPI(title="TravelMate", lifespan=lifespan, dependencies=[Depends(require_access)],
                  docs_url=None, redoc_url=None, openapi_url=None)
    install_auth(app)
    # Serialize checkpoint updates, including concurrent requests for the same session.
    lock = Lock()
    generating = {}

    @contextmanager
    def trip_lock():
        if not lock.acquire(timeout=1):
            raise HTTPException(409, "正在生成回复或处理其他请求，请稍后再保存行程")
        try:
            yield
        finally:
            lock.release()

    def start_generation(session_id, message, user):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "正在生成回复或处理其他请求，请稍后再试")
        try:
            if auth_enabled:
                app.state.accounts.start_generation(user['id'], session_id)
            generating[session_id] = {"message": message, "started_at": time(), "steps": []}
        except BaseException:
            lock.release()
            raise

    def finish_generation(session_id):
        generating.pop(session_id, None)
        lock.release()

    @contextmanager
    def generation_lock(session_id, message, user):
        start_generation(session_id, message, user)
        try:
            yield
        finally:
            finish_generation(session_id)

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
    def train_search(request: RailRequest, http_request: Request):
        if auth_enabled:
            user_id = http_request.state.user['id']
            app.state.accounts.throttle('trains:' + user_id, 10, 60)
            app.state.accounts.throttle('trains-day:' + user_id, 100, 86400)
        return search_train_tickets.invoke(request.model_dump())

    @app.get("/sessions")
    def list_sessions(http_request: Request):
        allowed = app.state.accounts.session_ids(http_request.state.user['id']) if auth_enabled else None
        return {"sessions": conversations(app.state.agent, allowed)}

    @app.get("/sessions/{session_id}")
    def history(session_id: Annotated[str, PathParam(min_length=1, max_length=100,
                                                   pattern=r"^[a-zA-Z0-9_-]+$")]):
        run = generating.get(session_id)
        history = conversation(app.state.agent, session_id)
        run = generating.get(session_id) or run
        return {**history, "generating": run is not None,
                "progress": {**run, "steps": list(run["steps"])} if run else None}

    @app.post("/chat", response_model=ChatResponse)
    def respond(request: ChatRequest, http_request: Request):
        try:
            with generation_lock(request.session_id, request.message, http_request.state.user):
                answer = chat(app.state.agent, request.session_id, request.message,
                              **({"interaction_response": request.interaction_response.model_dump()} if request.interaction_response else {}))
            return ChatResponse(session_id=request.session_id, answer=answer)
        except HTTPException:
            raise
        except Exception:
            logging.getLogger(__name__).warning("Agent request failed")
            raise HTTPException(502, "智能体请求失败，请检查服务配置或稍后重试") from None

    SessionId = Annotated[str, PathParam(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]

    @app.post("/sessions/delete")
    def remove_selected(request: SessionSelection, http_request: Request):
        if auth_enabled:
            app.state.accounts.check_sessions(http_request.state.user['id'], request.session_ids)
        with trip_lock():
            delete_sessions(app.state.agent, request.session_ids)
        return {"deleted": list(dict.fromkeys(request.session_ids))}

    @app.delete("/sessions/{session_id}")
    def remove_session(session_id: SessionId):
        with trip_lock():
            delete_sessions(app.state.agent, [session_id])
        return {"deleted": [session_id]}

    @app.patch("/sessions/{session_id}/title")
    def rename(session_id: SessionId, request: SessionRename):
        with trip_lock():
            if not any(item["session_id"] == session_id for item in conversations(app.state.agent)):
                raise HTTPException(404, "对话不存在，请刷新列表")
            rename_session(app.state.agent, session_id, request.title)
        return {"title": request.title}

    @app.post("/sessions/pin")
    def pin_selected(request: SessionPin, http_request: Request):
        if auth_enabled:
            app.state.accounts.check_sessions(http_request.state.user['id'], request.session_ids)
        with trip_lock():
            existing = {item["session_id"] for item in conversations(app.state.agent)}
            if any(key not in existing for key in request.session_ids):
                raise HTTPException(404, "所选对话不存在，请刷新列表")
            pin_sessions(app.state.agent, request.session_ids, request.pinned)
        return {"pinned": request.pinned}

    @app.get("/sessions/{session_id}/trip")
    def trip(session_id: SessionId):
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
            elif "review" in getattr(app.state.agent, "nodes", {}):
                state = {**state, "candidate": data, "issues": ["修改尚未经过独立质量审查，请在对话中提交修改要求"], "status": "needs_review"}
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

    def load_guide(session_id, version):
        state = get_workflow(app.state.agent, session_id)
        guide = get_version(state, version)
        if guide is None:
            raise HTTPException(404, "攻略版本不存在或尚未完成")
        return guide

    @app.get("/sessions/{session_id}/plans/{version}")
    def preview(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        guide = load_guide(session_id, version)
        return HTMLResponse(render_guide(guide, f"/sessions/{session_id}/plans/{version}/pdf"),
            headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
                     "X-Content-Type-Options": "nosniff"})

    @app.get("/sessions/{session_id}/plans/{version}/pdf")
    def export_guide(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        guide = load_guide(session_id, version)
        return Response(guide_pdf(guide), media_type="application/pdf",
            headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="travelmate-v{version}.pdf"'})

    @app.get("/sessions/{session_id}/trip/pdf")
    def export_trip(session_id: SessionId):
        state = get_workflow(app.state.agent, session_id)
        if state.get("status") != "confirmed":
            raise HTTPException(409, "请先确认有效行程")
        content = itinerary_pdf(state)
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="travelmate.pdf"'})

    @app.post("/chat/stream")
    def respond_stream(request: ChatRequest, http_request: Request):
        # Reserve quota and capacity before sending SSE headers or queueing a task.
        start_generation(request.session_id, request.message, http_request.state.user)
        # The producer survives a browser reload; the stream only delivers its events.
        queue = Queue()
        disconnected = Event()

        def publish(event, data):
            if event == "status" and request.session_id in generating:
                steps = generating[request.session_id]["steps"]
                if data not in steps:
                    steps.append(data)
            if not disconnected.is_set():
                queue.put(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")

        def generate():
            try:
                publish("status", {"text": "正在理解你的旅行需求…"})
                for event, data in stream_chat(app.state.agent, request.session_id, request.message,
                                              **({"interaction_response": request.interaction_response.model_dump()} if request.interaction_response else {})):
                    publish(event, data)
            except Exception:
                logging.getLogger(__name__).warning("Agent stream failed")
                publish("error", {"text": "回复中断，请检查配置或网络后重试"})
            finally:
                finish_generation(request.session_id)
                queue.put(None)

        try:
            app.state.executor.submit(generate)
        except BaseException:
            finish_generation(request.session_id)
            raise

        def events():
            try:
                while True:
                    try:
                        frame = queue.get(timeout=1)
                    except Empty:
                        yield ": heartbeat\n\n"
                        continue
                    if frame is None:
                        break
                    yield frame
            finally:
                disconnected.set()

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()
