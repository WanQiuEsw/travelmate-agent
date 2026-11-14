"""Coverflow overview using saved itinerary rows and bundled fallback scenery."""
from base64 import b64encode
from pathlib import Path
import re
from urllib.parse import urlencode


def highlight_stops(days):
    """Exclude trip logistics and meals; show each named attraction once."""
    seen, slides = set(), []
    for i, day in enumerate(days, 1):
        for j, row in enumerate(day.get('rows', []), 1):
            if len(row) < 2:
                continue
            for name in re.split(r'→|->|\+|、|；|;', row[1]):
                name = re.sub(r'^(?:抵达|到达|前往|游览|参观|打卡)\s*', '', name.strip())
                name = re.sub(r'(?:漫步|游览|打卡|游玩|参观)$', '', name).strip()
                key = re.sub(r'\s+', '', name)
                logistics = r'早餐|午餐|晚餐|午饭|晚饭|返程|返家|回家|出发|接站|接机|候机|乘车|乘机|高铁|动车|二等座|火车|机场|车站|酒店|入住|退房|行李|休息|自由活动|打车|地铁|公交|站(?:[（(].*[)）])?$'
                if not key or key in seen or re.search(logistics, name):
                    continue
                seen.add(key)
                slides.append((i, j, [row[0], name, *row[2:]]))
    # shortcut: 概览最多展示12处核心地点，完整安排仍在每日行程中。
    return slides[:12]


CAROUSEL_CSS = """
.carousel-photo .carousel-placeholder{position:absolute;inset:0;display:none;place-items:center;color:#fff9;font-size:18px}.carousel-photo:has(img[hidden]) .carousel-placeholder{display:grid}.carousel-photo img[hidden]{display:none}
.carousel{position:relative;padding:16px 0 0;margin-bottom:30px;text-align:center;overflow:hidden}
.carousel-heading{border:0;padding:0;font-size:30px;margin:0 0 8px}.carousel-intro{color:#63736c;margin:0 0 24px}
.carousel>input{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.carousel:has(>input:focus-visible){outline:3px solid #b94d2a;outline-offset:-3px;border-radius:20px}
.carousel-stage{height:530px;position:relative;perspective:1400px;margin:0}
.carousel-slide{position:absolute;top:0;left:19%;width:62%;text-align:left;opacity:0;visibility:hidden;pointer-events:none;transform:translateX(0) scale(.7);transition:transform .6s cubic-bezier(.22,.7,.25,1),opacity .5s,filter .5s,visibility .6s;transform-origin:center center}
.carousel .highlight{display:block;position:relative;border:1px solid #e3dfd4;border-radius:24px;overflow:hidden;background:#fffefa;box-shadow:0 18px 32px #453a2626;color:#193c38;text-decoration:none}
.carousel-photo{position:relative;height:440px;overflow:hidden;background:linear-gradient(135deg,#8ebbaa,#275f59)}.carousel-photo>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;display:block;transition:transform .7s ease}.carousel .highlight:hover img{transform:scale(1.035)}
.carousel-caption{position:absolute;inset:auto 0 0;padding:70px 24px 72px;background:linear-gradient(transparent,#092a25dc);color:white}.carousel-caption strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:24px;line-height:1.4}.carousel-image-note{position:absolute;top:14px;left:16px;font-size:11px;background:#163d35b8;color:white;border-radius:999px;padding:3px 10px}
.carousel-meta{position:absolute;inset:auto 0 0;display:flex;align-items:center;gap:10px;padding:12px 20px;min-height:54px;flex-wrap:wrap;color:white}.carousel-meta small{font-size:12px;border:1px solid #ffffff70;padding:3px 10px;border-radius:999px}.carousel-meta small:first-child{color:white;background:#326b5ccc;border-color:#ffffff50}.carousel-meta .carousel-cta{margin-left:auto;background:#ffffff20;color:white;border:1px solid #ffffff60;padding:7px 12px;border-radius:999px;font-size:12px;white-space:nowrap}
.carousel-side-select{position:absolute;inset:0;border-radius:24px;cursor:pointer;display:none}.carousel-controls{display:none;justify-content:center;align-items:center;gap:18px;position:absolute;top:472px;left:0;right:0;color:#326355;font-size:14px}.carousel-controls button{width:44px;height:44px;border:1px solid #5c9182;border-radius:50%;background:#fffefa;color:#087f7a;font-size:24px;cursor:pointer}.carousel-controls button:hover{background:#e5f1e8}.carousel-controls button:focus-visible{outline:3px solid #b94d2a;outline-offset:3px}.carousel-controls button:disabled{opacity:.4;cursor:default}
.carousel-dots{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:-10px 12px 10px}.carousel-dot{width:24px;height:24px;display:grid;place-items:center;cursor:pointer}.carousel-dot:after{content:'';width:24px;height:5px;border-radius:5px;background:#b1bdae}.carousel-help{font-size:12px;color:#63736c;margin:8px 0 24px}.carousel-days{border-top:1px solid #d6ddd2;padding-top:20px;text-align:left}.carousel-days h3{font-size:22px;margin:0 0 14px}.carousel-day-links{display:flex;gap:12px;overflow-x:auto;padding:2px 2px 10px}.carousel-day-links a{flex:1 0 170px;border:1px solid #d7ded1;border-radius:14px;padding:14px;background:#fffefa;color:#193c38;text-decoration:none;display:flex;gap:14px;align-items:center}.carousel-day-links small{color:#b94d2a;white-space:nowrap}.carousel-day-links span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.carousel-controls button{position:absolute;top:-245px;left:-27%}.carousel-controls button:last-child{left:auto;right:-27%}
@media(max-width:700px){.carousel-heading{font-size:25px}.carousel-intro{font-size:13px}.carousel-stage{height:425px}.carousel-slide{left:8%;width:84%}.carousel-photo{height:340px}.carousel-caption{padding:60px 16px 68px}.carousel-caption strong{font-size:20px}.carousel-meta{padding:10px 14px;gap:6px;min-height:52px}.carousel-meta .carousel-cta{font-size:11px;padding:7px 9px}.carousel-controls{top:370px}.carousel-meta small{font-size:11px}.carousel-help{margin-bottom:18px}}
@media(prefers-reduced-motion:reduce){.carousel-slide,.carousel-photo img{transition:none}}
@media print{.carousel .carousel-meta{display:flex!important}}
@media(max-width:700px){.carousel-controls button{top:-230px;left:-8%;width:36px;height:36px;font-size:20px}.carousel-controls button:last-child{right:-8%}}
@media print{.carousel-stage{height:auto;perspective:none}.carousel .carousel-slide{position:static;display:block!important;visibility:visible!important;opacity:1!important;transform:none!important;filter:none!important;width:100%;margin:0 0 20px;break-inside:avoid}.carousel-controls,.carousel>input,.carousel-dots,.carousel-side-select,.carousel-help{display:none!important}.carousel{overflow:visible}.carousel-photo{height:220px}}
"""


