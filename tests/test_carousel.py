from html import escape

from travelmate.carousel import coverflow, CAROUSEL_CSS


def days(count):
    return [{'rows': [['上午', place, '顺路游览，适当休息', '', '']]} for place in ['西湖', '灵隐寺', '龙井茶园'][:count]]


def test_coverflow_images_states_and_day_navigation():
    html = coverflow(days(3), escape)
    assert '/assets/visual/cities/hangzhou.webp' in html
    assert '/assets/visual/town.webp' in html and '/assets/visual/mountains.webp' in html
    assert 'rotateY' not in html and 'translateX(105%)' in html
    assert 'for="highlight-3"' in html and '03 / 03' in html
    assert 'data-carousel-target="highlight-3" aria-label="上一个景点"' in html
    assert 'href="#day-3"' in html and '每天都有一点期待' in html
    assert '默认风景 · 示意图' in html
    assert 'data:image' not in html
    assert 'data:image/webp;base64,' in coverflow(days(1), escape, inline_images=True)


def test_zero_one_two_and_escaping():
    assert '本版暂无景点安排' in coverflow([], escape)
    single = coverflow(days(1), escape)
    assert single.count('disabled') == 2
    assert 'translateX(-105%)' not in single
    two = coverflow(days(2), escape)
    assert 'translateX(-105%)' in two and 'translateX(105%)' not in two
    html = coverflow([{'rows': [['上午', '<img src=x>', '<script>unsafe</script>']]}], escape)
    assert '<img src=x>' not in html and '<script>' not in html
    assert '&lt;img src=x&gt;' in html
    assert '<div class="carousel-caption"><strong>&lt;img src=x&gt;</strong></div>' in html
    assert 'prefers-reduced-motion' in CAROUSEL_CSS
    assert '@media print' in CAROUSEL_CSS


def test_overview_shows_saved_description_time_and_duration():
    from travelmate.carousel import visit_duration
    row = ['09:00–10:30', '西湖', '沿湖漫步，欣赏湖边风光。']
    html = coverflow([{'rows': [row]}], escape, city='杭州')
    assert '09:00–10:30 · 1小时30分钟' in html
    assert '沿湖漫步，欣赏湖边风光。' in html
    assert visit_duration(['上午', '西湖', '建议游玩2小时']) == '2小时'
    assert visit_duration(['上午', '西湖', '随意散步']) == '游玩时长待确认'
    assert visit_duration(['25:00–26:00', '西湖']) == '游玩时长待确认'


def test_overview_only_shows_unique_attractions_with_photo_fallback():
    route = [{'rows': [['上午', name, '安排说明'] for name in
                       ('酒店入住', '早餐', '西湖', '西湖', '午餐', '灵隐寺', '杭州东站返程')]}]
    html = coverflow(route, escape, city='杭州')
    assert html.count('class="carousel-slide ') == 2
    assert '酒店入住' not in html and '杭州东站返程' not in html and '早餐' not in html
    assert 'data-photo-url="/api/places/photo?' in html
    assert '暂无景点图片' in html and '默认风景 · 示意图' in html
    assert 'data-photo-url' not in coverflow(route, escape, True, city='杭州')
    mixed = coverflow([{'rows': [['上午', '泉州站 → 潮汕站（动车二等座） → 酒店放行李 + 牌坊街漫步', '古城游览']]}], escape)
    assert '牌坊街' in mixed and '泉州站' not in mixed and '行李' not in mixed


def test_already_failed_default_photo_shows_empty_state():
    import subprocess
    from travelmate.carousel import CAROUSEL_JS
    stub = r"""
const assert = require('node:assert/strict');
const note = {textContent:'默认风景 · 示意图'};
const image = {complete:true,naturalWidth:0,hidden:false,addEventListener(){},
  closest:()=>({querySelector:()=>note})};
global.document={addEventListener(){},querySelectorAll:s=>s==='.carousel-photo img'?[image]:[]};
global.window={addEventListener(){}};
"""
    subprocess.run(['node', '-e', stub + CAROUSEL_JS + "\nassert.equal(image.hidden,true);assert.equal(note.textContent,'暂无景点图片');"],
                   check=True, capture_output=True, text=True)


