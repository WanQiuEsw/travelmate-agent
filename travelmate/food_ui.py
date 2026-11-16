"""Local food discovery carousel, including historical daily meal rows."""
import re
from urllib.parse import urlencode


CSS = """
.food-shell{container-type:inline-size;position:relative;max-width:640px;margin:0 auto;padding:20px 0 22px;color:#201c18}
.food-heading,.food-help{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%)}
.food-track{--food-width:85cqw;position:relative;display:flex;align-items:flex-start;gap:20px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x mandatory;scroll-padding-inline:calc((100% - var(--food-width))/2);padding:0 calc((100% - var(--food-width))/2);scrollbar-width:none;outline-offset:-2px}.food-track::-webkit-scrollbar{display:none}
.food-card:not(.is-active) .food-copy{visibility:hidden}.food-card{flex:0 0 var(--food-width);min-width:0;scroll-snap-align:center;border:0;border-radius:0;background:#fff;box-shadow:none}
.food-photo{position:relative;aspect-ratio:3/4;max-height:70svh;background:#f7f4f0;overflow:hidden;border-radius:16px;display:grid;place-items:center}.food-photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}.food-photo img[hidden]{display:none}.food-placeholder{display:grid;justify-items:center;gap:10px;padding:12px;text-align:center;color:#928477}.food-placeholder svg{width:44px;height:44px}.food-placeholder small{font-size:12px}.food-photo:has(img:not([hidden])) .food-placeholder{visibility:hidden}
.food-copy{padding:16px 0 0}.food-copy h3{font:700 clamp(27px,5.8cqw,36px)/1.35 Georgia,'Songti SC',SimSun,serif;margin:0 0 6px;overflow-wrap:anywhere}.food-copy>p{font-size:15px;line-height:1.65;margin:0;color:#615952;overflow-wrap:anywhere}.food-badge{display:none}.food-tips{margin-top:8px;color:#887566;font-size:12px;line-height:1.6}.food-tips summary{cursor:pointer;min-height:28px;font-size:12px;font-weight:400}.food-tips p{margin:4px 0 0;overflow-wrap:anywhere}
.food-controls{display:grid;grid-template-columns:44px minmax(0,1fr) 44px;align-items:center;gap:12px;width:85%;margin:16px auto 0;padding:0;background:none;border-radius:0;color:#c56539;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums;text-align:center}.food-controls button{display:grid;place-items:center;width:44px;height:44px;border:0;background:none;color:#201c18;font-size:34px;line-height:1;cursor:pointer}.food-controls button:disabled{opacity:.35;cursor:default}
.food-thumbs{position:relative;display:flex;gap:12px;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin;padding:4px 4% 12px;margin:14px 0 0}.food-thumb{position:relative;flex:0 0 calc((100% - 36px)/4);min-width:0;padding:0 0 10px;border:0;background:none;color:#302821;border-radius:0;cursor:pointer;font:inherit}.food-thumb[aria-pressed=true] .food-photo{outline:2px solid #c56539;outline-offset:2px}.food-thumb[aria-pressed=true]:after{content:'';position:absolute;bottom:0;left:24%;right:24%;height:3px;border-radius:3px;background:#c56539}.food-thumb .food-photo{aspect-ratio:4/5;max-height:none;border-radius:10px}.food-thumb .food-placeholder{padding:6px}.food-thumb .food-placeholder svg{width:24px;height:24px}.food-thumb .food-placeholder small{display:none}.food-thumb>span{display:block;font-size:12px;margin:7px 0 0;line-height:1.5;overflow-wrap:anywhere}.food-shell button:focus-visible,.food-track:focus-visible{outline:2px solid #c56539;outline-offset:2px}
.food-preference{margin:20px 7.5% 0;background:#fff5ec;padding:12px 14px;border-radius:10px;font-size:13px;line-height:1.8;overflow-wrap:anywhere;color:#86694f}.food-image-note{margin:18px 7.5% 0;font-size:10px;color:#9a8d83;line-height:1.7}.food-empty{margin:0 7.5%;text-align:center;background:#faf4ee;padding:36px 20px;border-radius:14px;color:#887566}
@container(max-width:400px){.food-copy>p{font-size:14px}.food-thumbs{gap:10px}.food-thumb{flex-basis:calc((100% - 30px)/4)}.food-thumb>span{font-size:11px}}
@media print{.food-track{display:block;overflow:visible;padding:0}.food-card{margin-bottom:20px;break-inside:avoid}.food-card .food-copy{visibility:visible!important}.food-card .food-photo{height:220px;aspect-ratio:auto}.food-controls,.food-thumbs,.food-help{display:none}.food-tips::details-content{display:block;content-visibility:visible}}
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
        return ('<div class="food-photo"><span class="food-placeholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2 12h20c-1 7-5 9-10 9S3 19 2 12ZM7 2c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7m5-7c-4 3 3 4 0 7"/></svg><small>暂无菜品图片</small></span>' + image + '</div>')

    out = ['<div class="food-shell" role="region" aria-label="当地特色美食推荐"><header class="food-heading"><h2>当地美食推荐</h2><p>当地特色，跟着胃口慢慢选</p></header>']
    if not foods:
        return ''.join(out) + '<p class="food-empty">暂无当地美食推荐，可在对话中补充想尝的当地风味。</p></div>'
    out.append('<div class="food-track" tabindex="0" aria-label="美食轮播，使用左右方向键切换">')
    for index, (name, description, tips) in enumerate(foods):
        out.append(f'<article id="food-card-{index}" class="food-card' + (' is-active' if index == 0 else '') + '" aria-label="' + text(name) + '">' + photo(name) + '<div class="food-copy"><h3>' + text(name) + '</h3><p>' + text(description) + '</p><span class="food-badge">当地风味</span>')
        if tips:
            out.append('<details class="food-tips"><summary>点单提醒</summary><p>' + text(tips) + '</p></details>')
        out.append('</div></article>')
    disabled = ' disabled' if len(foods) == 1 else ''
    out.append('</div><div class="food-controls"><button type="button" data-food-step="-1" aria-label="上一道美食"' + disabled + '>‹</button><span class="food-count" aria-live="polite" aria-atomic="true">01 / ' + f'{len(foods):02d}' + '</span><button type="button" data-food-step="1" aria-label="下一道美食"' + disabled + '>›</button></div><p class="food-help">左右滑动，发现更多当地美食</p><div class="food-thumbs" role="group" aria-label="选择想尝的美食">')
    for index, (name, _, _) in enumerate(foods):
        out.append(f'<button type="button" class="food-thumb" data-food-index="{index}" aria-controls="food-card-{index}" aria-pressed="' + ('true' if index == 0 else 'false') + '" aria-label="' + text('查看' + name) + '">' + photo(name) + '<span>' + text(name) + '</span></button>')
    out.append('</div><p class="food-help">点选图片，看看你想尝的那一道</p>')
    dietary = list(dict.fromkeys(item['text'] for section in sections for item in section.get('items', []) if item['text'].startswith('饮食要求')))
    if dietary:
        out.append('<aside class="food-preference" aria-label="饮食要求">' + '<br>'.join(text(note) for note in dietary) + '</aside>')
    out.append('<p class="food-image-note">' + ('离线版不加载在线配图。' if inline_images else '图片来自小红书搜索，未核实为所荐菜品或门店实拍；无匹配或加载失败时显示占位。') + '具体食材与忌口请向店家确认。</p></div>')
    return ''.join(out)


FOOD_JS = r"""
for (const food of document.querySelectorAll('.food-shell')) {
  const track = food.querySelector('.food-track');
  if (!track) continue;
  const cards = [...track.querySelectorAll('.food-card')];
  const thumbs = [...food.querySelectorAll('[data-food-index]')];
  const count = food.querySelector('.food-count');
  let current = 0;
  let width = track.clientWidth;
  const motion = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
  function mark(index) {
    current = index;
    cards.forEach((card, i) => card.classList.toggle('is-active', i === index));
    thumbs.forEach((thumb, i) => thumb.setAttribute('aria-pressed', String(i === index)));
    count.textContent = String(index + 1).padStart(2, '0') + ' / ' + String(cards.length).padStart(2, '0');
    loadPlacePhoto(cards[index].querySelector('[data-food-photo]'), true);
    const thumb = thumbs[index], strip = thumb.parentElement;
    if (thumb.offsetLeft < strip.scrollLeft || thumb.offsetLeft + thumb.offsetWidth > strip.scrollLeft + strip.clientWidth) {
      strip.scrollTo({left: thumb.offsetLeft - (strip.clientWidth - thumb.offsetWidth) / 2, behavior: motion});
    }
  }
  function select(index, behavior = motion) {
    index = (index + cards.length) % cards.length;
    const card = cards[index];
    track.scrollTo({left: card.offsetLeft - (track.clientWidth - card.offsetWidth) / 2, behavior});
    mark(index);
  }
  for (const button of food.querySelectorAll('[data-food-step]')) {
    button.addEventListener('click', () => select(current + Number(button.dataset.foodStep)));
  }
  thumbs.forEach((thumb, index) => thumb.addEventListener('click', () => select(index)));
  track.addEventListener('keydown', event => {
    if (event.target !== track || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    select(event.key === 'Home' ? 0 : event.key === 'End' ? cards.length - 1 : current + (event.key === 'ArrowRight' ? 1 : -1));
  });
  // Native touch scrolling and button navigation share the same selected state.
  track.addEventListener('scroll', () => {
    if (track.clientWidth !== width) return;
    const center = track.scrollLeft + track.clientWidth / 2;
    const index = cards.reduce((best, card, i) => Math.abs(card.offsetLeft + card.offsetWidth / 2 - center) < Math.abs(cards[best].offsetLeft + cards[best].offsetWidth / 2 - center) ? i : best, 0);
    if (index !== current) mark(index);
  }, {passive: true});
  new ResizeObserver(() => {
    if (!track.clientWidth || track.clientWidth === width) return;
    width = track.clientWidth;
    select(current, 'instant');
  }).observe(track);
}

// Start all food photos immediately, including cards outside the viewport.
if (document.querySelectorAll('[data-food-photo]').length) {
  const preloadFoodPhotos = () => {
    if (document.hidden) return;
    for (const image of document.querySelectorAll('[data-food-photo]')) {
      image.onerror = () => { image.hidden = true; };
      loadPlacePhoto(image, !!image.closest('.food-card.is-active')?.getClientRects().length);
    }
  };
  preloadFoodPhotos();
  window.addEventListener('hashchange', preloadFoodPhotos);
  document.addEventListener('visibilitychange', preloadFoodPhotos);
}
"""
