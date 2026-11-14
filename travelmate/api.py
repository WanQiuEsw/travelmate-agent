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

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator, StringConstraints

from travelmate.rail import search_train_tickets
from travelmate.interaction import InteractionResponse
from travelmate.agent import chat_reply, conversation, conversations, open_agent, stream_chat, pin_sessions, delete_sessions, rename_session
from travelmate.evidence import validate_evidence
from travelmate.workflow import Itinerary, get_workflow, save_workflow, validate_plan
from travelmate.pdf_export import itinerary_pdf, answer_pdf, guide_pdf
from travelmate.guide import get_version, render_guide, guide_markdown
from travelmate.result import RESULT_SCRIPT_HASH
from travelmate.accounts import Accounts
from travelmate.auth import CITY_VISUALS, install_auth, require_access
from travelmate import asr, watch
from travelmate.tools import search_places, search_web
from travelmate.preparation import overlay
from travelmate import library, budget


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
    plan_version: int | None = None


SessionKey = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]


class SessionSelection(BaseModel):
    session_ids: list[SessionKey] = Field(min_length=1, max_length=500)


class SessionPin(SessionSelection):
    pinned: bool = Field(strict=True)


class SessionRename(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class GuideFavorite(BaseModel):
    favorite: bool | None = Field(default=None, strict=True)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None


class PreparationItem(BaseModel):
    detail: str | None = Field(default=None, max_length=500)
    category: Literal['证件', '随身用品', '出发确认'] | None = None
    id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    done: bool = Field(strict=True)


class PreparationUpdate(BaseModel):
    revision: int = Field(ge=0, strict=True)
    items: list[PreparationItem] = Field(max_length=100)

    @field_validator('items')
    @classmethod
    def unique_ids(cls, items):
        if len({item.id for item in items}) != len(items):
            raise ValueError('事项编号不能重复')
        return items


class RailRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    transport: Literal["高铁", "动车", "火车"] = "火车"


def create_app(agent_factory=open_agent, *, auth_enabled=True):
    # Serialize checkpoint updates, including concurrent requests for the same session.
    lock = Lock()
    watch_tools = {"search_web": search_web, "search_places": search_places,
                   "search_train_tickets": search_train_tickets}

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
            library.initialize(agent)
            owners = None
            if auth_enabled:
                with app.state.accounts.connect() as conn:
                    owners = dict(conn.execute('SELECT session_id, user_id FROM auth_owners').fetchall())
            library.migrate(agent, owners)
            stop = Event()
            app.state.watch_stop = stop
            watch.start_scheduler(agent, lock, watch_tools, stop)
            try:
                yield
            finally:
                stop.set()

    app = FastAPI(title="TravelMate", lifespan=lifespan, dependencies=[Depends(require_access)],
                  docs_url=None, redoc_url=None, openapi_url=None)
    install_auth(app)
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

    def archive_session(session_id):
        owner = 'local'
        if auth_enabled:
            with app.state.accounts.connect() as conn:
                row = conn.execute('SELECT user_id FROM auth_owners WHERE session_id=?', (session_id,)).fetchone()
            if not row:
                return
            owner = row[0]
        library.sync_session(app.state.agent, session_id, owner)

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

    @app.get("/assets/theme.css", include_in_schema=False)
    def theme_stylesheet():
        return FileResponse(Path(__file__).with_name("theme.css"), media_type="text/css")

    @app.get("/assets/visual/{filename}", include_in_schema=False)
    def visual_asset(filename: Literal["companion.webp", "coast.webp", "mountains.webp", "town.webp", "icon.webp", "lodging-room.webp", "lodging-city.webp", "lodging-canal.webp", "food-reference.png", "hotel-room.webp"]):
        return FileResponse(Path(__file__).with_name("images") / filename, media_type="image/png" if filename.endswith('.png') else "image/webp")

    @app.get('/assets/visual/cities/{city}.webp', include_in_schema=False)
    def city_visual(city: str):
        if city not in CITY_VISUALS:
            raise HTTPException(404, '城市图片不存在')
        return FileResponse(Path(__file__).with_name('images') / 'cities' / f'{city}.webp', media_type='image/webp')

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get('/api/places/photo')
    def place_photo(request: Request, city: Annotated[str, Query(min_length=1, max_length=80)],
                    place: Annotated[str, Query(min_length=1, max_length=120)],
                    category: Literal['place', 'food'] = 'place'):
        from travelmate.place_photos import get_photo
        if auth_enabled:
            app.state.accounts.throttle('photos:' + request.state.user['id'], 20, 60)
        photo = (get_photo(city.strip(), place.strip(), category='food') if category == 'food'
                 else get_photo(city.strip(), place.strip()))
        if not photo:
            return Response(status_code=404, headers={'Cache-Control': 'private, max-age=600'})
        return Response(photo[0], media_type=photo[1], headers={
            'Cache-Control': 'private, max-age=21600', 'X-Content-Type-Options': 'nosniff'})

    @app.post("/transport/trains")
    def train_search(request: RailRequest, http_request: Request):
        if auth_enabled:
            user_id = http_request.state.user['id']
            app.state.accounts.throttle('trains:' + user_id, 10, 60)
            app.state.accounts.throttle('trains-day:' + user_id, 100, 86400)
        return search_train_tickets.invoke(request.model_dump())

    @app.post("/asr")
    async def transcribe(http_request: Request):
        """语音只转文字，回填到页面等用户确认；不进入对话，也不会直接触发行程生成。"""
        if auth_enabled:
            user_id = http_request.state.user['id']
            app.state.accounts.throttle('asr:' + user_id, 30, 3600)
            app.state.accounts.throttle('asr-day:' + user_id, 200, 86400)
        if int(http_request.headers.get('content-length') or 0) > asr.MAX_BYTES:
            raise HTTPException(413, "录音超过 8MB，请控制在 60 秒以内")
        audio = await http_request.body()
        try:
            return asr.transcribe(audio, http_request.headers.get('content-type'))
        except asr.VoiceError as error:
            raise HTTPException(error.status, error.message) from None

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

    @app.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
    def respond(request: ChatRequest, http_request: Request):
        try:
            with generation_lock(request.session_id, request.message, http_request.state.user):
                reply = chat_reply(app.state.agent, request.session_id, request.message,
                                   **({"interaction_response": request.interaction_response.model_dump()} if request.interaction_response else {}))
                archive_session(request.session_id)
            return ChatResponse(session_id=request.session_id, **reply)
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
            for session_id in request.session_ids:
                archive_session(session_id)
            delete_sessions(app.state.agent, request.session_ids)
        return {"deleted": list(dict.fromkeys(request.session_ids))}

    @app.delete("/sessions/{session_id}")
    def remove_session(session_id: SessionId):
        with trip_lock():
            archive_session(session_id)
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

    @app.get("/sessions/{session_id}/watch")
    def watch_status(session_id: SessionId):
        """出发前复核的状态与最近一次 diff；不改行程、不改版本。"""
        workflow = app.state.agent.get_state({"configurable": {"thread_id": session_id}}).values.get("workflow") or {}
        return watch.status(workflow)

    @app.post("/sessions/{session_id}/watch/check")
    def watch_check(session_id: SessionId):
        if lock.locked():
            raise HTTPException(409, "正在生成回复或处理其他请求，请稍后再复核")
        report = watch.check_session(app.state.agent, session_id, watch_tools, lock, force=True)
        if report is None:
            if lock.locked():
                raise HTTPException(409, "正在生成回复或处理其他请求，请稍后再复核")
            raise HTTPException(409, "当前行程还不需要行前复核：需要已保存行程，且出发日在 "
                                     f"{watch.lead_days()} 天内")
        return {"report": report, "markdown": watch.markdown(report)}

    def saved_answer(session_id, message_id):
        with trip_lock():
            messages = conversation(app.state.agent, session_id)["messages"]
            answer = next((m for m in messages if m.get("message_id") == message_id), None)
            if answer is None:
                raise HTTPException(404, "这条回答不存在或尚未完成，请刷新对话后重试")
            return answer["content"]

    @app.get("/sessions/{session_id}/answers/{message_id}/pdf")
    def export_answer(session_id: SessionId,
                      message_id: Annotated[str, PathParam(pattern=r"^[a-f0-9]{32}$")]):
        text = saved_answer(session_id, message_id)
        return Response(answer_pdf(text), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="travelmate-{message_id[:8]}.pdf"'})

    @app.get('/sessions/{session_id}/answers/{message_id}/md')
    def export_answer_markdown(session_id: SessionId,
                               message_id: Annotated[str, PathParam(pattern=r'^[a-f0-9]{32}$')]):
        return Response(saved_answer(session_id, message_id), media_type='text/markdown',
                        headers={'Content-Disposition': f'attachment; filename="travelmate-{message_id[:8]}.md"'})

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
                version = max((v['version'] for v in versions), default=0) + 1
                versions.append({"version": version, "plan": data, "requirements": state["requirements"], "total": total})
                state = {**state, "plan": data, "plan_requirements": state["requirements"], "versions": versions,
                         "version": version, "issues": [], "total": total, "status": "review"}
            save_workflow(app.state.agent, session_id, state)
            archive_session(session_id)
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
            archive_session(session_id)
            return state

    def load_guide(session_id, version):
        state = get_workflow(app.state.agent, session_id)
        guide = get_version(state, version)
        if guide is None:
            raise HTTPException(404, "攻略版本不存在或尚未完成")
        from copy import deepcopy
        guide = overlay(deepcopy(guide), state.get('preparation_lists', {}).get(str(version)))
        return budget.overlay(guide, state.get('budget_lists', {}).get(str(version)))

    @app.get('/sessions/{session_id}/plans/{version}/budget')
    def session_budget(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        with trip_lock():
            return load_guide(session_id, version)['budget_edit']

    @app.put('/sessions/{session_id}/plans/{version}/budget')
    def save_session_budget(session_id: SessionId, version: Annotated[int, PathParam(ge=1)], data: budget.BudgetUpdate):
        with trip_lock():
            guide = load_guide(session_id, version)
            if guide['budget_edit']['revision'] != data.revision:
                raise HTTPException(409, '预算已在其他页面更新，请刷新后重新编辑')
            saved = budget.validate(guide, data)
            state = get_workflow(app.state.agent, session_id)
            state['budget_lists'] = {**state.get('budget_lists', {}), str(version): saved}
            save_workflow(app.state.agent, session_id, state)
            archive_session(session_id)
            return saved

    @app.get('/sessions/{session_id}/plans/{version}/preparation')
    def preparation(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        with trip_lock():
            return load_guide(session_id, version)['preparation']

    @app.put('/sessions/{session_id}/plans/{version}/preparation')
    def update_preparation(session_id: SessionId, version: Annotated[int, PathParam(ge=1)], data: PreparationUpdate):
        with trip_lock():
            current = load_guide(session_id, version)['preparation']
            if current['revision'] != data.revision:
                raise HTTPException(409, '清单已更新，请刷新后重新编辑')
            state = get_workflow(app.state.agent, session_id)
            saved = {'revision': current['revision'] + 1, 'items': [item.model_dump() for item in data.items]}
            state['preparation_lists'] = {**state.get('preparation_lists', {}), str(version): saved}
            save_workflow(app.state.agent, session_id, state)
            archive_session(session_id)
            return saved

    @app.get("/sessions/{session_id}/plans/{version}")
    def preview(session_id: SessionId, version: Annotated[int, PathParam(ge=1)], http_request: Request,
                library_view: bool = False):
        if library_view:
            with app.state.agent.checkpointer.cursor() as cur:
                row = cur.execute('SELECT id FROM guide_library WHERE session_id=? AND deleted=0', (session_id,)).fetchone()
            if row:
                return library_preview(row[0], version, http_request)
        guide = load_guide(session_id, version)
        guide['_preparation_url'] = f'/sessions/{session_id}/plans/{version}/preparation'
        guide['_budget_url'] = f'/sessions/{session_id}/plans/{version}/budget'
        return HTMLResponse(render_guide(guide, f"/sessions/{session_id}/plans/{version}/pdf"),
            headers={"Cache-Control": "no-store", "Content-Security-Policy": f"default-src 'none'; connect-src 'self'; script-src 'sha256-{RESULT_SCRIPT_HASH}'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'",
                     "X-Content-Type-Options": "nosniff"})

    @app.get("/sessions/{session_id}/plans/{version}/pdf")
    def export_guide(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        guide = load_guide(session_id, version)
        return Response(guide_pdf(guide), media_type="application/pdf",
            headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="travelmate-v{version}.pdf"'})

    @app.get('/sessions/{session_id}/plans/{version}/md')
    def export_guide_markdown(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        return Response(guide_markdown(load_guide(session_id, version)), media_type='text/markdown',
                        headers={'Content-Disposition': f'attachment; filename="travelmate-v{version}.md"'})

    @app.get('/sessions/{session_id}/plans/{version}/html')
    def export_guide_html(session_id: SessionId, version: Annotated[int, PathParam(ge=1)]):
        return HTMLResponse(render_guide(load_guide(session_id, version)),
                            headers={'Cache-Control': 'no-store',
                                     'Content-Disposition': f'attachment; filename="travelmate-v{version}.html"'})

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
                    if event == 'done':
                        archive_session(request.session_id)
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

    GuideId = Annotated[str, PathParam(pattern=r'^[a-f0-9]{32}$')]
    Version = Annotated[int, PathParam(ge=1)]

    def owned_guide(request, guide_id):
        owner = request.state.user['id'] if auth_enabled else 'local'
        return library.owned(app.state.agent, guide_id, owner)

    @app.get('/guides', include_in_schema=False)
    def guide_library_page():
        return FileResponse(Path(__file__).with_name('library.html'))

    @app.get('/assets/library.css', include_in_schema=False)
    def library_styles():
        return FileResponse(Path(__file__).with_name('library.css'), media_type='text/css')

    @app.get('/assets/library.js', include_in_schema=False)
    def library_script():
        return FileResponse(Path(__file__).with_name('library.js'), media_type='text/javascript')

    @app.get('/api/guides')
    def guide_library_list(request: Request):
        owner = request.state.user['id'] if auth_enabled else 'local'
        return {'guides': library.listing(app.state.agent, owner)}

    @app.patch('/api/guides/{guide_id}')
    def update_library_guide(guide_id: GuideId, data: GuideFavorite, request: Request):
        with trip_lock():
            item = owned_guide(request, guide_id)
            with app.state.agent.checkpointer.cursor() as cur:
                if data.favorite is not None:
                    cur.execute('UPDATE guide_library SET favorite=? WHERE id=?', (data.favorite, guide_id))
                if data.title is not None:
                    meta = json.loads(cur.execute('SELECT metadata FROM guide_library WHERE id=?', (guide_id,)).fetchone()[0])
                    meta['title'] = data.title
                    meta['custom_title'] = data.title
                    cur.execute('UPDATE guide_library SET metadata=? WHERE id=?', (json.dumps(meta, ensure_ascii=False), guide_id))
            return owned_guide(request, item['id'])

    @app.delete('/api/guides/{guide_id}')
    def delete_library_guide(guide_id: GuideId, request: Request):
        with trip_lock():
            owned_guide(request, guide_id)
            library.remove(app.state.agent, guide_id)
        return {'deleted': guide_id}

    @app.post('/api/guides/{guide_id}/resume')
    def resume_library_guide(guide_id: GuideId, request: Request):
        from langchain_core.messages import AIMessage
        with trip_lock():
            item = owned_guide(request, guide_id)
            session_id = item['session_id']
            values = app.state.agent.get_state({'configurable': {'thread_id': session_id}}).values
            state = get_workflow(app.state.agent, session_id)
            completed_node = 'present' if 'present' in app.state.agent.nodes else 'model'
            if not state.get('versions'):
                snapshots, preparation, budgets = [], {}, {}
                for row in reversed(library.versions(app.state.agent, guide_id)):
                    snapshot, guide = library.load(app.state.agent, guide_id, row['version'])
                    snapshots.append(snapshot)
                    preparation[str(row['version'])] = guide['preparation']
                    if guide['budget_edit']['revision']:
                        budgets[str(row['version'])] = guide['budget_edit']
                latest = snapshots[-1]
                state = {'requirements': latest['requirements'], 'plan_requirements': latest['requirements'],
                         'plan': latest['plan'], 'total': latest.get('total'), 'version': latest['version'],
                         'versions': snapshots, 'status': 'confirmed', 'preparation_lists': preparation, 'budget_lists': budgets}
                app.state.agent.update_state({'configurable': {'thread_id': session_id}}, {
                    'workflow': state, 'evidence': latest.get('evidence', {}),
                    'messages': [AIMessage(content='已从我的攻略恢复方案，可以继续提出调整需求。',
                                           additional_kwargs={'plan_version': latest['version']})]}, as_node=completed_node)
            elif not values.get('messages'):
                app.state.agent.update_state({'configurable': {'thread_id': session_id}}, {
                    'messages': [AIMessage(content='已打开保存的旅行方案，可以继续提出调整需求。',
                                           additional_kwargs={'plan_version': item['latest']})]}, as_node=completed_node)
            # Resume the saved plan rather than a pending task left by an interrupted run.
            config = {'configurable': {'thread_id': session_id}}
            if app.state.agent.get_state(config).next:
                app.state.agent.update_state(config, None, as_node='__end__')
        return {'session_id': session_id}

    def library_preview(guide_id, version, request):
        from travelmate.library_ui import detail_page
        with trip_lock():
            item = owned_guide(request, guide_id)
            version = version or item['latest']
            _, guide = library.load(app.state.agent, guide_id, version)
            guide['_preparation_url'] = f'/api/guides/{guide_id}/versions/{version}/preparation'
            guide['_budget_url'] = f'/api/guides/{guide_id}/versions/{version}/budget'
            document = render_guide(guide, f'/api/guides/{guide_id}/versions/{version}/pdf')
            return HTMLResponse(detail_page(document, item, library.versions(app.state.agent, guide_id), version),
                                headers={'Cache-Control': 'no-store'})

    @app.get('/guides/{guide_id}', include_in_schema=False)
    def library_latest(guide_id: GuideId, request: Request):
        return library_preview(guide_id, None, request)

    @app.get('/guides/{guide_id}/versions/{version}', include_in_schema=False)
    def library_version(guide_id: GuideId, version: Version, request: Request):
        return library_preview(guide_id, version, request)

    @app.get('/api/guides/{guide_id}/versions/{version}/preparation')
    def library_preparation(guide_id: GuideId, version: Version, request: Request):
        with trip_lock():
            owned_guide(request, guide_id)
            return library.load(app.state.agent, guide_id, version)[1]['preparation']

    @app.get('/api/guides/{guide_id}/versions/{version}/budget')
    def library_budget(guide_id: GuideId, version: Version, request: Request):
        with trip_lock():
            owned_guide(request, guide_id)
            return library.load(app.state.agent, guide_id, version)[1]['budget_edit']

    @app.put('/api/guides/{guide_id}/versions/{version}/budget')
    def save_library_budget(guide_id: GuideId, version: Version, data: budget.BudgetUpdate, request: Request):
        with trip_lock():
            item = owned_guide(request, guide_id)
            guide = library.load(app.state.agent, guide_id, version)[1]
            if guide['budget_edit']['revision'] != data.revision:
                raise HTTPException(409, '预算已在其他页面更新，请刷新后重新编辑')
            saved = budget.validate(guide, data)
            state = get_workflow(app.state.agent, item['session_id'])
            if state.get('versions'):
                state['budget_lists'] = {**state.get('budget_lists', {}), str(version): saved}
                save_workflow(app.state.agent, item['session_id'], state)
            with app.state.agent.checkpointer.cursor() as cur:
                cur.execute('UPDATE guide_versions SET budget=? WHERE guide_id=? AND version=?',
                            (json.dumps(saved, ensure_ascii=False), guide_id, version))
            return saved

    @app.put('/api/guides/{guide_id}/versions/{version}/preparation')
    def save_library_preparation(guide_id: GuideId, version: Version, data: PreparationUpdate, request: Request):
        with trip_lock():
            item = owned_guide(request, guide_id)
            current = library.load(app.state.agent, guide_id, version)[1]['preparation']
            if data.revision != current['revision']:
                raise HTTPException(409, '清单已更新，请刷新后重新编辑')
            saved = {'revision': current['revision'] + 1, 'items': [i.model_dump() for i in data.items]}
            state = get_workflow(app.state.agent, item['session_id'])
            if state.get('versions'):
                state['preparation_lists'] = {**state.get('preparation_lists', {}), str(version): saved}
                save_workflow(app.state.agent, item['session_id'], state)
            with app.state.agent.checkpointer.cursor() as cur:
                cur.execute('UPDATE guide_versions SET preparation=? WHERE guide_id=? AND version=?',
                            (json.dumps(saved, ensure_ascii=False), guide_id, version))
            return saved

    @app.get('/api/guides/{guide_id}/versions/{version}/{format}')
    def library_export(guide_id: GuideId, version: Version, format: Literal['pdf', 'md', 'html'], request: Request):
        with trip_lock():
            owned_guide(request, guide_id)
            _, guide = library.load(app.state.agent, guide_id, version)
        content = guide_pdf(guide) if format == 'pdf' else guide_markdown(guide) if format == 'md' else render_guide(guide)
        media = {'pdf': 'application/pdf', 'md': 'text/markdown', 'html': 'text/html'}[format]
        return Response(content, media_type=media, headers={
            'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="travelmate-v{version}.{format}"'})

    return app


app = create_app()
