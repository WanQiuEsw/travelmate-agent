"""Daily dining cards rendered from the saved guide, including older snapshots."""
import re
from base64 import b64encode
from pathlib import Path
from travelmate.dining import complete_meals


CSS = """
.food-shell{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;position:relative;min-height:815px;padding:4px 0 0;color:#103d34}.food-content{width:calc(71% - 28px)}.food-heading small{font-size:22px;letter-spacing:2px}.food-heading h2{font:700 52px/1.35 Georgia,'Songti SC',SimSun,serif;border:0;padding:0;margin:6px 0 0}.food-heading p{font-size:20px;letter-spacing:1px;color:#535753;margin:0 0 24px}.food-picker{border:1px solid #a9bdaa;border-radius:17px;display:flex;padding:0;margin:0;width:416px;max-width:100%;overflow:hidden}.food-picker legend{position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden}.food-picker label{position:relative;flex:1;text-align:center;padding:5px 14px;cursor:pointer;font-size:20px;min-height:44px;white-space:nowrap}.food-picker label+label{border-left:1px solid #a9bdaa}.food-picker label:has(:checked){background:#b95128;color:white;border-radius:16px}.food-picker input{position:absolute;opacity:0;width:1px;height:1px}.food-picker label:has(:focus-visible){outline:3px solid #b95128;outline-offset:-4px}.food-day{display:none}.food-route{margin:0;position:absolute;right:calc(29% + 28px);top:159px;max-width:calc(71% - 470px);border-radius:40px;background:#e5eadb;padding:6px 22px;font-size:19px;font-weight:600;overflow-wrap:anywhere}.food-route svg{width:27px;height:27px;vertical-align:middle;margin-right:10px}.food-meals{position:relative;margin-top:44px;padding-left:110px;display:grid;gap:24px}.food-meals:before{content:'';position:absolute;left:5px;top:54px;bottom:96px;border-left:1px solid #58805c}.food-meal{position:relative;border:1px solid #a9bdaa;border-radius:17px;padding:12px 16px;display:grid;grid-template-columns:24% minmax(0,1fr) 26%;gap:24px;min-height:154px;align-items:center}.food-meal-label{position:absolute;left:-89px;top:32px;border-radius:30px;background:#fae4d5;color:#ae4d25;padding:5px 18px;font:700 20px/1.6 Georgia,'Songti SC',SimSun,serif}.food-meal-label:before{content:'';position:absolute;left:-25px;top:15px;width:11px;height:11px;border:2px solid #49764b;background:#faf8f3;border-radius:50%}.food-meal h3{font:700 28px/1.4 Georgia,'Songti SC',SimSun,serif;margin:0 0 5px}.food-meal p{margin:5px 0;font-size:16px;line-height:1.6;color:#484b46;overflow-wrap:anywhere}.food-meal .food-match{margin-top:10px}.food-match svg{width:19px;height:19px;vertical-align:middle;color:#527b58;margin-right:5px}.food-order{border-left:1px solid #cfcfc1;padding-left:24px;align-self:stretch;display:flex;flex-direction:column;justify-content:center}.food-order>span{background:#41694c;color:white;border-radius:30px;padding:2px 17px;align-self:flex-start;margin-bottom:10px;white-space:nowrap}.food-order strong{font-size:18px}.food-order p{margin:0}.food-photo{position:relative;overflow:hidden;border-radius:14px;aspect-ratio:210/137;align-self:center;min-height:0;background:#e6e8db}.food-photo{background-size:731.43% auto;background-position:13.122% 47.576%;background-repeat:no-repeat}.food-photo.noodles{aspect-ratio:210/128;background-position:13.122% 68.080%}.food-photo.dinner{aspect-ratio:210/119;background-position:13.122% 94.144%}.food-photo.generic{background-image:none;display:grid;place-items:center}.food-photo.generic svg{width:64px;height:64px;color:#58805c}.food-snack{min-height:58px;padding:0 20px;background:#edf0e4;grid-template-columns:120px auto minmax(0,1fr);gap:20px}.food-snack .food-photo{min-height:56px;height:56px;aspect-ratio:auto;border-radius:0}.food-snack .food-photo{background-size:1280% auto;background-position:12.712% 79.339%}.food-snack .food-meal-label{display:none}.food-snack h3{font-size:22px;margin:0}.food-snack>p{border-left:1px solid #b5c4ab;padding-left:20px}.food-aside{position:absolute;top:9px;right:0;width:29%;border:1px solid #afc0ad;border-radius:17px;padding:12px 18px 22px;min-height:815px}.food-aside h3{font:700 32px/1.4 Georgia,'Songti SC',SimSun,serif;margin:0 10px 12px}.food-rhythm{position:relative;height:210px;border-bottom:1px solid #d4d1c4;margin-bottom:6px}.food-landscape{position:absolute;bottom:14px;left:-17px;right:-17px;height:66px;overflow:hidden;opacity:.72}.food-landscape{background-size:364% auto;background-position:98.115% 37.996%;background-repeat:no-repeat}.food-waypoints{display:flex;justify-content:space-around;position:relative;z-index:1;padding-top:25px;gap:8px}.food-waypoint{text-align:center;font-weight:600;max-width:30%;font-size:16px;overflow-wrap:anywhere}.food-waypoint:nth-child(2){transform:translateY(-20px)}.food-waypoint>span{display:grid;place-items:center;background:#edf0df;border-radius:50%;width:54px;height:54px;margin:0 auto 3px;color:#4d7551}.food-waypoint svg{width:32px;height:32px}.food-curve{position:absolute;top:90px;width:100%;height:65px;z-index:1}.food-tip{display:flex;align-items:center;gap:20px;padding:16px 5px;border-bottom:1px solid #dedacf}.food-tip>span{flex-shrink:0;display:grid;place-items:center;width:52px;height:52px;background:#edf0df;border-radius:50%;color:#4c7550}.food-tip svg{width:32px;height:32px}.food-tip h4,.food-preference h4{font:700 22px/1.5 Georgia,'Songti SC',SimSun,serif;margin:0}.food-tip p{margin:0;font-size:16px;line-height:1.5;color:#4a4d47}.food-preference{background:#eaf0df;border-radius:18px;padding:16px 22px;margin-top:22px}.food-preference svg{width:35px;height:35px;vertical-align:middle;margin-right:14px}.food-preference p{margin:12px 0 0;color:#4a4d47;line-height:1.7}.food-disclaimer{font-size:14px;color:#646760;margin:32px 10px 0}.food-image-note{font-size:12px;color:#82857d;margin-top:12px}.food-extra{margin-top:18px;color:#63736c}.food-extra summary{font-size:14px}.food-flexible{font-size:14px;color:#63736c;margin:20px 0 -24px 110px}
body:not(.library-page):has(.panel-food:target) main{padding-left:44px;padding-right:20px}body:not(.library-page):has(.panel-food:target) .budget-header-art{display:none}body:not(.library-page):has(.panel-food:target) .result-nav{margin-bottom:25px}body:not(.library-page):has(.panel-food:target) .daily-masthead{border-bottom:1px solid #d6d2c8;padding-bottom:14px}body:not(.library-page):has(.panel-food:target) .result-nav a{font-size:22px;min-height:61px}body:not(.library-page):has(.panel-food:target) .result-nav a[aria-current=page]{position:relative}body:not(.library-page):has(.panel-food:target) .result-nav a[aria-current=page]:after{content:'';position:absolute;bottom:-1px;left:15%;right:15%;height:5px;background:#b95128;border-radius:5px 5px 0 0}
@media(max-width:1300px){.food-route{position:static;max-width:none;display:table;margin:16px 0 -24px}.food-meals{padding-left:85px;gap:20px}.food-meal{gap:14px;grid-template-columns:25% minmax(0,1fr);padding:12px}.food-order{grid-column:2;border-left:0;border-top:1px solid #d4d1c4;padding:10px 0 0}.food-order>span{margin-bottom:6px}.food-meal-label{left:-72px;padding:5px 12px;font-size:17px}.food-meal-label:before{left:-22px}.food-snack{grid-template-columns:85px 1fr}.food-snack>p{grid-column:2;border:0;padding:0}.food-aside{padding:14px}.food-aside h3{font-size:26px}.food-tip{gap:12px}.food-tip h4,.food-preference h4{font-size:19px}.food-content{width:calc(69% - 22px)}.food-aside{width:31%}.food-heading h2{font-size:44px}}
@media(max-width:850px){body:not(.library-page):has(.panel-food:target) main{padding:12px}.food-content{width:100%}.food-aside{position:static;width:100%;min-height:0;margin-top:24px}.food-shell{min-height:0}.food-heading h2{font-size:36px}.food-heading p{font-size:16px}.food-rhythm{height:210px;max-width:430px;margin-inline:auto}.food-heading small{font-size:17px}.food-meal h3{font-size:23px}.food-meal p{font-size:14px}.food-aside h3{font-size:28px}.food-meals{margin-top:34px}.food-route{font-size:16px}.food-flexible{margin-left:85px}.food-snack h3{font-size:19px}}
@media(max-width:480px){.food-meals{padding-left:62px}.food-meal{grid-template-columns:1fr}.food-meal-label{left:-60px;padding:5px 9px;font-size:15px}.food-meal-label:before{left:-13px;width:8px;height:8px;border-width:1px}.food-photo{min-height:0;aspect-ratio:210/137}.food-order{grid-column:1}.food-snack{grid-template-columns:70px 1fr}.food-snack>p{grid-column:1/-1}.food-snack .food-photo{height:40px;min-height:40px}.food-heading h2{font-size:32px}.food-flexible{margin-left:62px}.food-picker label{font-size:17px;padding:7px 9px}}
@media print{.food-picker,.food-route{display:none}.food-day{display:block!important}.food-content{width:100%}.food-aside{position:static;width:100%;min-height:0}.food-meal{break-inside:avoid}.food-shell{min-height:0}.food-heading h2{font-size:30px}}
"""

