"""把人工整理的城市攻略 Markdown 转成带元数据、切片友好的知识库条目。

用法：python scripts/normalize_kb.py <源目录> <输出目录>
默认：E:/test/travel-agent/data/knowledge/已录入 -> kb
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

# 每城元数据：省份/区域/别名/最佳季节/避开/标签/预算档/建议天数/交通枢纽/是否有地铁
CITIES = {
    '北京': dict(slug='beijing', province='北京市', region='华北', aliases=['帝都', '京城'],
                 season=['9月中旬-10月底', '4-5月'], avoid=['7-8月湿热', '春节/五一/十一人流'],
                 tags=['历史古迹', '博物馆', '长城', '胡同', '美食'], budget='中高', days=[3, 5],
                 hubs=['首都机场', '大兴机场', '北京南站', '北京西站', '北京北站'], metro=True),
    '天津': dict(slug='tianjin', province='天津市', region='华北', aliases=['津门'],
                 season=['4-5月', '9-10月'], avoid=['冬季雾霾', '暑期闷热'],
                 tags=['近代建筑', '海河夜景', '相声', '小吃'], budget='中', days=[1, 2],
                 hubs=['天津站', '天津西站', '滨海机场'], metro=True),
    '承德': dict(slug='chengde', province='河北省', region='华北', aliases=['避暑山庄'],
                 season=['6-9月'], avoid=['冬季极冷', '11-3月部分景区关闭'],
                 tags=['皇家园林', '寺庙', '避暑'], budget='经济', days=[1, 2],
                 hubs=['承德站', '承德南站'], metro=False),
    '大同': dict(slug='datong', province='山西省', region='华北', aliases=['平城'],
                 season=['5-10月'], avoid=['冬季严寒', '春季风沙'],
                 tags=['石窟', '古建', '悬空寺'], budget='经济', days=[2, 3],
                 hubs=['大同站', '大同南站', '云冈机场'], metro=False),
    '哈尔滨': dict(slug='harbin', province='黑龙江省', region='东北', aliases=['冰城'],
                  season=['12-2月冰雪', '6-8月避暑'], avoid=['4月化雪泥泞', '11月初无雪'],
                  tags=['冰雪', '俄式建筑', '滑雪'], budget='中', days=[2, 4],
                  hubs=['哈尔滨站', '哈尔滨西站', '太平机场'], metro=True),
    '大连': dict(slug='dalian', province='辽宁省', region='东北', aliases=['滨城'],
                season=['5-9月'], avoid=['冬季海风阴冷'],
                tags=['海滨', '广场', '海鲜', '老街'], budget='中', days=[2, 3],
                hubs=['大连站', '大连北站', '周水子机场'], metro=True),
    '长白山': dict(slug='changbaishan', province='吉林省', region='东北', aliases=['天池'],
                 season=['6-9月看天池', '12-2月滑雪'], avoid=['5月积雪未化', '10月封山过渡期'],
                 tags=['天池', '滑雪', '温泉', '森林'], budget='中高', days=[3, 4],
                 hubs=['长白山机场', '松江河站', '敦化站'], metro=False),
    '上海': dict(slug='shanghai', province='上海市', region='华东', aliases=['魔都', '申城'],
                season=['3-5月', '9-11月'], avoid=['梅雨季6月', '7-8月湿热'],
                tags=['城市漫步', '本帮菜', '老洋房', '博物馆', '夜景'], budget='高', days=[2, 4],
                hubs=['虹桥机场', '浦东机场', '上海虹桥站', '上海站'], metro=True),
    '南京': dict(slug='nanjing', province='江苏省', region='华东', aliases=['金陵'],
                season=['3-4月', '10-11月'], avoid=['7-8月酷热', '梅雨季'],
                tags=['历史', '民国建筑', '小吃', '博物馆'], budget='中', days=[2, 3],
                hubs=['南京南站', '南京站', '禄口机场'], metro=True),
    '苏州': dict(slug='suzhou', province='江苏省', region='华东', aliases=['姑苏'],
                season=['3-5月', '9-11月'], avoid=['梅雨季', '暑期园林暴晒'],
                tags=['园林', '古镇', '评弹', '面食'], budget='中', days=[2, 3],
                hubs=['苏州站', '苏州北站', '无锡硕放机场'], metro=True),
    '扬州': dict(slug='yangzhou', province='江苏省', region='华东', aliases=['广陵'],
                season=['3-5月', '9-11月'], avoid=['夏季闷热'],
                tags=['园林', '早茶', '运河'], budget='中', days=[1, 2],
                hubs=['扬州站', '扬州东站'], metro=False),
    '杭州': dict(slug='hangzhou', province='浙江省', region='华东', aliases=['临安', '西湖'],
                season=['3-4月', '10-11月'], avoid=['梅雨季', '五一/十一'],
                tags=['西湖', '茶', '寺庙', '周边古镇'], budget='中高', days=[2, 4],
                hubs=['杭州东站', '杭州站', '萧山机场'], metro=True),
    '乌镇': dict(slug='wuzhen', province='浙江省', region='华东', aliases=['水乡'],
                season=['3-5月', '9-11月'], avoid=['暑期人多', '冬季湿冷'],
                tags=['水乡', '古镇', '夜景'], budget='中', days=[1, 2],
                hubs=['桐乡站', '乌镇汽车站'], metro=False),
    '黄山': dict(slug='huangshan', province='安徽省', region='华东', aliases=['徽州', '屯溪'],
                season=['3-5月', '9-11月'], avoid=['暑期人流', '冬季部分索道检修'],
                tags=['山岳', '云海', '古村落', '徽菜'], budget='中高', days=[3, 4],
                hubs=['黄山北站', '屯溪机场'], metro=False),
    '厦门': dict(slug='xiamen', province='福建省', region='华东', aliases=['鹭岛'],
                season=['3-5月', '10-12月'], avoid=['7-9月台风', '暑期鼓浪屿人流'],
                tags=['海岛', '骑楼', '沙茶面', '校园'], budget='中高', days=[2, 4],
                hubs=['厦门站', '厦门北站', '高崎机场'], metro=True),
    '泉州': dict(slug='quanzhou', province='福建省', region='华东', aliases=['鲤城', '刺桐'],
                season=['3-5月', '10-12月'], avoid=['7-9月台风', '夏季暴晒'],
                tags=['世遗', '宗教建筑', '小吃', '古城'], budget='经济', days=[2, 3],
                hubs=['泉州站', '泉州东站', '晋江机场'], metro=False),
    '青岛': dict(slug='qingdao', province='山东省', region='华东', aliases=['岛城'],
                season=['6-9月'], avoid=['8月人挤', '冬季海风'],
                tags=['海滨', '德式建筑', '啤酒', '海鲜'], budget='中', days=[2, 4],
                hubs=['青岛站', '青岛北站', '胶东机场'], metro=True),
    '武汉': dict(slug='wuhan', province='湖北省', region='华中', aliases=['江城'],
                season=['3-4月樱花', '10-11月'], avoid=['7-8月酷热'],
                tags=['樱花', '长江', '过早', '博物馆'], budget='中', days=[2, 3],
                hubs=['武汉站', '汉口站', '天河机场'], metro=True),
    '长沙': dict(slug='changsha', province='湖南省', region='华中', aliases=['星城'],
                season=['3-5月', '9-11月'], avoid=['7-8月高温', '节假日人流'],
                tags=['小吃', '夜生活', '书院', '橘子洲'], budget='经济', days=[2, 3],
                hubs=['长沙南站', '长沙站', '黄花机场'], metro=True),
    '张家界': dict(slug='zhangjiajie', province='湖南省', region='华中', aliases=['武陵源'],
                 season=['4-6月', '9-10月'], avoid=['暑期排队', '冬季部分索道停运'],
                 tags=['山岳', '峡谷', '索道', '徒步'], budget='中高', days=[3, 4],
                 hubs=['张家界站', '张家界西站', '荷花机场'], metro=False),
    '洛阳': dict(slug='luoyang', province='河南省', region='华中', aliases=['神都'],
                season=['4月牡丹', '9-10月'], avoid=['暑期高温'],
                tags=['石窟', '牡丹', '古都', '汤馆'], budget='经济', days=[2, 3],
                hubs=['洛阳龙门站', '洛阳站', '北郊机场'], metro=True),
    '广州': dict(slug='guangzhou', province='广东省', region='华南', aliases=['羊城', '穗'],
                season=['10-12月', '3-4月'], avoid=['5-9月湿热多雨', '回南天'],
                tags=['早茶', '骑楼', '城市漫步', '粤菜'], budget='中高', days=[2, 3],
                hubs=['广州南站', '广州站', '白云机场'], metro=True),
    '桂林': dict(slug='guilin', province='广西壮族自治区', region='华南', aliases=['阳朔', '漓江'],
                season=['4-6月', '9-11月'], avoid=['7-8月暴雨涨水', '冬季枯水'],
                tags=['喀斯特', '漓江', '徒步', '米粉'], budget='中', days=[3, 4],
                hubs=['桂林北站', '桂林站', '两江机场'], metro=False),
    '三亚': dict(slug='sanya', province='海南省', region='华南', aliases=['鹿城'],
                season=['11-4月'], avoid=['春节价格翻倍', '5-10月台风季'],
                tags=['海滨', '度假', '潜水', '海鲜'], budget='高', days=[3, 5],
                hubs=['三亚凤凰机场', '三亚站', '亚龙湾站'], metro=False),
    '香港': dict(slug='hongkong', province='中国香港', region='华南', aliases=['港', 'HK'],
                season=['10-12月'], avoid=['6-9月台风', '春节人流'],
                tags=['购物', '茶餐厅', '郊野徒步', '夜景'], budget='高', days=[2, 4],
                hubs=['香港西九龙站', '赤鱲角机场'], metro=True,
                note='内地居民需持有效港澳通行证及签注；港币计价。'),
    '澳门': dict(slug='macau', province='中国澳门', region='华南', aliases=['Macau'],
                season=['10-12月'], avoid=['6-9月台风', '春节人流'],
                tags=['世遗', '葡式建筑', '小吃', '娱乐场'], budget='高', days=[1, 2],
                hubs=['澳门国际机场', '横琴口岸', '拱北口岸'], metro=False,
                note='内地居民需持有效港澳通行证及澳门签注；澳门币计价。'),
    '成都': dict(slug='chengdu', province='四川省', region='西南', aliases=['蓉城', '锦官城'],
                season=['3-4月', '9-11月'], avoid=['7-8月闷热', '冬季雾霾'],
                tags=['美食', '熊猫', '茶馆', '周边古镇'], budget='中', days=[2, 4],
                hubs=['成都东站', '成都南站', '天府机场', '双流机场'], metro=True),
    '重庆': dict(slug='chongqing', province='重庆市', region='西南', aliases=['山城', '雾都'],
                season=['3-5月', '9-11月'], avoid=['7-8月酷热', '冬季多雾'],
                tags=['立体城市', '火锅', '夜景', '轻轨'], budget='中', days=[2, 3],
                hubs=['重庆北站', '重庆西站', '江北机场'], metro=True),
    '昆明': dict(slug='kunming', province='云南省', region='西南', aliases=['春城'],
                season=['全年皆宜', '11-3月红嘴鸥'], avoid=['6-8月雨季'],
                tags=['避暑', '花卉', '米线', '中转'], budget='经济', days=[1, 2],
                hubs=['昆明南站', '昆明站', '长水机场'], metro=True),
    '大理': dict(slug='dali', province='云南省', region='西南', aliases=['苍山洱海'],
                season=['3-5月', '9-11月'], avoid=['6-8月雨季', '春节'],
                tags=['洱海', '古城', '骑行', '白族'], budget='中', days=[2, 4],
                hubs=['大理站', '大理机场'], metro=False),
    '丽江': dict(slug='lijiang', province='云南省', region='西南', aliases=['大研', '束河'],
                season=['3-5月', '9-11月'], avoid=['7-8月雨季', '冬季早晚极冷'],
                tags=['古城', '雪山', '纳西', '泸沽湖中转'], budget='中高', days=[3, 5],
                hubs=['丽江站', '三义机场'], metro=False),
    '拉萨': dict(slug='lhasa', province='西藏自治区', region='西南', aliases=['日光城'],
                season=['5-10月'], avoid=['11-3月部分线路封闭', '雨季7-8月'],
                tags=['高原', '寺庙', '布达拉宫', '朝圣'], budget='中高', days=[4, 7],
                hubs=['拉萨站', '贡嘎机场'], metro=False,
                note='海拔 3650 米，需预留适应时间；布达拉宫需实名预约。'),
    '西安': dict(slug='xian', province='陕西省', region='西北', aliases=['长安'],
                season=['3-5月', '9-11月'], avoid=['7-8月高温', '冬季雾霾'],
                tags=['古都', '城墙', '陕菜', '博物馆'], budget='中', days=[2, 4],
                hubs=['西安北站', '西安站', '咸阳机场'], metro=True),
    '敦煌': dict(slug='dunhuang', province='甘肃省', region='西北', aliases=['沙州'],
                season=['5-10月'], avoid=['7-8月正午暴晒', '冬季景区淡季停运'],
                tags=['石窟', '戈壁', '壁画', '夜游'], budget='中', days=[2, 3],
                hubs=['敦煌站', '敦煌机场'], metro=False),
    '西宁': dict(slug='xining', province='青海省', region='西北', aliases=['夏都'],
                season=['6-9月'], avoid=['冬季严寒', '4月风沙'],
                tags=['高原', '青海湖中转', '清真美食', '塔尔寺'], budget='中', days=[2, 3],
                hubs=['西宁站', '曹家堡机场'], metro=False),
}

SECTION_MAP = {
    '城市概况与最佳旅游季节': 'city',
    '必去景点': 'spot',
    '必去景点及简介': 'spot',
    '推荐游览路线': 'route',
    '交通出行方式': 'transit',
    '住宿区域建议': 'stay',
    '特色美食': 'food',
    '实用注意事项': 'pitfall',
}

PRICE = re.compile(r'(\d{1,4})\s*元')
RESERVE = re.compile(r'提前\s*(\d{1,2})\s*天')
CLOCK = re.compile(r'(\d{1,2}:\d{2})\s*(?:在|准时|开售|放票)')
CLOSED = re.compile(r'周([一二三四五六日])[^，。]{0,4}闭馆')
METRO = re.compile(r'地铁\s*([0-9]+(?:/[0-9]+)?)\s*号线[^，。；]{0,6}?([\u4e00-\u9fa5]{2,6})站')
SECTION_TITLE = {'city': '城市概况与最佳季节', 'spot': '必去景点', 'route': '推荐游览路线',
                 'transit': '交通出行方式', 'stay': '住宿区域建议', 'food': '特色美食',
                 'pitfall': '实用注意事项'}


def facts(text):
    """从一段原文里抽出可速查的硬信息，抽不到就不写，绝不补。"""
    items = []
    if '免费' in text:
        items.append('门票 免费')
    else:
        prices = [value for value in PRICE.findall(text)][:2]
        if prices:
            items.append('门票 ' + '/'.join(prices) + ' 元')
    days = RESERVE.search(text)
    clock = CLOCK.search(text)
    if days:
        items.append(f'提前{days.group(1)}天预约' + (f'（{clock.group(1)} 放票）' if clock else ''))
    elif '预约' in text or '实名' in text:
        items.append('需预约')
    closed = CLOSED.search(text)
    if closed:
        items.append(f'周{closed.group(1)}闭馆')
    metro = METRO.search(text)
    if metro:
        station = re.sub(r'^[到往至在坐乘]', '', metro.group(2))
        items.append(f'地铁 {metro.group(1)} 号线{station}站')
    return ' · '.join(items)


def split_long(paragraph, limit=420):
    """超长段落按句切开，向量切片更稳；不改一个字的措辞。"""
    if len(paragraph) <= limit:
        return [paragraph]
    parts, current = [], ''
    for sentence in re.split(r'(?<=[。！？])', paragraph):
        if current and len(current) + len(sentence) > limit:
            parts.append(current)
            current = sentence
        else:
            current += sentence
    if current.strip():
        parts.append(current)
    return parts


def yaml_value(value):
    if isinstance(value, list):
        return '[' + ', '.join(json.dumps(item, ensure_ascii=False) for item in value) + ']'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return json.dumps(value, ensure_ascii=False)


def convert(source: Path, target: Path):
    checked = date(2026, 11, 3)
    index = {}
    for path in sorted(source.glob('*.md')):
        city = path.stem
        meta = CITIES.get(city)
        if not meta:
            print('skip (no metadata):', city)
            continue
        lines = path.read_text(encoding='utf-8').splitlines()
        body, section, spot = [], None, None
        for line in lines[1:]:  # 丢掉一级标题，元数据里有
            heading = re.match(r'^##\s+(.+?)\s*$', line)
            sub = re.match(r'^###\s+(.+?)\s*$', line)
            if heading:
                name = heading.group(1)
                # 两批文件分别写成「北京·必去景点」「中国香港·必去景点」，统一去掉前缀
                name = name.split('·', 1)[1].strip() if '·' in name else name.strip()
                kind = SECTION_MAP.get(name)
                if not kind:
                    print('skip section:', city, name)
                    continue
                section, spot = kind, None
                body += ['', '## ' + SECTION_TITLE[kind], '']
                continue
            if sub and section == 'spot':
                spot = re.sub(r'（[^）]*）$', '', sub.group(1)).strip()
                body += ['', '### ' + spot, '']
                continue
            text = line.strip()
            if not text:
                continue
            if text.startswith('> '):
                continue  # 旧版开头说明，统一换到元数据与「参考与时效」
            if section == 'spot' and spot and not text.startswith('**') and '速查' not in text:
                quick = facts(text)
                if quick:
                    body += [f'> 速查：{quick}', '']
            body += [paragraph for paragraph in split_long(text)]
            body.append('')
        front = ['---', 'schema: travelmate-kb/1', f'city: {yaml_value(city)}',
                 f'slug: {yaml_value(meta["slug"])}', f'province: {yaml_value(meta["province"])}',
                 f'region: {yaml_value(meta["region"])}', f'aliases: {yaml_value(meta["aliases"])}',
                 f'best_season: {yaml_value(meta["season"])}', f'avoid: {yaml_value(meta["avoid"])}',
                 f'tags: {yaml_value(meta["tags"])}', f'budget_level: {yaml_value(meta["budget"])}',
                 f'typical_days: {yaml_value(meta["days"])}', f'transport_hubs: {yaml_value(meta["hubs"])}',
                 f'has_metro: {yaml_value(meta["metro"])}', 'source: 人工整理']
        if meta.get('note'):
            front.append(f'note: {yaml_value(meta["note"])}')
        front += [f'checked_at: {checked.isoformat()}', f'valid_until: {date(2027, 5, 3).isoformat()}',
                  'confidence: medium', '---', '']
        tail = ['', '## 参考与时效', '',
                '本条目票价与预约政策核对于 2026 年 11 月，由人工整理，未逐项联网复核。',
                '出行前请以景区官方小程序或公众号当日公示为准；票价、开放时间、预约规则可能随时调整。',
                '本条目有效期至 2027-05-03，过期后价格与班次信息需重新核对。', '']
        # 文件名用中文城市名：和百炼里的文档名一致，本地检索也能按城市匹配
        output = target / 'cities' / (city + '.md')
        output.parent.mkdir(parents=True, exist_ok=True)
        text = '\n'.join(front + [f'# {city}'] + body + tail)
        output.write_text(re.sub(r'\n{3,}', '\n\n', text), encoding='utf-8')
        index[city] = {key: meta[key] for key in ('slug', 'province', 'region', 'aliases', 'tags',
                                                 'budget', 'days', 'hubs')} | {'file': f'cities/{city}.md'}
    (target / '_index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')
    return index


if __name__ == '__main__':
    source = Path(sys.argv[1] if len(sys.argv) > 1 else r'E:/test/travel-agent/data/knowledge/已录入')
    target = Path(sys.argv[2] if len(sys.argv) > 2 else 'kb')
    entries = convert(source, target)
    print(f'converted {len(entries)} entries -> {target}')
