from contextlib import contextmanager

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from travelmate.agent import open_agent
from travelmate.api import create_app
from test_travelmate import BudgetModel


class TravelAnswerModel(BudgetModel):
    def _generate(self, messages, **kwargs):
        request = next(m.text for m in reversed(messages) if isinstance(m, HumanMessage))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=f"## {request}\n09:00-11:00 游览，费用200元\n## 参考来源\n本地旅游资料"))])


def test_export_selected_answer_across_turns_sessions_and_restart(tmp_path, monkeypatch):
    import travelmate.api as api
    original = api.answer_pdf
    exported = []

    def capture(text):
        exported.append(text)
        return original(text)

    monkeypatch.setattr(api, "answer_pdf", capture)

    @contextmanager
    def factory():
        with open_agent(legacy_tool_loop=True, model=TravelAnswerModel(), database=tmp_path / "answers.sqlite", knowledge=tmp_path) as agent:
            yield agent

    with TestClient(create_app(factory)) as client:
        client.post('/chat', json={'session_id': 'same', 'message': '2026-12-01 上海两日游'})
        first = client.get('/sessions/same').json()['messages'][-1]
        client.post('/chat', json={'session_id': 'same', 'message': '2026-12-05 重庆三日游'})
        second = client.get('/sessions/same').json()['messages'][-1]
        assert first['message_id'] != second['message_id']
        client.post('/chat', json={'session_id': 'same', 'message': '2026-12-05 重庆三日游改成轻松路线'})
        for answer, city, other in ((first, '上海', '重庆'), (second, '重庆', '上海')):
            response = client.get(f"/sessions/same/answers/{answer['message_id']}/pdf")
            assert response.status_code == 200 and response.content.startswith(b'%PDF-')
            assert exported[-1] == answer['content']
            assert city in exported[-1] and other not in exported[-1]
        assert client.get(f"/sessions/other/answers/{first['message_id']}/pdf").status_code == 404
        assert client.get('/sessions/same/answers/' + '0' * 32 + '/pdf').status_code == 404
        assert client.get('/sessions/same/answers/bad/pdf').status_code == 422
    with TestClient(create_app(factory)) as client:
        assert client.get('/sessions/same').json()['messages'][1]['message_id'] == first['message_id']
        assert client.get(f"/sessions/same/answers/{first['message_id']}/pdf").status_code == 200
        assert '上海' in exported[-1] and '重庆' not in exported[-1]
