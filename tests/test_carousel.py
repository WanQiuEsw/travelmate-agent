from html import escape

from travelmate.carousel import coverflow, CAROUSEL_CSS


def days(count):
    return [{'rows': [['上午', place, '顺路游览，适当休息', '', '']]} for place in ['西湖', '灵隐寺', '龙井茶园'][:count]]


def test_coverflow_images_states_and_day_navigation():
    html = coverflow(days(3), escape)
    assert '/assets/visual/cities/hangzhou.webp' in html
    assert '/assets/visual/town.webp' in html and '/assets/visual/mountains.webp' in html
    assert 'rotateY(12deg)' in html and 'translateX(64%)' in html
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
    assert 'translateX(-64%)' not in single
    two = coverflow(days(2), escape)
    assert 'translateX(-64%)' in two and 'translateX(64%)' not in two
    html = coverflow([{'rows': [['上午', '<img src=x>', '<script>unsafe</script>']]}], escape)
    assert '<img src=x>' not in html and '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'prefers-reduced-motion' in CAROUSEL_CSS
    assert '@media print' in CAROUSEL_CSS


def test_autoplay_only_pauses_when_not_visible():
    import subprocess
    from travelmate.carousel import CAROUSEL_JS
    stub = r"""
const assert = require('node:assert/strict');
const win = {}, doc = {}; let callback, active=0, visible=true, pending=new Map(), id=0;
global.setTimeout=(fn,delay)=>{assert.equal(delay,4000);pending.set(++id,fn);return id;};
global.clearTimeout=id=>pending.delete(id);
const radios=[0,1,2].map(i=>({get checked(){return active===i;},set checked(v){if(v)active=i;}}));
const carousel={querySelectorAll:()=>radios,querySelector:()=>({}),getClientRects:()=>visible?[{}]:[],addEventListener(){}};
global.window={addEventListener:(n,f)=>win[n]=f};
global.document={hidden:false,querySelectorAll:()=>[carousel],addEventListener:(n,f)=>doc[n]=f};
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
Object.assign(carousel,{querySelectorAll:()=>radios,querySelector:()=>({}),getClientRects:()=>[{}]});
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
    subprocess.run(['node', '-e', stub + RESULT_JS + checks], check=True, capture_output=True, text=True)
