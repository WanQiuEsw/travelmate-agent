"""Coverflow overview using saved itinerary rows and bundled fallback scenery."""
from base64 import b64encode
from pathlib import Path
import re
from urllib.parse import urlencode


def photo_url(city, place):
    return '/api/places/photo?' + urlencode({'city': city, 'place': place, 'v': 4})


def visit_duration(row):
    detail = row[2] if len(row) > 2 else ''
    explicit = re.search(r'(?:游玩|游览|参观|停留)(?:时长)?[：:\s约]*(\d+(?:\.\d+)?(?:[～~—–-]\d+(?:\.\d+)?)?\s*(?:小时|分钟))', detail)
    if explicit:
        return explicit[1]
    times = re.fullmatch(r'\s*(\d{1,2}):(\d{2})\s*[–—~～-]\s*(\d{1,2}):(\d{2})\s*', row[0])
    if times:
        start_h, start_m, end_h, end_m = map(int, times.groups())
        minutes = (end_h - start_h) * 60 + end_m - start_m
        if max(start_h, end_h) < 24 and max(start_m, end_m) < 60 and minutes > 0:
            return f'{minutes // 60}小时{minutes % 60}分钟' if minutes % 60 and minutes >= 60 else f'{minutes // 60}小时' if minutes >= 60 else f'{minutes}分钟'
    return '游玩时长待确认'


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

CAROUSEL_CSS += """
.carousel-photo{height:340px}.carousel-caption{padding:65px 24px 20px}.carousel-meta{position:static;color:#285b48;padding:14px 20px 4px;min-height:0}.carousel-meta small:first-child{background:#e7efe5;color:#285b48;border-color:#c9d7c6}.carousel-meta .carousel-time{font-size:12px;color:#63736c}.carousel-copy{padding:6px 20px 18px;min-height:104px}.carousel-copy p{font-size:14px;line-height:1.6;color:#63736c;text-align:left;margin:0 0 10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.carousel-copy .carousel-cta{display:inline-block;color:#087f7a;font-size:13px;font-weight:600}.carousel-controls{top:490px}.carousel-controls button{top:-300px}.carousel .highlight{min-height:475px}.carousel-photo:has(img[hidden]) .carousel-placeholder{display:grid}
@media(max-width:700px){.carousel-stage{height:480px}.carousel-photo{height:280px}.carousel .highlight{min-height:425px}.carousel-caption{padding:50px 16px 16px}.carousel-copy{padding:6px 14px 14px;min-height:100px}.carousel-meta{padding:12px 14px 4px}.carousel-controls{top:435px}.carousel-controls button{top:-275px}.carousel-caption strong{font-size:22px}}
@media print{.carousel-photo{height:220px}.carousel .highlight{min-height:0}.carousel .carousel-meta{display:flex!important}}
"""


