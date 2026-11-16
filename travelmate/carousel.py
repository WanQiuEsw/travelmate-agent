"""Overview photo feed and shared cached photo loading."""
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
            details = day.get('stop_details', [])
            detail = details[j - 1] if j <= len(details) else {}
            kind = detail.get('kind')
            if kind in ('transport', 'meal', 'lodging', 'rest'):
                continue
            if not kind and detail.get('activities') and set(detail['activities']) <= {'food', 'rest'}:
                continue
            for name in re.split(r'→|->|\+|、|；|;', row[1]):
                name = re.sub(r'^(?:抵达|到达|前往|游览|参观|打卡)\s*', '', name.strip())
                name = re.sub(r'(?:漫步|游览|打卡|游玩|参观)$', '', name).strip()
                key = re.sub(r'\s+', '', name)
                logistics = r'早餐|午餐|晚餐|午饭|晚饭|返程|返家|回家|出发|接站|接机|候机|乘车|乘机|高铁|动车|二等座|火车|机场|车站|酒店|入住|退房|行李|休息|自由活动|打车|地铁|公交|站(?:[（(].*[)）])?$'
                if not key or key in seen or (kind not in ('visit', 'experience') and re.search(logistics, name)):
                    continue
                seen.add(key)
                slide = [row[0], name, *row[2:]]
                if detail.get('highlight', '').strip():
                    slide = [row[0], name, detail['highlight'].strip(), *row[3:]]
                slides.append((i, j, slide))
    # shortcut: 概览最多展示12处核心地点，完整安排仍在每日行程中。
    return slides[:12]


CAROUSEL_CSS = Path(__file__).with_name('overview.css').read_text(encoding='utf-8')


def coverflow(days, text, inline_images=False, city=''):
    """Browse the saved attractions as a focused portrait-photo carousel."""
    slides = highlight_stops(days)
    out = ['<div class="overview-feed discovery-feed" role="region" aria-label="行程概览"><header class="discovery-heading"><h2>这次，我们去这些地方</h2><p>核心景点一眼看清，点击卡片查看当天安排。</p></header>']
    if not slides:
        return ''.join(out) + '<p class="discovery-empty">本版暂无景点安排，请返回对话补充旅行需求。</p></div>'
    sources = {}
    def scenery(place):
        name = 'mountains.webp' if any(w in place for w in ('山', '茶', '峰', '林')) else 'town.webp' if any(w in place for w in ('寺', '庙', '街', '镇', '馆')) else 'coast.webp'
        if any(w in place for w in ('西湖', '杭州')):
            name = 'cities/hangzhou.webp'
        if name not in sources:
            sources[name] = ('data:image/webp;base64,' + b64encode((Path(__file__).with_name('images') / name).read_bytes()).decode('ascii')
                             if inline_images else '/assets/visual/' + name)
        return sources[name]
    out.append('<div class="overview-carousel" aria-roledescription="轮播图" aria-label="行程景点与体验"><div class="overview-stage">')
    for n, (i, j, row) in enumerate(slides, 1):
        remote = f' data-photo-url="{text(photo_url(city, row[1]))}"' if not inline_images and city else ''
        duration = visit_duration(days[i - 1]['rows'][j - 1])
        description = row[2] if len(row) > 2 and row[2].strip() else '查看当天安排，了解游览与交通提醒。'
        out.append(f'<article id="overview-place-{n}" class="overview-card" aria-label="{text(row[1])}"><a class="overview-card-link" href="#day-{i}"><div class="overview-photo"><span class="discovery-placeholder">暂无景点图片</span><img src="{text(scenery(row[1]))}" alt="默认风景示意图，非景点实拍"{remote}></div><div class="overview-copy"><small class="carousel-image-note">默认风景 · 示意图</small><h3>{text(row[1])}</h3><p class="overview-description">{text(description)}</p><div class="overview-card-meta"><span class="overview-tag">第 {i} 天 · {text(row[0])} · {text(duration)}</span><span class="overview-cta">查看当天行程 ↗</span></div></div></a></article>')
    out.append('</div><button type="button" class="overview-arrow overview-prev" aria-label="上一个景点"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button><button type="button" class="overview-arrow overview-next" aria-label="下一个景点"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button></div><div class="overview-pagination"><div class="overview-indicators" aria-label="选择景点">')
    for n, (_, _, row) in enumerate(slides, 1):
        out.append(f'<button type="button" data-overview-index="{n - 1}" aria-label="第{n}个景点：{text(row[1])}"' + (' aria-current="true"' if n == 1 else '') + '></button>')
    out.append(f'</div><span class="overview-count" aria-live="polite" aria-atomic="true">01 / {len(slides):02d}</span></div><details class="overview-days"><summary>每天都有一点期待</summary><div class="overview-day-links">')
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
    const note = (image.closest('.overview-card') || image.parentElement).querySelector('.carousel-image-note, .daily-image-note, .food-placeholder small');
    const messages = {not_configured:'小红书图片未启用', invalid_cookie:'小红书登录配置无效',
      login_or_risk_control:'小红书登录失效或受限', login_required:'请先登录 TravelMate',
      no_photo:'未找到小红书配图', image_download_failed:'小红书图片下载失败', fetch_failed:'小红书图片暂时不可用'};
    if (note) note.textContent = src ? '小红书 · 搜索配图' : (messages[error] || '小红书图片暂时不可用') + (image.dataset.foodPhoto ? '' : ' · 示意图');
  });
}
document.addEventListener('visibilitychange', runPlacePhotoQueue);
window.addEventListener('pagehide', event => {
  if (!event.persisted) for (const task of placePhotos.values()) task.then(({src}) => { if (src) URL.revokeObjectURL(src); });
});

// Fetch the complete overview before the user scrolls to individual cards.
const overviewImages = [...document.querySelectorAll('.overview-feed img[data-photo-url]')];
for (const image of overviewImages) {
  const showEmpty = () => {
    image.hidden = true;
    image.closest('.overview-card').querySelector('.carousel-image-note').textContent = '暂无景点图片';
  };
  image.addEventListener('error', showEmpty);
  if (image.complete && !image.naturalWidth) showEmpty();
}
const preloadOverviewPhotos = () => {
  if (document.hidden) return;
  for (const image of overviewImages) loadPlacePhoto(image);
};
preloadOverviewPhotos();
document.addEventListener('visibilitychange', preloadOverviewPhotos);
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
"""
CAROUSEL_JS += Path(__file__).with_name('overview.js').read_text(encoding='utf-8')
