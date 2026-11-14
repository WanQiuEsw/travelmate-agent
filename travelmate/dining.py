"""Fill missing meal slots without inventing restaurants, prices or opening hours."""
from copy import deepcopy
import re


MEALS = ('早餐', '午餐', '晚餐')


def complete_meals(foods, days, dietary=''):
    result = deepcopy(foods)
    for day in range(1, days + 1):
        for meal in MEALS:
            if any(food.get('day') == day and food.get('meal') == meal for food in result):
                continue
            candidates = [food for food in foods if food.get('meal') == meal and food.get('day') in (None, day)]
            if meal != '早餐':
                candidates += [food for food in foods if food.get('meal', '不限') == '不限' and food.get('day') in (None, day)]
            else:
                candidates += [food for food in foods if food.get('meal', '不限') == '不限'
                               and food.get('day') in (None, day) and re.search('粥|豆浆|包子|馄饨|肠粉|面|饼', food['name'])]
            used = {food['name'] for food in result if food.get('day') == day}
            candidates = [food for food in candidates if food['name'] not in used]
            if candidates:
                chosen = deepcopy(candidates[(day - 1) % len(candidates)])
                chosen.update(day=day, meal=meal)
            else:
                chosen = {'name': {'早餐': '住宿附近的当地早餐', '午餐': '游览片区的顺路午餐', '晚餐': '返程或住宿片区的晚餐'}[meal],
                          'description': {'早餐': '选择温热主食与饮品，按食量点单，给当天游览留出体力。',
                                          '午餐': '就近选择当地家常菜或主食，安排蔬菜，避免为用餐反复跨城。',
                                          '晚餐': '按当天活动量适量点单，避免连续重餐；较晚到达时选择仍营业的合适餐食。'}[meal],
                          'area': '结合当天行程就近选择；首末日按实际到离时刻，可在出发地、车站或机场用餐。',
                          'tips': '这是一项补充用餐建议，具体菜品与营业情况请到店确认。', 'day': day, 'meal': meal}
            if dietary:
                chosen['tips'] = (chosen.get('tips', '') + ' 饮食要求：' + dietary + '，点单前确认食材及交叉接触。')[:300]
            result.append(chosen)
    return result
