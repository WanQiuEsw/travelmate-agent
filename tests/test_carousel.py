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
const carousel={querySelectorAll:()=>radios,querySelector:()=>({}),getClientRects:()=>visible?[{}]:[]};
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
