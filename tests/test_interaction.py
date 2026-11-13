from contextlib import contextmanager
import json

from fastapi.testclient import TestClient

from travelmate.agent import chat, conversation, stream_chat
from travelmate.api import create_app
from travelmate.workflow import get_workflow
from test_planner import Model, open_test
from test_workflow import REQ


def test_missing_fields_roundtrip_is_structured_and_survives_restart(tmp_path):
    model = Model(intake={"intent": "plan", "conditions": {"destination": "杭州", "start_date": REQ['start_date']}, "direction": "## 初步方向\n可考虑西湖。"})
    with open_test(tmp_path, model) as agent:
        frames = list(stream_chat(agent, "form", "想去杭州"))
        done = frames[-1][1]
        interaction = done["interaction"]
        keys = {field["key"] for field in interaction["fields"]}
        assert 'days' in keys and 'mobility' not in keys and 'destination' not in keys
        assert '已选目的地：杭州' in interaction['description']
        assert model.calls == ["Intake"]
    model = Model()
    with open_test(tmp_path, model) as agent:
        assert conversation(agent, "form")["messages"][-1]["interaction"] == interaction
        answer = chat(agent, "form", "已填写旅行条件", interaction_response={
            "id": interaction["id"], "answers": {key: REQ[key] for key in keys}})
        assert "Intake" not in model.calls
        assert get_workflow(agent, "form")["requirements"]["destination"] == "杭州"
        message = conversation(agent, "form")["messages"][-1]
        assert '杭州 · 1天旅行攻略已整理完成' in answer
        assert message["plan_version"] == 1 and "interaction" not in message


def test_destination_suggestions_wait_for_the_users_choice(tmp_path):
    conditions = {key: value for key, value in REQ.items() if key not in {"destination", "start_date"}}
    model = Model(intake={"intent": "plan", "conditions": conditions,
                          "destination_suggestions": ["青岛", " 威海 ", "厦门", "威海"],
                          "direction": "青岛适合城市漫步，威海适合沿海慢游，厦门可兼顾海岸与美食。"})
    with open_test(tmp_path, model) as agent:
        answer = chat(agent, "coast", "想去海边散步、吃点当地美食")
        interaction = conversation(agent, "coast")["messages"][-1]["interaction"]
        assert "威海适合沿海慢游" in answer
        assert [(field["key"], field["suggestions"]) for field in interaction["fields"]] == [
            ("destination", ["青岛", "威海", "厦门"])]
        assert not get_workflow(agent, "coast")["requirements"].get("destination")
        assert model.calls == ["Intake"]

        chat(agent, "coast", "目的地：威海", interaction_response={
            "id": interaction["id"], "answers": {"destination": "威海"}})
        requirements = get_workflow(agent, "coast")["requirements"]
        assert requirements["destination"] == "威海"
        assert requirements["origin"] == conditions["origin"]
        assert model.calls.count("Intake") == 1
        assert "Areas" in model.calls


def test_unclear_task_stops_before_tools_and_confirmation_resumes(tmp_path):
    model = Model(intake={"intent": "modify", "conditions": {}, "confirmation": {
        "question": "需要调整哪一部分？", "options": ["仅调整景点", "重新安排全部行程"]}})
    with open_test(tmp_path, model) as agent:
        chat(agent, "confirm", "把它改一下")
        interaction = conversation(agent, "confirm")["messages"][-1]["interaction"]
        assert interaction["fields"][0]["type"] == "select"
        assert model.calls == ["Intake"]
        model.intake = {"intent": "plan", "conditions": REQ}
        chat(agent, "confirm", "重新安排全部行程", interaction_response={
            "id": interaction["id"], "answers": {"decision": "重新安排全部行程"}})
        assert get_workflow(agent, "confirm")["status"] == "review"


def test_stale_form_does_not_change_conditions(tmp_path):
    model = Model(intake={"intent": "plan", "conditions": {"destination": "杭州"}})
    with open_test(tmp_path, model) as agent:
        chat(agent, "stale", "杭州")
        interaction = conversation(agent, "stale")["messages"][-1]["interaction"]
        before = get_workflow(agent, "stale")["requirements"].copy()
        text = chat(agent, "stale", "旧表单", interaction_response={"id": "0" * 32, "answers": {"days": 30}})
        assert "问题已更新" in text
        assert get_workflow(agent, "stale")["requirements"] == before
        assert conversation(agent, "stale")["messages"][-1]["interaction"] == interaction


def test_declining_confirmation_never_calls_model_or_tools(tmp_path):
    model = Model(intake={"intent": "modify", "confirmation": {"question": "是否重新安排？", "options": ["全部重排", "只改景点"]}})
    with open_test(tmp_path, model) as agent:
        chat(agent, 'cancel', '改一下')
        interaction = conversation(agent, 'cancel')['messages'][-1]['interaction']
        text = chat(agent, 'cancel', '暂不执行', interaction_response={'id': interaction['id'], 'answers': {'decision': '暂不执行'}})
        assert '已取消' in text
        assert model.calls == ['Intake']
        assert 'interaction' not in conversation(agent, 'cancel')['messages'][-1]


def test_invalid_numeric_answer_keeps_form_and_does_not_start_planning(tmp_path):
    model = Model(intake={"intent": "plan", "conditions": {"destination": "杭州"}})
    with open_test(tmp_path, model) as agent:
        chat(agent, "invalid", "杭州")
        interaction = conversation(agent, "invalid")["messages"][-1]["interaction"]
        answers = {field['key']: REQ[field['key']] for field in interaction['fields']}
        answers['days'] = 31
        chat(agent, "invalid", "提交条件", interaction_response={"id": interaction['id'], "answers": answers})
        assert conversation(agent, "invalid")["messages"][-1]["interaction"] == interaction
        assert model.calls == ['Intake']
        assert get_workflow(agent, 'invalid')['requirements'].get('days') is None


def test_api_stream_transports_form_answers(tmp_path):
    model = Model(intake={"intent": "plan", "conditions": {"destination": "杭州", "start_date": REQ['start_date']}})
    @contextmanager
    def factory():
        with open_test(tmp_path, model) as agent:
            yield agent
    with TestClient(create_app(factory, auth_enabled=False)) as client:
        response = client.post('/chat/stream', json={"session_id": "api-form", "message": "杭州"})
        done = [json.loads(frame.split('data: ', 1)[1]) for frame in response.text.split('\n\n') if frame.startswith('event: done')][0]
        interaction = done['interaction']
        answers = {field['key']: REQ[field['key']] for field in interaction['fields']}
        response = client.post('/chat/stream', json={"session_id": "api-form", "message": "提交条件",
            "interaction_response": {"id": interaction['id'], "answers": answers}})
        assert 'event: done' in response.text
        assert '旅行攻略已整理完成' in response.text and 'event: token' not in response.text
        saved = client.get('/sessions/api-form').json()['messages'][-1]
        assert saved['plan_version'] == 1 and '预算怎么用' not in saved['content']
        path = f'/sessions/api-form/plans/{saved["plan_version"]}'
        assert '预算怎么用' in client.get(path).text
        assert client.get(path + '/pdf').content.startswith(b'%PDF-')
        assert '预算怎么用' in client.get(path + '/md').text
        assert client.get('/sessions/api-form/trip').json()['status'] == 'review'
