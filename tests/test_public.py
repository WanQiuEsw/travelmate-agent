from langchain_core.messages import ToolMessage

from travelmate.public import public_data


def test_identifiers_hidden_in_history_plan_and_source(monkeypatch):
    monkeypatch.setenv("ALIYUN_INDEX_ID", "index-private-123")
    messages = [ToolMessage(content='{"results":[{"document_id":"doc-private-456"}]}', tool_call_id="old")]
    value = {"source": "杭州攻略 doc-private-456 index-private-123", "doc_id": "private",
             "notes": "知识库ID：kb-private-789"}
    result = public_data(value, messages)
    assert result["source"].startswith("杭州攻略")
    assert "private" not in str(result)
    assert "doc_id" not in result


def test_amap_reference_keeps_query_failure_status():
    from travelmate.public import public_answer
    text = "## 参考来源\n- 高德地图地点搜索：查询失败\n- 高德地图地点搜索：查询匹配"
    assert "查询失败" in public_answer(text)
    assert "查询匹配" in public_answer(text)


def test_review_evidence_identifiers_hidden_in_prose():
    from travelmate.public import public_answer
    assert "a" * 32 not in public_answer("引用" + " " + "a" * 32 + ":0 的地点仍待核实")


def test_machine_readable_evidence_references_survive_cleaning():
    ref = 'a' * 32 + ':0'
    data = {'evidence': {ref: {'id': ref}}, 'fact_refs': {'place': ref}}
    assert public_data(data) == data


def test_travel_prose_hides_coordinates_and_translates_internal_fields():
    from travelmate.public import public_answer
    text = '洪崖洞(106.579027,29.562204)到北仓文创街区（106.538685，29.578539）；行程给travel_minutes 30分钟且标注transit；`transport_mode`为`walking`。'
    result = public_answer(text)
    assert '106.' not in result and '29.562204' not in result
    assert 'travel_minutes' not in result and 'transport_mode' not in result
    assert '交通预留时间 30分钟' in result and '公交/地铁' in result and '步行' in result
    assert '洪崖洞到北仓文创街区' in result


def test_output_cleaning_preserves_evidence_and_navigation_links():
    from travelmate.public import public_answer
    url = 'https://uri.amap.com/marker?position=106.579027,29.562204&name=transit'
    assert public_answer('[查看地图](' + url + ')') == '[查看地图](' + url + ')'
    evidence = {'location': '106.579027,29.562204', 'transport_mode': 'walking'}
    assert public_data(evidence) == evidence
