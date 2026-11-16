"""Local food photo feed, including historical daily meal rows."""
import re
from urllib.parse import urlencode


CSS = """
.food-copy{padding:16px 18px 18px}.food-copy h3{margin:0 0 8px;font-size:26px;line-height:1.4;overflow-wrap:anywhere}.food-copy>p{margin:0;color:#63736c;font-size:15px;line-height:1.75;overflow-wrap:anywhere}
.food-placeholder svg{width:44px;height:44px}.food-placeholder small{font-size:12px}.food-tips{margin-top:12px;font-size:13px;line-height:1.75;color:#63736c}.food-tips summary{font-size:13px;min-height:32px;cursor:pointer}.food-tips p{margin:4px 0 0;overflow-wrap:anywhere}.food-preference{margin:20px 0 0;padding:14px 18px;border-radius:12px;background:#eaf3ee;color:#476455;font-size:14px;line-height:1.8;overflow-wrap:anywhere}.food-image-note{margin:18px 0 0;font-size:11px;line-height:1.8;color:#8a988f}
@media(max-width:600px){.food-copy{padding:12px}.food-copy h3{font-size:19px}.food-copy>p{font-size:13px}.food-tips,.food-tips summary{font-size:12px}}
@media print{.food-tips::details-content{display:block;content-visibility:visible}}
"""


def panel(sections, days, text, inline_images=False, city=''):
    # Old snapshots repeat dishes across days and contain generated meal fillers.
    foods, seen = [], {}
    for section in sections:
        for row in section.get('rows', []):
            name, description, _, _, tips = (list(row) + [''] * 5)[:5]
            name = name.strip()
            key = re.sub(r'\s+', '', name).casefold()
            if not key or name in ('住宿附近的当地早餐', '游览片区的顺路午餐', '返程或住宿片区的晚餐'):
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

    out = ['<div class="food-shell discovery-feed" role="region" aria-label="当地特色美食推荐"><header class="discovery-heading"><h2>当地特色美食</h2><p>从代表菜到地道小吃，看看这座城的味道</p></header>']
    if not foods:
        return ''.join(out) + '<p class="discovery-empty">暂无当地美食推荐，可在对话中补充想尝的当地风味。</p></div>'
    out.append('<div class="discovery-grid" aria-label="当地特色菜品">')
    for index, (name, description, tips) in enumerate(foods):
        out.append(f'<article id="food-card-{index}" class="food-card" aria-label="' + text(name) + '"><div class="discovery-card-body food-card-body">' + photo(name) + '<div class="food-copy"><h3>' + text(name) + '</h3><p>' + text(description) + '</p>')
        if tips:
            out.append('<details class="food-tips"><summary>点单提醒</summary><p>' + text(tips) + '</p></details>')
        out.append('</div></div></article>')
    out.append('</div>')
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