CSS += """
.food-shell{container-type:inline-size;container-name:food-panel}
.food-route{position:static;display:block;max-width:100%;margin:18px 0 0;padding:12px 16px;border-radius:14px;font-size:15px;line-height:1.7;white-space:normal;overflow-wrap:anywhere}
.food-meals{margin-top:24px}.food-picker{width:100%;max-width:520px;overflow-x:auto;justify-content:flex-start}.food-picker label{flex:0 0 auto;min-width:96px}
.food-waypoint{font-size:13px}.food-waypoint>small{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-size:inherit;font-weight:inherit;line-height:1.6}
.food-rhythm{height:230px}.food-curve{top:140px}
@container food-panel (max-width:1100px){.food-content{width:100%}.food-aside{position:static;width:100%;min-height:0;margin-top:24px}.food-meal{grid-template-columns:minmax(100px,25%) minmax(0,1fr);gap:16px}.food-order{grid-column:2;border-left:0;border-top:1px solid #d4d1c4;padding:10px 0 0}.food-heading h2{font-size:clamp(28px,5cqw,44px)}.food-heading p{font-size:16px}.food-rhythm{max-width:480px;margin-inline:auto}.food-snack{grid-template-columns:85px minmax(0,1fr)}.food-snack>p{grid-column:2}}
@container food-panel (max-width:560px){.food-meals{padding-left:62px}.food-meal{grid-template-columns:minmax(0,1fr);padding:12px;gap:12px}.food-order{grid-column:1}.food-meal-label{left:-60px;padding:5px 9px;font-size:15px}.food-meal-label:before{left:-13px;width:8px;height:8px;border-width:1px}.food-meal h3{font-size:22px}.food-meal p{font-size:14px}.food-picker label{min-width:88px;font-size:16px}.food-route{font-size:14px}.food-snack{grid-template-columns:70px minmax(0,1fr)}.food-snack>p{grid-column:1/-1}.food-flexible{margin-left:62px}}
@media print{.food-route{display:none}.food-content{width:100%}.food-aside{position:static;width:100%;min-height:0}}
"""

