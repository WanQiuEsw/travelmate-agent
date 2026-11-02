"""Local single-user HTTP service. Bind to loopback only."""
import logging
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from travelmate.agent import chat, open_agent


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

    return app


app = create_app()
