from contextlib import contextmanager
import sqlite3

import pytest

from fastapi.testclient import TestClient

from travelmate.agent import open_agent, chat, delete_sessions, move_sessions, conversation
from travelmate.api import create_app
from travelmate.public import public_answer
from test_travelmate import BudgetModel


def test_session_groups_and_deletion_persist(tmp_path):
    @contextmanager
    def factory():
        with open_agent(model=BudgetModel(), database=tmp_path / "sessions.sqlite") as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        for key in ("one", "two", "three"):
            assert client.post("/chat", json={"session_id": key, "message": "预算"}).status_code == 200
        answer_id = client.get("/sessions/one").json()["messages"][-1]["message_id"]
        assert client.post("/sessions/group", json={"session_ids": ["one", "two"], "group": " 家庭游 "}).status_code == 200
        sessions = client.get("/sessions").json()["sessions"]
        assert {row["session_id"] for row in sessions if row.get("group") == "家庭游"} == {"one", "two"}
        assert client.post("/sessions/group", json={"session_ids": ["one", "missing"], "group": "错误"}).status_code == 404
        assert client.post("/sessions/delete", json={"session_ids": ["one", "../bad"]}).status_code == 422
        assert client.post("/sessions/delete", json={"session_ids": []}).status_code == 422
        assert client.post("/sessions/group", json={"session_ids": ["one"], "group": "x" * 61}).status_code == 422
        assert client.get("/sessions/one").json()["messages"]

    with TestClient(create_app(factory)) as client:
        assert sum(row.get("group") == "家庭游" for row in client.get("/sessions").json()["sessions"]) == 2
        assert client.post("/sessions/group", json={"session_ids": ["two"], "group": ""}).status_code == 200
        assert client.delete("/sessions/three").status_code == 200
        assert client.post("/sessions/delete", json={"session_ids": ["one", "two", "one"]}).status_code == 200
        assert client.get("/sessions").json()["sessions"] == []
        assert client.get("/sessions/one").json()["messages"] == []
        assert client.get(f"/sessions/one/answers/{answer_id}/pdf").status_code == 404
        assert client.get("/sessions/one/trip").json().get("plan") is None

    with TestClient(create_app(factory)) as client:
        assert client.get("/sessions").json()["sessions"] == []
        # Reusing an old key must not revive messages or group metadata.
        client.post("/chat", json={"session_id": "one", "message": "预算"})
        assert len(client.get("/sessions/one").json()["messages"]) == 2
        assert "group" not in client.get("/sessions").json()["sessions"][0]


def test_reference_labels_are_short_and_closing_advice_is_preserved():
    answer = public_answer("正文\n## 参考来源\n重庆旅行攻略知识库（城市、景点、交通）\n高德地图地点搜索：机场、景区\n高德地图驾车路线（机场至景区）\n\n如需调整交通，告诉我即可。")
    assert "使用了重庆旅行攻略知识库" in answer
    assert answer.count("通过高德地图查询") == 1
    assert "城市、景点" not in answer and "机场至景区" not in answer
    assert answer.endswith("如需调整交通，告诉我即可。")


def test_delete_rolls_back_if_database_write_fails(tmp_path):
    with open_agent(model=BudgetModel(), database=tmp_path / "rollback.sqlite") as agent:
        chat(agent, "one", "预算")
        move_sessions(agent, ["one"], "家庭游")
        with agent.checkpointer.cursor() as cur:
            cur.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON session_groups BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            delete_sessions(agent, ["one"])
        assert len(conversation(agent, "one")["messages"]) == 2
