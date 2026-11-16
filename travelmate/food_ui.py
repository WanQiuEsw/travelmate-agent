"""Portrait food recommendations, including historical daily meal rows."""
import re
from urllib.parse import urlencode
from travelmate.recommendations import is_specific_food


CSS = """
.food-shell.overview-feed{padding:8px 0 24px;color:#103e35}
.food-kicker{margin:0 12px 30px;padding:12px 20px;border:1px solid #cbd8c9;border-radius:24px;background:#e8eee4;text-align:center;font:500 19px/1.5 Georgia,'Songti SC',SimSun,serif;letter-spacing:.1em}
.food-shell.overview-feed .discovery-heading{margin-bottom:28px}
.food-shell.overview-feed .discovery-heading h2{font-size:clamp(26px,3.8vw,48px);color:#103e35}
.food-shell .overview-carousel{--card-width:clamp(280px,34vw,430px);--step:calc(var(--card-width)*.86)}
.food-shell .food-card-body{border:1px solid #e1e1d6;border-radius:22px;background:#fffdf7;overflow:hidden;box-shadow:0 12px 26px #193c3812}
.food-shell .food-photo,.food-shell .food-photo:has(img:not([hidden])){aspect-ratio:2/3;display:grid;position:relative;overflow:hidden;border-radius:20px;background:#e8eee4}
.food-shell .food-photo img{grid-area:1/1;width:100%;height:100%;min-height:0;object-fit:cover;display:block}
.food-shell .food-photo img[hidden]{display:none}
.food-shell .food-photo:has(img:not([hidden])) .food-placeholder{visibility:hidden}
.food-shell .food-copy{padding:20px 24px 22px}
.food-title{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:12px}
.food-shell .food-copy h3{margin:0;font:700 34px/1.35 Georgia,'Songti SC',SimSun,serif;color:#103e35}
.food-tag{padding:3px 10px;border:1px solid #bfcdba;border-radius:999px;background:#edf1e8;color:#476455;font-size:12px}
.food-shell .is-active .food-tag{border-color:#df833f;background:#fff4e6;color:#c8661f}
.food-shell .food-tips{padding-top:10px;border-top:1px solid #dedfd2}
.food-shell .overview-card:focus-visible{outline:3px solid #b94d2a;outline-offset:4px;border-radius:22px}
.food-shell .overview-card[inert]{visibility:hidden}
.food-shell .overview-stage:before,.food-shell .overview-stage:after{display:none}
.food-shell .overview-pagination{padding:10px 0 30px}
.food-shell .overview-indicators{gap:3px;max-width:85%}
.food-shell .overview-indicators button{width:32px;height:36px}
.food-shell .overview-indicators button:after{left:10px;right:auto;top:12px;width:12px;height:12px;border-radius:50%;background:#c1cfbb}
.food-shell .overview-indicators button[aria-current=true]:after{background:#103e35}
.food-shell .overview-count{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
.food-reason{display:flex;align-items:center;gap:26px;margin:16px 12px 0;padding:24px 28px;border:1px solid #cbd8c9;border-radius:24px;background:#e8eee4}
.food-reason h3{display:flex;align-items:center;gap:14px;flex-shrink:0;margin:0;font:700 28px/1.4 Georgia,'Songti SC',SimSun,serif}
.food-reason h3:before{content:'';width:3px;height:30px;border-radius:4px;background:#de7a27}
.food-reason p{margin:0;color:#546b60;font-size:16px;line-height:1.8}
.food-reason svg{width:26px;height:32px;flex-shrink:0;margin-left:auto;fill:none;stroke:currentColor;stroke-width:1.5}
.result:has(#panel-food:target){background:transparent;border-color:transparent}
.food-copy{padding:16px 18px 18px}.food-copy h3{margin:0 0 8px;font-size:26px;line-height:1.4;overflow-wrap:anywhere}.food-copy>p{margin:0;color:#63736c;font-size:15px;line-height:1.75;overflow-wrap:anywhere}
.food-placeholder svg{width:44px;height:44px}.food-placeholder small{font-size:12px}.food-tips{margin-top:12px;font-size:13px;line-height:1.75;color:#63736c}.food-tips summary{font-size:13px;min-height:32px;cursor:pointer}.food-tips p{margin:4px 0 0;overflow-wrap:anywhere}.food-preference{margin:20px 0 0;padding:14px 18px;border-radius:12px;background:#eaf3ee;color:#476455;font-size:14px;line-height:1.8;overflow-wrap:anywhere}.food-image-note{margin:18px 0 0;font-size:11px;line-height:1.8;color:#8a988f}
@media(max-width:600px){.food-copy{padding:12px}.food-copy h3{font-size:19px}.food-copy>p{font-size:13px}.food-tips,.food-tips summary{font-size:12px}}
@media(max-width:760px){.food-shell .overview-carousel{--card-width:clamp(225px,62vw,330px);--step:calc(var(--card-width)*.88)}.food-kicker{margin:0 4px 22px;padding:10px;font-size:15px}.food-shell .food-copy{padding:14px 16px}.food-shell .food-copy h3{font-size:26px}.food-reason{margin:12px 4px 0;padding:18px;gap:14px;flex-wrap:wrap}.food-reason h3{font-size:23px}.food-reason p{font-size:13px;flex:1 1 160px}.food-reason svg{display:none}.food-shell.overview-feed .discovery-heading h2{gap:10px}.food-shell.overview-feed .discovery-heading p{font-size:12px}}
@media print{.food-shell .overview-card[inert]{visibility:visible}.food-tips::details-content{display:block;content-visibility:visible}}
"""