def test_autoplay_only_pauses_when_not_visible():
    import subprocess
    from travelmate.carousel import CAROUSEL_JS
    stub = r"""
const assert = require('node:assert/strict');
const win = {}, doc = {}; let callback, active=0, visible=true, pending=new Map(), id=0;
global.setTimeout=(fn,delay)=>{assert.equal(delay,4000);pending.set(++id,fn);return id;};
global.clearTimeout=id=>pending.delete(id);
const radios=[0,1,2].map(i=>({get checked(){return active===i;},set checked(v){if(v)active=i;}}));
const carousel={querySelectorAll:()=>radios,querySelector:s=>s.includes(':checked')?null:{},getClientRects:()=>visible?[{}]:[],addEventListener(){},dispatchEvent(){}};
global.window={addEventListener:(n,f)=>win[n]=f};
global.document={hidden:false,querySelectorAll:s=>s==='.carousel'?[carousel]:[],addEventListener:(n,f)=>doc[n]=f};
global.IntersectionObserver=class{constructor(fn){callback=fn;}observe(){}};
function tick(){assert.equal(pending.size,1);const fn=[...pending.values()][0];pending.clear();fn();}
"""
    checks = r"""
assert.equal(pending.size,0);callback([{isIntersecting:true}]);tick();assert.equal(active,1);
tick();tick();assert.equal(active,0);
callback([{isIntersecting:false}]);assert.equal(pending.size,0);
callback([{isIntersecting:true}]);assert.equal(pending.size,1);
document.hidden=true;doc.visibilitychange();assert.equal(pending.size,0);
document.hidden=false;doc.visibilitychange();assert.equal(pending.size,1);
visible=false;win.hashchange();assert.equal(pending.size,0);
visible=true;win.hashchange();assert.equal(pending.size,1);
win.pagehide();assert.equal(pending.size,0);win.pageshow();assert.equal(pending.size,1);
"""
    subprocess.run(['node','-e',stub+CAROUSEL_JS+checks],check=True,capture_output=True,text=True)
    assert 'mouseenter' not in CAROUSEL_JS and 'focusin' not in CAROUSEL_JS
    assert 'data-carousel-playback' not in coverflow(days(3), escape)


def test_manual_changes_restart_full_autoplay_delay():
    import subprocess
    from travelmate.result import RESULT_JS

    stub = r"""
const assert = require('node:assert/strict');
let now=0, id=0, active=0, observer;
const pending=new Map();
global.setTimeout=(fn,delay)=>{pending.set(++id,{fn,at:now+delay});return id;};
global.clearTimeout=id=>pending.delete(id);
function advance(ms){
  const end=now+ms;
  while(true){
    const next=[...pending].sort((a,b)=>a[1].at-b[1].at)[0];
    if(!next || next[1].at>end) break;
    now=next[1].at;pending.delete(next[0]);next[1].fn();
  }
  now=end;
}
const carousel=new EventTarget();
const radios=[0,1,2].map(i=>({
  get checked(){return active===i;},set checked(v){if(v)active=i;},
  focus(){},dispatchEvent(event){if(event.bubbles)carousel.dispatchEvent(event);}
}));
Object.assign(carousel,{querySelectorAll:()=>radios,querySelector:s=>s.includes(':checked')?null:{},getClientRects:()=>[{}]});
const buttons=[1,2].map(i=>Object.assign(new EventTarget(),{dataset:{carouselTarget:`highlight-${i+1}`}}));
global.document={hidden:false,addEventListener(){},querySelector:()=>null,
  querySelectorAll:s=>s==='[data-carousel-target]'?buttons:s==='.carousel'?[carousel]:[],
  getElementById:id=>radios[Number(id.split('-')[1])-1]};
global.window={addEventListener(){}};
global.IntersectionObserver=class{constructor(fn){observer=fn;}observe(){}};
"""
    checks = r"""
observer([{isIntersecting:true}]);
for(const [button,selected] of [[buttons[0],1],[buttons[1],2]]){
  active=0;
  advance(3999);
  button.dispatchEvent(new Event('click'));
  assert.equal(active,selected);
  assert.equal(pending.size,1);
  advance(1);assert.equal(active,selected,'old timer must not advance the new slide');
  advance(3998);assert.equal(active,selected,'manual selection gets a full 4 seconds');
  advance(1);assert.equal(active,(selected+1)%3);
}
// Native label and keyboard changes also bubble a change event.
advance(3999);active=1;carousel.dispatchEvent(new Event('change'));
advance(3999);assert.equal(active,1);
advance(1);assert.equal(active,2);assert.equal(pending.size,1);
"""
    subprocess.run(['node', '-'], input=stub + RESULT_JS + checks, check=True, capture_output=True, text=True, encoding='utf-8')