CAROUSEL_CSS += """
.carousel-photo{display:grid;height:auto;min-height:140px;background:#edf0e5}.carousel-photo>img{position:static;grid-area:1/1;width:100%;height:auto;max-height:65vh;object-fit:contain}.carousel-photo:has(img[hidden]){min-height:220px}
.carousel-photo .carousel-placeholder{grid-area:1/1;position:static;color:#63736c;min-height:220px}.carousel-caption{position:static;padding:14px 20px 0;background:none;color:#193c38}.carousel-image-note{position:static;justify-self:start;margin:8px 10px 0}.carousel .highlight{min-height:0}.carousel .highlight:hover img{transform:none}
.carousel-controls{position:static;margin:12px auto 0;padding:0 0 18px;gap:18px}.carousel-controls button,.carousel-controls button:last-child{position:static}.carousel-dots{margin:12px}
@media print{.carousel-photo>img{max-height:220px}.carousel-photo{height:auto}.carousel-stage{height:auto!important}}
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
        remote = f' data-photo-url="{text(photo_url(city, row[1]))}"' if not inline_images and city else ''
        description = row[2] if len(row) > 2 and row[2].strip() else '查看当天安排，了解游览与交通提醒。'
        out.append(f'<article class="carousel-slide slide-{n}"><a class="highlight" href="#day-{i}"><div class="carousel-photo"><span class="carousel-placeholder">暂无景点图片</span><img src="{text(scenery(row[1]))}" alt="默认风景示意图，非景点实拍"{remote}><span class="carousel-image-note">默认风景 · 示意图</span></div><div class="carousel-caption"><strong>{text(row[1])}</strong></div><div class="carousel-meta"><small>第 {i} 天</small><span class="carousel-time">{text(row[0])} · {text(visit_duration(row))}</span></div><div class="carousel-copy"><p>{text(description)}</p><span class="carousel-cta">查看当日日程 ↗</span></div></a><label class="carousel-side-select" for="highlight-{n}" aria-label="切换至{text(row[1])}"></label><div class="carousel-controls"><button type="button" data-carousel-target="highlight-{previous}" aria-label="上一个景点" {"disabled" if len(slides) == 1 else ""}>←</button><span>{n:02d} / {len(slides):02d}</span><button type="button" data-carousel-target="highlight-{following}" aria-label="下一个景点" {"disabled" if len(slides) == 1 else ""}>→</button></div></article>')
    out.append('</div><div class="carousel-dots" aria-label="选择景点">')
    out.extend(f'<label class="carousel-dot" for="highlight-{n}" aria-label="选择景点 {n}"></label>' for n in range(1, len(slides)+1))
    out.append('</div><p class="carousel-help">点击两侧卡片或使用方向键切换 · 点击主卡片查看当日日程</p><div class="carousel-days"><h3>每天都有一点期待</h3><div class="carousel-day-links">')
    for i, day in enumerate(days, 1):
        title = next((row[1] for day_no, _, row in slides if day_no == i), f'查看第 {i} 天安排')
        out.append(f'<a href="#day-{i}"><small>DAY {i:02d}</small><span>{text(title)}</span></a>')
    return ''.join(out) + '</div></div></div>'


CAROUSEL_JS = r"""
// Share one request per place across overview and daily cards; fetch media serially.
const placePhotos = new Map();
const placePhotoQueue = [];
let placePhotoLoading = false;
let placePhotoBlocked = '';
function runPlacePhotoQueue() {
  if (placePhotoLoading || document.hidden || !placePhotoQueue.length) return;
  const next = placePhotoQueue.shift();
  placePhotoLoading = true;
  next.run().then(next.resolve).finally(() => {
    placePhotoLoading = false;
    runPlacePhotoQueue();
  });
}
function loadPlacePhoto(image, priority = false) {
  if (!image) return;
  const url = image.dataset.photoUrl || image.dataset.foodPhoto;
  const pending = placePhotoQueue.findIndex(task => task.url === url);
  if (priority && pending > 0) placePhotoQueue.unshift(placePhotoQueue.splice(pending, 1)[0]);
  if (image.dataset.photoState) return;
  image.dataset.photoState = 'loading';
  if (!placePhotos.has(url)) {
    let resolve;
    const task = new Promise(done => { resolve = done; });
    const run = async () => {
      if (placePhotoBlocked) return {error: placePhotoBlocked};
      for (let attempt = 0; attempt < 2; attempt++) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 45000);
        try {
          const response = await fetch(url, {signal: controller.signal, credentials: 'same-origin'});
          if (response.status === 429 && attempt === 0) {
            clearTimeout(timeout);
            const seconds = Math.min(60, Math.max(1, Number(response.headers.get('Retry-After')) || 60));
            await new Promise(done => setTimeout(done, seconds * 1000));
            continue;
          }
          if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            const error = data.error || (response.status === 401 ? 'login_required' : 'fetch_failed');
            if (['not_configured', 'invalid_cookie', 'login_or_risk_control', 'login_required'].includes(error)) placePhotoBlocked = error;
            return {error};
          }
          return {src: URL.createObjectURL(await response.blob())};
        } catch {
          return {error: 'fetch_failed'};
        } finally { clearTimeout(timeout); }
      }
    };
    placePhotos.set(url, task);
    const request = {url, run, resolve};
    if (priority) placePhotoQueue.unshift(request);
    else placePhotoQueue.push(request);
    runPlacePhotoQueue();
  }
  placePhotos.get(url).then(({src, error}) => {
    image.dataset.photoState = src ? 'ready' : 'failed';
    if (src) {
      image.src = src;
      image.hidden = false;
      if (!image.dataset.foodPhoto) image.alt = '小红书搜索配图，未核实图片内容';
    }
    const note = image.parentElement.querySelector('.carousel-image-note, .daily-image-note, .food-placeholder small');
    const messages = {not_configured:'小红书图片未启用', invalid_cookie:'小红书登录配置无效',
      login_or_risk_control:'小红书登录失效或受限', login_required:'请先登录 TravelMate',
      no_photo:'未找到小红书配图', image_download_failed:'小红书图片下载失败', fetch_failed:'小红书图片暂时不可用'};
    if (note) note.textContent = src ? '小红书 · 搜索配图' : (messages[error] || '小红书图片暂时不可用') + (image.dataset.foodPhoto ? '' : ' · 示意图');
    image.closest('.carousel')?.dispatchEvent(new Event('photo-ready'));
  });
}
document.addEventListener('visibilitychange', runPlacePhotoQueue);
window.addEventListener('pagehide', event => {
  if (!event.persisted) for (const task of placePhotos.values()) task.then(({src}) => { if (src) URL.revokeObjectURL(src); });
});

