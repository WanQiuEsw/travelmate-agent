"""Local single-user HTTP service. Bind to loopback only."""
import logging
import json
from pathlib import Path
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from travelmate.agent import chat, open_agent, stream_chat


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

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def respond(request: ChatRequest):
        try:
            with lock:
                answer = chat(app.state.agent, request.session_id, request.message)
            return ChatResponse(session_id=request.session_id, answer=answer)
        except Exception:
            logging.getLogger(__name__).warning("Agent request failed")
            raise HTTPException(502, "智能体请求失败，请检查服务配置或稍后重试") from None

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