def test_photo_loading_prefetches_all_slides_prioritizes_selection_and_shares_requests():
    import subprocess
    from travelmate.carousel import CAROUSEL_JS
    stub = r"""
import assert from 'node:assert/strict';
const downloads=[], observers=[], timers=new Map(); let timerId=0, active=0;
globalThis.setTimeout=(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;};
globalThis.clearTimeout=id=>timers.delete(id);
globalThis.fetch=(url,{signal})=>new Promise((resolve,reject)=>{
  downloads.push({url,resolve});signal.addEventListener('abort',()=>reject(new Error('aborted')));
});
globalThis.URL.createObjectURL=blob=>'blob:'+blob.url;
const carousel=new EventTarget();
const radios=[1,2,3].map(n=>({id:`highlight-${n}`,get checked(){return active===n-1;},set checked(v){if(v)active=n-1;}}));
function image(url,owner=carousel){
  const note={textContent:'默认风景 · 示意图'};
  return {dataset:{photoUrl:url},hidden:false,alt:'示意图',parentElement:{querySelector:()=>note},
    closest:()=>owner,getClientRects:()=>[{}],note};
}
const photos=[1,2,3].map(n=>image(`/photo/${n}`));
const daily=image('/photo/1',null);
Object.assign(carousel,{
  querySelectorAll:s=>s==='img[data-photo-url]'?photos:radios,getClientRects:()=>[{}],
  querySelector:s=>s.includes(':checked')?radios[active]:s.includes('input')?null:
    s.includes('img[data-photo-url]')?photos[Number(s.match(/slide-(\d)/)[1])-1]:
    s.includes('.slide-')?{querySelector:()=>photos[Number(s.match(/slide-(\d)/)[1])-1]}:{},
});
globalThis.document={hidden:false,addEventListener(){},
  querySelectorAll:s=>s==='.carousel:has([data-photo-url])'||s==='.carousel'?[carousel]:[]};
globalThis.window={addEventListener(){}};
globalThis.IntersectionObserver=class {constructor(fn){observers.push(fn);}observe(){}unobserve(){}};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
"""
    checks = r"""
observers[0]([{isIntersecting:true}]); // Autoplay sees the initial prefetch and waits.
loadPlacePhoto(daily);
await flush();
assert.equal(downloads.length,1,'overview and daily must share one request');
assert.equal([...timers.values()].some(t=>t.ms===4000),false,'slow image must hold autoplay');
downloads[0].resolve({ok:true,blob:async()=>({url:'/photo/1'})});await flush();
assert.equal(photos[0].src,'blob:/photo/1');assert.equal(daily.src,'blob:/photo/1');
assert.equal(daily.note.textContent,'小红书 · 搜索配图');
assert.equal(downloads.length,2,'continue prefetching without a slide change');
assert.equal(photos[2].dataset.photoState,'loading','queue even hidden slides immediately');
assert.equal([...timers.values()].some(t=>t.ms===4000),true);
downloads[1].resolve({ok:false,status:503,json:async()=>({error:'image_download_failed'})});await flush();
assert.equal(photos[1].dataset.photoState,'failed');assert.equal(photos[1].src,undefined);
assert.equal(downloads.length,3,'failed images must not stop the remaining prefetches');
active=1;carousel.dispatchEvent(new Event('change'));await flush();
assert.equal(downloads.length,3);
const timeout=[...timers.values()].find(t=>t.ms===45000);timeout.fn();await flush();
assert.equal(photos[2].dataset.photoState,'failed','timeout must release the queue');
const expired=image('/photo/4',null);loadPlacePhoto(expired);await flush();
downloads[3].resolve({ok:false,status:503,json:async()=>({error:'login_or_risk_control'})});await flush();
assert.ok(expired.note.textContent.includes('小红书登录失效或受限'));
const later=image('/photo/5',null);loadPlacePhoto(later);await flush();
assert.equal(downloads.length,4,'stop issuing requests after login is rejected');
assert.ok(later.note.textContent.includes('小红书登录失效或受限'));
"""
    result = subprocess.run(['node', '--input-type=module', '-'], input=stub + CAROUSEL_JS + checks,
                            capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stderr
