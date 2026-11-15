from copy import deepcopy

import pytest

from travelmate.evidence import model_view, normalize
from travelmate.planner import research_view, transport_anchor
from test_workflow import REQ


@pytest.mark.parametrize('tool,count,length', [
    ('search_knowledge', 2, 800), ('search_xiaohongshu', 5, 1200), ('search_web', 4, 600),
])
def test_model_document_limits_keep_originals_and_citations(tool, count, length):
    records = normalize(tool, {'query': '杭州'}, {'results': [
        {'title': f'杭州攻略{i}', 'content': f'{i}杭州游览美食避坑' * 1000,
         'url': f'https://example.com/{i}'} for i in range(10)
    ]}, 'docs', REQ)
    original = deepcopy(records)
    compact = model_view(records)
    assert len(compact) == count
    for key, row in compact.items():
        assert row['id'] == key
        assert row['url'] == records[key]['url']
        assert row['verification'] == 'reference'
        assert len(row['value']) <= length and row['excerpt']
        assert 'query' not in row
    assert records == original


def test_duplicate_documents_do_not_consume_budget_or_remove_facts():
    records = {}
    for i in range(20):
        records.update(normalize('source-' + str(i), {}, {'results': [
            {'content': '共享原文'}, {'content': f'{i}杭州攻略' * 1000},
        ]}, f'docs-{i}', REQ))
    records.update(normalize('search_places', {}, {'results': [
        {'name': '西湖', 'location': '120.1,30.2', 'address': '杭州西湖区'},
    ]}, 'place', REQ))
    compact = model_view(records)
    docs = [row for row in compact.values() if row['kind'] == 'document']
    assert sum(len(row['value']) for row in docs) <= 10000
    assert sum(row['value'] == '共享原文' for row in docs) == 1
    assert compact['place:0']['value'] == '西湖'
    assert compact['place:0']['location'] == '120.1,30.2'


def test_new_results_take_priority_over_old_records_for_the_same_trip():
    records = normalize('search_knowledge', {}, {'results': [
        {'content': '旧资料1'}, {'content': '旧资料2'},
    ]}, 'old', REQ)
    for row in records.values():
        row['queried_at'] = '2025-01-01T00:00:00+00:00'
    records.update(normalize('search_knowledge', {}, {'results': [
        {'content': '新资料1'}, {'content': '新资料2'},
    ]}, 'new', REQ))
    assert set(model_view(records)) == {'new:0', 'new:1'}


def test_document_budget_covers_different_queries_before_taking_more_from_one():
    records = {}
    for topic in ('价格', '预约', '路线'):
        records.update(normalize('search_web', {'query': topic}, {'results': [
            {'content': f'{topic}{i}的完整资料'} for i in range(5)
        ]}, topic, REQ))
    compact = model_view(records)
    assert len(compact) == 4
    assert {'价格:0', '预约:0', '路线:0'} <= compact.keys()


def test_research_omits_repeated_text_but_retains_train_anchors_and_raw_records():
    research = [
        {'tool': 'search_knowledge', 'data': {'results': [
            {'content': '原始知识库正文', 'source': '杭州攻略', 'score': 0.9},
        ]}},
        {'tool': 'search_train_tickets', 'leg': '去程', 'data': {'results': [
            {'start_train_code': 'G1', 'start_time': '08:00', 'arrive_time': '10:00'},
        ]}},
        {'tool': 'search_web', 'data': {'error': 'unavailable'}},
    ]
    original = deepcopy(research)
    compact = research_view(research)
    assert 'content' not in compact[0]['data']['results'][0]
    assert compact[0]['data']['results'][0]['source'] == '杭州攻略'
    assert compact[-1]['data']['error'] == 'unavailable'
    assert transport_anchor(compact) == transport_anchor(research)
    assert compact[1] == research[1]
    assert research == original


def test_planning_stages_receive_one_copy_and_save_full_source(tmp_path, monkeypatch):
    import json
    from langchain.tools import tool
    from langchain_core.runnables import RunnableLambda
    from travelmate import agent as module
    from travelmate.workflow import get_workflow
    from test_planner import Model

    content = '杭州游览路线、美食小吃、排队避坑。UNIQUE_DOCUMENT_BODY ' + '完整原文。' * 500
    captured = {}

    @tool
    def search_knowledge(query: str, city: str = '') -> dict:
        """Return a long local source."""
        return {'results': [{'source': '杭州攻略', 'content': content}]}

    class CapturingModel(Model):
        def with_structured_output(self, schema, **kwargs):
            runnable = super().with_structured_output(schema, **kwargs)

            def run(messages):
                captured[schema.__name__] = messages[-1].content
                return runnable.invoke(messages)
            return RunnableLambda(run)

    monkeypatch.setattr(module, 'create_knowledge_tool', lambda directory: search_knowledge)
    with module.open_agent(model=CapturingModel(), database=tmp_path / 'context.sqlite', knowledge=tmp_path) as agent:
        module.chat(agent, 'context', '规划杭州')
        state = get_workflow(agent, 'context')
        raw = agent.get_state({'configurable': {'thread_id': 'context'}}).values
    for stage in ('Areas', 'Itinerary', 'ReviewReport'):
        assert captured[stage].count('UNIQUE_DOCUMENT_BODY') == 1
        data = json.loads(captured[stage])
        assert all(len(row['value']) <= 800 for row in data['evidence'].values() if row['kind'] == 'document')
    assert raw['research_data'][0]['data']['results'][0]['content'] == content
    assert next(row['value'] for row in state['evidence'].values() if row['kind'] == 'document') == content
    assert state['versions'][0]['evidence']
