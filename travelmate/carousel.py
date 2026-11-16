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
.carousel{container-type:inline-size;position:relative;padding:20px 0 0;margin:0 0 24px;text-align:left;overflow:hidden;color:#201c18}
.carousel-heading,.carousel-intro,.carousel-help,.carousel-copy .carousel-cta,.carousel-time{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%)}
.carousel>input{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.carousel:has(>input:focus-visible){outline:2px solid #c56539;outline-offset:-2px}
.carousel-stage{position:relative;height:680px;margin:0}.carousel-slide{--gallery-copy-opacity:0;position:absolute;top:0;left:7.5%;width:85%;opacity:0;visibility:hidden;pointer-events:none;transform:translateX(0);transition:transform .4s ease,opacity .3s,visibility .4s}
.carousel .highlight{display:grid;grid-template-columns:minmax(0,1fr) auto;position:relative;color:inherit;text-decoration:none;background:#fff;border:0;border-radius:0;box-shadow:none}
.carousel-photo{grid-column:1/-1;position:relative;aspect-ratio:3/4;max-height:70svh;overflow:hidden;border-radius:16px;background:#f7f4f0}.carousel-photo>img{position:absolute;inset:0;display:block;width:100%;height:calc(100% - 19px);object-fit:contain}.carousel-photo img[hidden]{display:none}
.carousel-placeholder{position:absolute;inset:0;display:none;place-items:center;padding:16px;text-align:center;font-size:13px;color:#8b8078}.carousel-photo:has(img[hidden]) .carousel-placeholder{display:grid}
.carousel-image-note{position:absolute;inset:auto 0 0;height:19px;line-height:19px;background:#fff;color:#91867e;font-size:10px;text-align:right}
.carousel-caption,.carousel-meta,.carousel-copy{opacity:var(--gallery-copy-opacity,1)}.carousel-caption{grid-column:1;padding:16px 0 0;min-width:0}.carousel-caption strong{display:block;font:700 clamp(27px,5.8cqw,36px)/1.35 Georgia,'Songti SC',SimSun,serif;overflow-wrap:anywhere}
.carousel-meta{grid-column:2;grid-row:2;align-self:center;padding:16px 0 0 12px}.carousel-meta small{display:inline-block;border-radius:99px;background:#fbf0e7;padding:3px 10px;font-size:12px;color:#b85e32;white-space:nowrap}
.carousel-copy{grid-column:1/-1;padding:6px 0 0;min-width:0}.carousel-copy p{margin:0;font-size:15px;line-height:1.65;color:#615952;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.carousel-side-select{position:absolute;inset:0;border-radius:16px;cursor:pointer;display:none}
.carousel-controls{display:none;grid-template-columns:44px minmax(0,1fr) 44px;align-items:center;justify-content:space-between;gap:12px;margin:16px 0 0;padding:0;color:#c56539;font-size:19px;font-variant-numeric:tabular-nums;font-weight:600;text-align:center}.carousel-controls button{display:grid;place-items:center;width:44px;height:44px;border:0;background:none;color:#201c18;font-size:34px;line-height:1;cursor:pointer}.carousel-controls button:disabled{opacity:.35;cursor:default}.carousel-controls button:focus-visible{outline:2px solid #c56539;outline-offset:2px}
.carousel-dots{position:relative;display:flex;gap:12px;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin;margin:14px 0 0;padding:4px 4% 12px}.carousel-dot{position:relative;flex:0 0 calc((100% - 36px)/4);min-width:0;padding:0 0 10px;cursor:pointer;color:#302821;text-align:center}.carousel-dot:after{content:'';position:absolute;bottom:0;left:24%;right:24%;height:3px;border-radius:3px;background:transparent}.carousel-thumb-photo{aspect-ratio:4/5;max-height:none;border-radius:10px}.carousel-thumb-photo>img{height:100%}.carousel-thumb-photo .carousel-image-note{display:none}.carousel-dot>span{display:block;margin-top:7px;font-size:12px;line-height:1.5;overflow-wrap:anywhere}
.carousel-days{margin:16px 7.5% 0;border-top:1px solid #eee7e0;padding-top:12px;color:#776b61}.carousel-days summary{font-size:13px}.carousel-day-links{display:flex;gap:10px;overflow-x:auto;padding:12px 0}.carousel-day-links a{flex:0 0 150px;padding:10px;border:1px solid #eee7e0;border-radius:10px;color:#4f4237;font-size:13px;text-decoration:none}.carousel-day-links small{display:block;color:#c56539}
@media(prefers-reduced-motion:reduce){.carousel-slide{transition:none}}
@media print{.carousel{overflow:visible}.carousel-stage{height:auto!important}.carousel .carousel-slide{--gallery-copy-opacity:1!important;position:static;visibility:visible!important;opacity:1!important;transform:none!important;width:100%;margin-bottom:20px;break-inside:avoid}.carousel-photo{height:220px;aspect-ratio:auto}.carousel-controls,.carousel>input,.carousel-dots,.carousel-side-select{display:none!important}.carousel-time{position:static;width:auto;height:auto;clip-path:none}.carousel-days{display:none}}
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
        positions = [(n, 'translateX(0)', '1', 'none', 3)]
        if len(slides) > 1:
            positions.append(((n-2) % len(slides)+1, 'translateX(-105%)', '1', 'none', 1))
        if len(slides) > 2:
            positions.append((n % len(slides)+1, 'translateX(105%)', '1', 'none', 1))
        for target, transform, opacity, filtering, z in positions:
            selector = f'.carousel:has(#highlight-{n}:checked) .slide-{target}'
            rules.append(selector + '{visibility:visible;opacity:' + opacity + ';transform:' + transform + ';filter:' + filtering + f';z-index:{z}' + '}')
            if target != n:
                rules.append(selector + ' .carousel-side-select{display:block;pointer-events:auto}')
                rules.append(selector + ' .carousel-meta{display:none}')
        active = f'.carousel:has(#highlight-{n}:checked)'
        rules.extend([active + f' .slide-{n}' + '{pointer-events:auto;--gallery-copy-opacity:1}', active + f' .slide-{n} .carousel-controls' + '{display:grid}',
                      active + f' label[for="highlight-{n}"].carousel-dot:after' + '{background:#c56539}', active + f' label[for="highlight-{n}"] .carousel-thumb-photo' + '{outline:2px solid #c56539;outline-offset:2px}'])
    out.append('<style>' + ''.join(rules) + '</style><div class="carousel-stage">')
    for n, (i, j, row) in enumerate(slides, 1):
        previous, following = (n-2) % len(slides)+1, n % len(slides)+1
        remote = f' data-photo-url="{text(photo_url(city, row[1]))}"' if not inline_images and city else ''
        description = row[2] if len(row) > 2 and row[2].strip() else '查看当天安排，了解游览与交通提醒。'
        out.append(f'<article class="carousel-slide slide-{n}"><a class="highlight" href="#day-{i}"><div class="carousel-photo"><span class="carousel-placeholder">暂无景点图片</span><img src="{text(scenery(row[1]))}" alt="默认风景示意图，非景点实拍"{remote}><span class="carousel-image-note">默认风景 · 示意图</span></div><div class="carousel-caption"><strong>{text(row[1])}</strong></div><div class="carousel-meta"><small>第 {i} 天</small><span class="carousel-time">{text(row[0])} · {text(visit_duration(row))}</span></div><div class="carousel-copy"><p>{text(description)}</p><span class="carousel-cta">查看当日日程 ↗</span></div></a><label class="carousel-side-select" for="highlight-{n}" aria-label="切换至{text(row[1])}"></label><div class="carousel-controls"><button type="button" data-carousel-target="highlight-{previous}" aria-label="上一个景点" {"disabled" if len(slides) == 1 else ""}>‹</button><span>{n:02d} / {len(slides):02d}</span><button type="button" data-carousel-target="highlight-{following}" aria-label="下一个景点" {"disabled" if len(slides) == 1 else ""}>›</button></div></article>')
    out.append('</div><div class="carousel-dots" aria-label="选择景点">')
    for n, (_, _, row) in enumerate(slides, 1):
        remote = f' data-photo-url="{text(photo_url(city, row[1]))}"' if not inline_images and city else ''
        out.append(f'<label class="carousel-dot" for="highlight-{n}" aria-label="选择景点 {n}：{text(row[1])}"><div class="carousel-photo carousel-thumb-photo"><span class="carousel-placeholder">暂无图片</span><img src="{text(scenery(row[1]))}" alt="默认风景示意图，非景点实拍"{remote}><span class="carousel-image-note">默认风景 · 示意图</span></div><span>{text(row[1])}</span></label>')
    out.append('</div><p class="carousel-help">点击两侧卡片或使用方向键切换 · 点击主卡片查看当日日程</p><details class="carousel-days"><summary>每天都有一点期待</summary><div class="carousel-day-links">')
    for i, day in enumerate(days, 1):
        title = next((row[1] for day_no, _, row in slides if day_no == i), f'查看第 {i} 天安排')
        out.append(f'<a href="#day-{i}"><small>DAY {i:02d}</small><span>{text(title)}</span></a>')
    return ''.join(out) + '</div></details></div>'


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
    const thumb = selected && carousel.querySelector('label[for="' + selected.id + '"].carousel-dot');
    if (thumb && (thumb.offsetLeft < thumb.parentElement.scrollLeft || thumb.offsetLeft + thumb.offsetWidth > thumb.parentElement.scrollLeft + thumb.parentElement.clientWidth)) {
      thumb.parentElement.scrollTo({left: thumb.offsetLeft - (thumb.parentElement.clientWidth - thumb.offsetWidth) / 2, behavior: 'instant'});
    }
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
  let touchStart, swipedAt = 0;
  carousel.addEventListener('touchstart', event => { touchStart = event.touches.length === 1 ? event.touches[0] : null; }, {passive:true});
  carousel.addEventListener('touchend', event => {
    const end = event.changedTouches[0];
    if (!touchStart || !end) return;
    const dx = end.clientX - touchStart.clientX, dy = end.clientY - touchStart.clientY;
    touchStart = null;
    if (Math.abs(dx) < 50 || Math.abs(dx) <= Math.abs(dy)) return;
    const index = radios.findIndex(radio => radio.checked);
    radios[(index + (dx < 0 ? 1 : radios.length - 1)) % radios.length].checked = true;
    swipedAt = Date.now();
    carousel.dispatchEvent(new Event('change', {bubbles:true}));
  }, {passive:true});
  carousel.addEventListener('click', event => { if (Date.now() - swipedAt < 400) event.preventDefault(); }, true);
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