for (const image of document.querySelectorAll('.carousel-photo img')) {
  const showEmpty = () => {
    image.hidden = true;
    image.closest('.carousel-photo').querySelector('.carousel-image-note').textContent = '暂无景点图片';
  };
  image.addEventListener('error', showEmpty);
  if (image.complete && !image.naturalWidth) showEmpty();
}
// The selected card determines the stage height; portrait images stay uncropped.
for (const carousel of document.querySelectorAll('.carousel')) {
  const stage = carousel.querySelector('.carousel-stage');
  if (!stage?.style) continue;
  const fit = () => {
    const selected = carousel.querySelector('input[name="highlight"]:checked');
    const slide = selected && carousel.querySelector('.slide-' + selected.id.split('-').pop());
    if (slide && carousel.getClientRects().length) stage.style.height = slide.offsetHeight + 'px';
  };
  const observer = new ResizeObserver(fit);
  for (const slide of carousel.querySelectorAll('.carousel-slide')) observer.observe(slide);
  carousel.addEventListener('change', fit);
  window.addEventListener('hashchange', fit);
  fit();
}
// Queue every overview image up front; promote the selected slide over prefetches.
for (const carousel of document.querySelectorAll('.carousel:has([data-photo-url])')) {
  const loadPhoto = () => {
    if (document.hidden) return;
    const selected = carousel.querySelector('input[name="highlight"]:checked');
    const slide = selected && carousel.querySelector('.slide-' + selected.id.split('-').pop());
    const image = slide && slide.querySelector('img[data-photo-url]');
    loadPlacePhoto(image, !!carousel.getClientRects().length);
    for (const other of carousel.querySelectorAll('img[data-photo-url]')) loadPlacePhoto(other);
  };
  carousel.addEventListener('change', loadPhoto);
  window.addEventListener('hashchange', loadPhoto);
  document.addEventListener('visibilitychange', loadPhoto);
  loadPhoto();
}
if (document.querySelectorAll('.daily-view img[data-photo-url]').length) {
  const dailyPhotoObserver = new IntersectionObserver(entries => {
    if (document.hidden) return;
    for (const entry of entries) {
      if (entry.isIntersecting && entry.target.getClientRects().length) {
        loadPlacePhoto(entry.target);
        dailyPhotoObserver.unobserve(entry.target);
      }
    }
  });
  const observeDailyPhotos = () => {
    if (document.hidden) return;
    for (const image of document.querySelectorAll('.daily-view img[data-photo-url]')) {
      if (!image.dataset.photoState) dailyPhotoObserver.observe(image);
    }
  };
  observeDailyPhotos();
  window.addEventListener('hashchange', observeDailyPhotos);
  document.addEventListener('visibilitychange', observeDailyPhotos);
}
for (const carousel of document.querySelectorAll('.carousel')) {
  const radios = [...carousel.querySelectorAll('input[name="highlight"]')];
  if (radios.length < 2) continue;
  let timer, inView = false;
  const stop = () => { clearTimeout(timer); timer = undefined; };
  function schedule() {
    stop();
    if (!inView || document.hidden || !carousel.getClientRects().length) return;
    const selected = carousel.querySelector('input[name="highlight"]:checked');
    const image = selected && carousel.querySelector('.slide-' + selected.id.split('-').pop() + ' img[data-photo-url]');
    if (image?.dataset.photoState === 'loading') return;
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
  carousel.addEventListener('photo-ready', schedule);
  document.addEventListener('visibilitychange', schedule);
  window.addEventListener('hashchange', schedule);
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', schedule);
}
"""