def coverflow(days, text, inline_images=False, city=''):
    slides = highlight_stops(days)
    out = ['<div class="carousel" role="region" aria-label="景点轮播"><h2 class="carousel-heading">这次，我们去这些地方</h2><p class="carousel-intro">核心景点一眼看清，点击图片查看当天安排。</p>']
    if not slides:
        return ''.join(out) + '<p>本版暂无景点安排，请返回对话补充旅行需求。</p></div>'
    sources = {}
    def scenery(place):
        name = 'mountains.webp' if any(w in place for w in ('山', '茶', '峰', '林')) else 'town.webp' if any(w in place for w in ('寺', '庙', '街', '镇', '馆')) else 'coast.webp'
        if any(w in place for w in ('西湖', '杭州')):
            name = 'cities/hangzhou.webp'
        if name not in sources:
            sources[name] = ('data:image/webp;base64,' + b64encode((Path(__file__).with_name('images') / name).read_bytes()).decode('ascii')
                             if inline_images else '/assets/visual/' + name)
        return sources[name]
    for n, (_, _, row) in enumerate(slides, 1):
        out.append(f'<input type="radio" name="highlight" id="highlight-{n}" aria-label="景点 {n}：{text(row[1])}" {"checked" if n == 1 else ""}>')
    rules = []
    for n in range(1, len(slides)+1):
        positions = [(n, 'translateX(0) scale(1)', '1', 'none', 3)]
        if len(slides) > 1:
            positions.append(((n-2) % len(slides)+1, 'translateX(-64%) scale(.82) rotateY(12deg) rotate(-4deg)', '.85', 'saturate(.8)', 1))
        if len(slides) > 2:
            positions.append((n % len(slides)+1, 'translateX(64%) scale(.82) rotateY(-12deg) rotate(4deg)', '.85', 'saturate(.8)', 1))
        for target, transform, opacity, filtering, z in positions:
            selector = f'.carousel:has(#highlight-{n}:checked) .slide-{target}'
            rules.append(selector + '{visibility:visible;opacity:' + opacity + ';transform:' + transform + ';filter:' + filtering + f';z-index:{z}' + '}')
            if target != n:
                rules.append(selector + ' .carousel-side-select{display:block;pointer-events:auto}')
                rules.append(selector + ' .carousel-meta{display:none}')
        active = f'.carousel:has(#highlight-{n}:checked)'
        rules.extend([active + f' .slide-{n}' + '{pointer-events:auto}', active + f' .slide-{n} .carousel-controls' + '{display:flex}',
                      active + f' label[for="highlight-{n}"].carousel-dot:after' + '{background:#b94d2a}'])
    out.append('<style>' + ''.join(rules) + '</style><div class="carousel-stage">')
    for n, (i, j, row) in enumerate(slides, 1):
        previous, following = (n-2) % len(slides)+1, n % len(slides)+1
        photo_url = '/api/places/photo?' + urlencode({'city': city, 'place': row[1], 'v': 2})
        remote = f' data-photo-url="{text(photo_url)}"' if not inline_images and city else ''
        out.append(f'<article class="carousel-slide slide-{n}"><a class="highlight" href="#day-{i}"><div class="carousel-photo"><span class="carousel-placeholder">暂无景点图片</span><img src="{text(scenery(row[1]))}" alt="默认风景示意图，非景点实拍"{remote}><span class="carousel-image-note">默认风景 · 示意图</span><div class="carousel-caption"><strong>{text(row[1])}</strong></div></div><div class="carousel-meta"><small>第 {i} 天</small><span class="carousel-cta">查看当日日程 ↗</span></div></a><label class="carousel-side-select" for="highlight-{n}" aria-label="切换至{text(row[1])}"></label><div class="carousel-controls"><button type="button" data-carousel-target="highlight-{previous}" aria-label="上一个景点" {"disabled" if len(slides) == 1 else ""}>←</button><span>{n:02d} / {len(slides):02d}</span><button type="button" data-carousel-target="highlight-{following}" aria-label="下一个景点" {"disabled" if len(slides) == 1 else ""}>→</button></div></article>')
    out.append('</div><div class="carousel-dots" aria-label="选择景点">')
    out.extend(f'<label class="carousel-dot" for="highlight-{n}" aria-label="选择景点 {n}"></label>' for n in range(1, len(slides)+1))
    out.append('</div><p class="carousel-help">点击两侧卡片或使用方向键切换 · 点击主卡片查看当日日程</p><div class="carousel-days"><h3>每天都有一点期待</h3><div class="carousel-day-links">')
    for i, day in enumerate(days, 1):
        title = next((row[1] for day_no, _, row in slides if day_no == i), f'查看第 {i} 天安排')
        out.append(f'<a href="#day-{i}"><small>DAY {i:02d}</small><span>{text(title)}</span></a>')
    return ''.join(out) + '</div></div></div>'


