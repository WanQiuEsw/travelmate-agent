"""Version-scoped user budgets; model estimates remain in the original snapshot."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class BudgetItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: int = Field(ge=0, le=2000)
    amount_cents: int | None = Field(ge=0, le=10000000000)
    included: bool


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=0)
    limit_cents: int | None = Field(ge=0, le=10000000000)
    items: list[BudgetItem] = Field(max_length=2000)


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def initial(guide):
    from travelmate.result import split_expenses
    meta = guide.get('result', {})
    ledger = split_expenses(meta.get('ledger') or [])
    return {'revision': 0,
            'limit_cents': cents(meta['budget']) if meta.get('budget') is not None and meta.get('budget_currency', 'CNY') == 'CNY' else None,
            'items': [{'id': i, 'amount_cents': cents(row['amount']) if row['amount'] is not None else None,
                       'included': row['amount'] is not None} for i, row in enumerate(ledger)]}


def validate(guide, data):
    if guide.get('result', {}).get('ledger') is None:
        raise HTTPException(409, '历史方案缺少费用分项，请先生成新版攻略')
    expected = initial(guide)
    ids = [item.id for item in data.items]
    if len(ids) != len(set(ids)) or set(ids) != {i['id'] for i in expected['items']}:
        raise HTTPException(422, '费用项目已变化，请刷新攻略后重新编辑')
    if guide.get('result', {}).get('budget_currency', 'CNY') != 'CNY' and data.limit_cents is not None:
        raise HTTPException(422, '当前预算编辑仅支持人民币')
    return {**data.model_dump(), 'revision': data.revision + 1}


def overlay(guide, saved=None):
    from travelmate.result import split_expenses
    original = initial(guide)
    state = saved if saved is not None else original
    guide['budget_edit'] = deepcopy(state)
    meta = guide.get('result', {})
    if meta.get('ledger') is None:
        return guide
    ledger = deepcopy(split_expenses(meta.get('ledger') or []))
    edits = {item['id']: item for item in state['items']}
    for i, row in enumerate(ledger):
        row['original_amount'] = row['amount']
        row['original_included'] = row['amount'] is not None
        if saved is not None and i in edits:
            item = edits[i]
            row['amount'] = item['amount_cents'] / 100 if item['amount_cents'] is not None else None
            row['included'] = item['included']
            row['status'] = '用户填写，非已核实报价'
    meta['ledger'] = ledger
    meta['original_budget'] = original['limit_cents'] / 100 if original['limit_cents'] is not None else None
    meta['budget_revision'] = state['revision']
    meta['budget_endpoint'] = guide.get('_budget_url', '')
    if saved is None:
        return guide
    meta['budget'] = state['limit_cents'] / 100 if state['limit_cents'] is not None else None
    total = sum(item['amount_cents'] or 0 for item in state['items'] if item['included'])
    unknown = sum(item['included'] and item['amount_cents'] is None for item in state['items'])
    display = f'¥{total / 100:.2f}（用户保存' + ('，另有待核实项目）' if unknown else '）')
    meta['cost'] = display
    guide['total'] = total / 100
    per_person = (Decimal(total) / (meta.get('travelers') or 1) / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    meta['per_person'] = f'¥{per_person:.2f}（用户保存）'
    table = []
    for i, row in enumerate(ledger):
        item = edits[i]
        table.append([row['name'], '待核实' if item['amount_cents'] is None else f'¥{item["amount_cents"] / 100:.2f}',
                      '计入' if item['included'] else '不计入'])
    limit = '待确认' if state['limit_cents'] is None else f'¥{state["limit_cents"] / 100:.2f}'
    section = {'title': '用户保存的预算', 'kind': 'budget', 'columns': ['费用项目', '全员金额', '计入合计'],
               'rows': table, 'items': [{'text': f'全员预算上限：{limit}；已计入合计：{display}。'},
               {'text': '金额由用户保存，不代表商家报价；每日行程中的原始估算保留供参考。'}]}
    sections = guide['sections']
    first = next((i for i, s in enumerate(sections) if s['kind'] == 'budget'), 1)
    guide['sections'] = [s for s in sections if s['kind'] != 'budget']
    guide['sections'].insert(first, section)
    for s in guide['sections']:
        if s['kind'] == 'overview':
            for row in s.get('rows', []):
                if row[0] == '预算':
                    row[1] = f'全员 {limit}（用户保存）'
                elif row[0].startswith('预算余量'):
                    row[1] = '待确认' if state['limit_cents'] is None else f'¥{(state["limit_cents"] - total) / 100:.2f}（用户保存）'
    return guide
