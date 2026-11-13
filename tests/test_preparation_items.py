
def test_compound_packing_items_are_independent_and_keep_context():
    from travelmate.preparation import initial_tasks, overlay
    from copy import deepcopy
    reminder = '电子：充电宝、数据线；老院子房间插座少，带个插排'
    guide = {'sections': [{'title': '行前准备', 'kind': 'verify', 'items': [{'text': reminder}]}]}
    items = initial_tasks(guide)
    assert [i['text'] for i in items] == ['充电宝', '数据线', '插排']
    assert all(i['detail'] == reminder for i in items)
    assert len({i['id'] for i in items}) == 3
    saved = {'revision': 3, 'items': [{'id': 'seed-0', 'text': reminder, 'done': True}]}
    migrated = overlay(deepcopy(guide), saved)['preparation']
    assert migrated['revision'] == 3 and all(i['done'] for i in migrated['items'])
    assert saved['items'][0]['text'] == reminder
    assert overlay(deepcopy(guide), migrated)['preparation'] == migrated
    saved['items'][0]['text'] = '自定义充电宝和数据线'
    assert len(overlay(deepcopy(guide), saved)['preparation']['items']) == 1


def test_packing_split_handles_documents_clothes_and_limit():
    from travelmate.preparation import split_task, expand_tasks
    assert [i['text'] for i in split_task({'id': 'seed-0', 'text': '身份证、学生证/老年证', 'done': False})] == ['身份证', '学生证', '老年证']
    assert [i['text'] for i in split_task({'id': 'seed-1', 'text': '春秋带薄外套，冬天要帽子手套；鞋选软底防滑', 'done': False})] == ['薄外套', '帽子', '手套', '鞋']
    tasks = [{'id': f'seed-{i}', 'text': '充电宝、数据线', 'done': False} for i in range(100)]
    assert len(expand_tasks(tasks)) == 100