CAROUSEL_JS = r"""
for (const image of document.querySelectorAll('.carousel-photo img')) {
  const showEmpty = () => {
    image.hidden = true;
    image.closest('.carousel-photo').querySelector('.carousel-image-note').textContent = '暂无景点图片';
  };
  image.addEventListener('error', showEmpty);
  if (image.complete && !image.naturalWidth) showEmpty();
}
// Load only the selected attraction, so opening a guide cannot fan out searches.
for (const carousel of document.querySelectorAll('.carousel:has([data-photo-url])')) {
  const loadPhoto = () => {
    if (!carousel.getClientRects().length || document.hidden) return;
    const selected = carousel.querySelector('input[name="highlight"]:checked');
    const slide = selected && carousel.querySelector('.slide-' + selected.id.split('-').pop());
    const image = slide && slide.querySelector('img[data-photo-url]');
    if (!image || image.dataset.photoRequested) return;
    image.dataset.photoRequested = 'true';
    const photo = new Image();
    photo.onload = () => {
      image.src = photo.src;
      image.hidden = false;
      image.alt = slide.querySelector('.carousel-caption strong').textContent + ' · 小红书搜索配图';
      slide.querySelector('.carousel-image-note').textContent = '小红书 · 搜索配图';
    };
    photo.src = image.dataset.photoUrl;
  };
  carousel.addEventListener('change', loadPhoto);
  window.addEventListener('hashchange', loadPhoto);
  document.addEventListener('visibilitychange', loadPhoto);
  new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) loadPhoto(); }).observe(carousel);
}
for (const carousel of document.querySelectorAll('.carousel')) {
  const radios = [...carousel.querySelectorAll('input[name="highlight"]')];
  if (radios.length < 2) continue;
  let timer, inView = false;
  const stop = () => { clearTimeout(timer); timer = undefined; };
  function schedule() {
    stop();
    if (!inView || document.hidden || !carousel.getClientRects().length) return;
    timer = setTimeout(() => {
      const index = radios.findIndex(radio => radio.checked);
      radios[(index + 1) % radios.length].checked = true;
      carousel.dispatchEvent(new Event('change', {bubbles:true}));
      schedule();
    }, 4000);
  }
  const observer = new IntersectionObserver(entries => {
    inView = entries.some(entry => entry.isIntersecting);
    schedule();
  });
  observer.observe(carousel.querySelector('.carousel-stage'));
  carousel.addEventListener('change', schedule);
  document.addEventListener('visibilitychange', schedule);
  window.addEventListener('hashchange', schedule);
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', schedule);
}
"""