def panel(sections, days, text, inline_images=False, city=''):
    # Old snapshots repeat dishes across days and contain generated meal fillers.
    attractions = set()
    for day in days:
        for row, detail in zip(day.get('rows', []), day.get('stop_details', [])):
            if detail.get('kind') in ('visit', 'experience') and len(row) > 1:
                attractions.add(re.sub(r'\s+', '', row[1]).casefold())
    foods, seen = [], {}
    for section in sections:
        for row in section.get('rows', []):
            name, description, _, _, tips = (list(row) + [''] * 5)[:5]
            name = name.strip()
            key = re.sub(r'\s+', '', name).casefold()
            if key in attractions or not is_specific_food(name):
                continue
            if key in seen:
                previous, detail, reminders = foods[seen[key]]
                if tips and tips not in reminders:
                    foods[seen[key]] = (previous, detail, '；'.join(filter(None, (reminders, tips))))
                continue
            seen[key] = len(foods)
            foods.append((name, description, tips))

    def photo(name):
        image = ''
        if city and not inline_images:
            url = '/api/places/photo?' + urlencode({'city': city, 'place': name, 'category': 'food', 'v': 4})
            image = '<img data-food-photo="' + text(url) + '" alt="' + text(name + ' · 小红书搜索配图') + '" hidden>'
        return ('<div class="food-photo discovery-photo"><span class="food-placeholder discovery-placeholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2 12h20c-1 7-5 9-10 9S3 19 2 12ZM7 2c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7"/></svg><small>暂无菜品图片</small></span>' + image + '</div>')

    out = ['<div class="food-shell overview-feed discovery-feed" role="region" aria-label="当地特色美食推荐"><p class="food-kicker">' + (text(city) + ' · ' if city else '') + '美食推荐</p><header class="discovery-heading"><h2>这次，我们吃这些</h2><p>把旅途中的好味道，提前收藏。</p></header>']
    if not foods:
        return ''.join(out) + '<p class="discovery-empty">暂无当地美食推荐，可在对话中补充想尝的当地风味。</p></div>'
    out.append('<div class="overview-carousel" aria-roledescription="轮播图" aria-label="当地特色菜品"><div class="overview-stage">')
    for index, (name, description, tips) in enumerate(foods):
        out.append(f'<article id="food-card-{index}" class="food-card overview-card" tabindex="0" aria-label="' + text(name) + '"><div class="discovery-card-body food-card-body">' + photo(name) + '<div class="food-copy"><div class="food-title"><h3>' + text(name) + '</h3><span class="food-tag">当地风味</span></div><p>' + text(description) + '</p>')
        if tips:
            out.append('<details class="food-tips"><summary>点单提醒</summary><p>' + text(tips) + '</p></details>')
        out.append('</div></div></article>')
    out.append('</div><button type="button" class="overview-arrow overview-prev" aria-label="上一个美食"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button><button type="button" class="overview-arrow overview-next" aria-label="下一个美食"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button></div><div class="overview-pagination"><div class="overview-indicators" aria-label="选择美食">')
    for index, (name, _, _) in enumerate(foods):
        out.append(f'<button type="button" data-overview-index="{index}" aria-label="第{index + 1}个美食：{text(name)}" aria-current="' + ('true' if index == 0 else 'false') + '"></button>')
    out.append(f'</div><span class="overview-count" aria-live="polite" aria-atomic="true">01 / {len(foods):02d}</span></div><aside class="food-reason"><h3>推荐理由</h3><p>从地道风味到街巷小吃，<br>找到属于你的' + text(city or '旅途') + '味道。</p><svg viewBox="0 0 24 28" aria-hidden="true"><path d="M4 26V3a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v23l-8-6Z"/></svg></aside>')
    dietary = list(dict.fromkeys(item['text'] for section in sections for item in section.get('items', []) if item['text'].startswith('饮食要求')))
    if dietary:
        out.append('<aside class="food-preference" aria-label="饮食要求">' + '<br>'.join(text(note) for note in dietary) + '</aside>')
    out.append('<p class="food-image-note">' + ('离线版不加载在线配图。' if inline_images else '图片来自小红书搜索，未核实为所荐菜品或门店实拍；无匹配或加载失败时显示占位。') + '具体食材与忌口请向店家确认。</p></div>')
    return ''.join(out)


FOOD_JS = r"""
// Start all food photos immediately, including cards outside the viewport.
if (document.querySelectorAll('[data-food-photo]').length) {
  const preloadFoodPhotos = () => {
    if (document.hidden) return;
    for (const image of document.querySelectorAll('[data-food-photo]')) {
      image.onerror = () => { image.hidden = true; };
      loadPlacePhoto(image);
    }
  };
  preloadFoodPhotos();
  window.addEventListener('hashchange', preloadFoodPhotos);
  document.addEventListener('visibilitychange', preloadFoodPhotos);
}
"""
