"""Content checks shared by generated recommendations and historical cards."""
import re


def is_specific_food(name):
    name = re.sub(r'\s+', '', name)
    if not name or name in {'早餐', '午餐', '晚餐', '正餐', '小吃', '美食', '当地美食', '当地特色',
                            '当地小吃', '特色小吃', '当地特色小吃', '当地特色美食', '本地菜', '家常菜',
                            '中餐', '西餐', '快餐', '简餐', '自助餐', '海鲜大餐'}:
        return False
    return not re.search(r'附近|顺路|酒店|住宿|返程|景区|公园|步行街|美食街|小吃街|餐厅|餐馆|饭店|大排档|用餐|觅食', name)