ICONS = {
    'pin': '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    'bowl': '<path d="M2 12h20c-1 7-5 9-10 9S3 19 2 12Zm5 10h10M7 2c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7"/>',
    'check': '<path d="M20 5v16H3V4h13M7 11l4 4L22 3"/>',
    'leaf': '<path d="M3 22 18 5M4 16C0 6 13 3 23 2c-2 12-6 19-19 14Z"/>',
    'gate': '<path d="M3 21V7h18v14M1 7l3-4h16l3 4M8 21V11h8v10M1 11h22"/>',
    'pagoda': '<path d="M12 1v3M4 8q5 0 8-4 3 4 8 4ZM2 14q6 0 10-4 4 4 10 4ZM1 21h22M6 8v13m12-13v13M4 17h16"/>',
    'route': '<circle cx="17" cy="5" r="4"/><circle cx="5" cy="19" r="2"/><path d="M16 9v6a4 4 0 0 1-4 4H7"/>',
}


def icon(name):
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[name] + '</svg>'


def panel(sections, days, text, inline_images=False):
    rows = [row for section in sections for row in section.get('rows', [])]
    notes = [item['text'] for section in sections for item in section.get('items', [])]
    asset = '/assets/visual/food-reference.png'
    if inline_images:
        asset = 'data:image/png;base64,' + b64encode(Path(__file__).with_name('images').joinpath('food-reference.png').read_bytes()).decode('ascii')

    def photo(kind):
        # shortcut: reference photographs are CSS crops; replace with individual dish assets when available.
        if kind == 'generic':
            return '<div class="food-photo generic" role="img" aria-label="餐饮示意">' + icon('bowl') + '</div>'
        return f'<div class="food-photo {kind}" role="img" aria-label="菜品示意图"></div>'

    out = [f"<style>.food-photo:not(.generic),.food-landscape{{background-image:url('{asset}')}}</style>" + '<div class="food-shell"><div class="food-content"><header class="food-heading"><small>02 / 每日用餐</small><h2 aria-label="当地特色美食">今天，顺路吃什么</h2><p>用餐跟着路线走，少绕路，也留一点休息时间</p></header><fieldset class="food-picker"><legend>选择用餐日</legend>']
    count = max(len(days), 1)
    for number in range(1, count + 1):
        out.append(f'<label><input type="radio" name="food-day" id="food-choice-{number}" aria-controls="food-day-{number}"' + (' checked' if number == 1 else '') + f'>第{number}天</label>')
    out.append('</fieldset>')
    for number in range(1, count + 1):
        out.append(f'<style>.food-shell:has(#food-choice-{number}:checked) #food-day-{number}' + '{display:block}</style>')
        out.append(f'<article id="food-day-{number}" class="food-day" aria-label="第{number}天用餐">')
        places = list(dict.fromkeys(row[1] for row in days[number-1].get('rows', []) if len(row) > 1)) if days else []
        route = places[:3]
        if route:
            out.append('<p class="food-route">' + icon('route') + text(' → '.join(route)) + '</p>')
        selected, shared = [], []
        for row in rows:
            values = (list(row) + [''] * 5)[:5]
            match = re.search(r'第\s*(\d+)\s*天', values[2])
            if not match:
                shared.append(values)
            elif int(match[1]) == number:
                selected.append(values)
        order = {'早餐': 0, '午餐': 1, '加餐': 2, '下午茶': 2, '晚餐': 3}
        selected.sort(key=lambda row: next((rank for meal, rank in order.items() if meal in row[2]), 4))
        if not selected and not shared:
            out.append('<p class="daily-empty">当天尚无用餐建议，以下提供基础安排，可在对话中补充口味与忌口。</p>')
        local = []
        for row in selected + shared:
            meal = next((meal for meal in ('早餐', '午餐', '晚餐', '加餐') if meal in row[2]), '不限')
            local.append(dict(name=row[0], description=row[1], day=1 if row in selected else None,
                              meal=meal, area=row[3], tips=row[4]))
        dietary = next((note for note in notes if note.startswith('饮食要求')), '')
        completed = complete_meals(local, 1, dietary)
        added = completed[len(local):]
        for food in added:
            selected.append([food['name'], food['description'], f'第{number}天 · {food["meal"]}', food['area'], food['tips']])
        selected.sort(key=lambda row: next((rank for meal, rank in order.items() if meal in row[2]), 4))
        for group, flexible in ((selected, False), (shared, True)):
            if not group:
                continue
            if flexible:
                out.append('<p class="food-flexible">灵活安排 · 以下推荐未指定日期，可结合当天片区选择</p>')
            out.append('<div class="food-meals">')
            for name, description, schedule, area, tips in group:
                meal = next((meal for meal in order if meal in schedule), '推荐')
                snack = meal in ('加餐', '下午茶')
                kind = ('breakfast' if any(w in name for w in ('包', '面点', '馒头')) else 'noodles' if any(w in name for w in ('面', '片儿川')) else 'dinner' if any(w in name for w in ('家常', '东坡肉', '红烧肉')) else 'snack' if '定胜糕' in name else 'generic')
                out.append('<section class="food-meal' + (' food-snack' if snack else '') + '"><span class="food-meal-label">' + text(meal) + '</span>' + photo(kind))
                if snack:
                    out.append('<h3>加餐 · ' + text(name) + '</h3><p>' + text(description) + '<br>' + text(area) + (' · ' + text(tips) if tips else '') + '</p>')
                else:
                    badge = {'早餐': '温和开场', '午餐': '地道之选', '晚餐': '舒适收尾'}.get(meal, '顺路之选')
                    out.append('<div><h3>' + text(name) + '</h3><p>' + text(description) + '</p><p class="food-match">' + icon('pin') + '路线契合：' + text(area or '结合当天片区顺路选择') + '</p></div><div class="food-order"><span>' + badge + '</span><strong>点单提醒：</strong><p>' + text(tips or '点单前与商家确认食材及口味。') + '</p></div>')
                out.append('</section>')
            out.append('</div>')
        out.append('<aside class="food-aside" aria-label="今天的用餐节奏"><h3>今天的用餐节奏</h3><div class="food-rhythm"><div class="food-landscape" aria-hidden="true"></div><div class="food-waypoints">')
        for i, place in enumerate(route):
            out.append('<div class="food-waypoint"><span>' + icon('pagoda' if i == 0 else 'gate') + '</span><small title="' + text(place) + '">' + text(place) + '</small></div>')
        out.append('</div><svg class="food-curve" viewBox="0 0 360 70" fill="none" aria-hidden="true"><path d="M25 50C90 60 95 8 170 23S260 70 335 39" stroke="#608564" stroke-width="2"/><g fill="#faf8f3" stroke="#48764e" stroke-width="2.5"><circle cx="25" cy="50" r="6"/><circle cx="170" cy="23" r="6"/><circle cx="335" cy="39" r="6"/></g></svg></div>')
        for symbol, title, copy in (('bowl', '避开连续重餐', '三餐安排轻重有序，保证游玩状态。'), ('pin', '排队过长就近替换', '遇到高峰可选择同片区的其他餐食，不耽误行程。'), ('check', '忌口随时确认', '点单前与店家确认食材与口味，更安心合口味。')):
            out.append('<div class="food-tip"><span>' + icon(symbol) + '</span><div><h4>' + title + '</h4><p>' + copy + '</p></div></div>')
        dietary = next((note for note in notes if note.startswith('饮食要求')), '')
        out.append('<div class="food-preference"><h4>' + icon('leaf') + ('饮食偏好 · 按需选择' if dietary else '饮食偏好 · 清淡优先') + '</h4><p>' + text(dietary or '以清淡、鲜香为主，少油少辣，更适合本次行程的游玩节奏。') + '</p></div><p class="food-disclaimer">ⓘ　本页为菜品与片区建议，非实时门店推荐。</p></aside></article>')
    out.append('<p class="food-image-note">图片为菜品示意 · 具体食材请向店家确认</p>')
    if notes:
        out.append('<details class="food-extra"><summary>用餐说明</summary><ul>' + ''.join('<li>' + text(note) + '</li>' for note in notes) + '</ul></details>')
    return ''.join(out) + '</div></div>'
