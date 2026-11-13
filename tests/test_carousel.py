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


def test_autoplay_timer_pause_resume_and_accessibility():
    import subprocess
    from travelmate.carousel import CAROUSEL_JS
    stub = r'''
const assert = require('node:assert/strict');
const handlers = {}, windowHandlers = {}, documentHandlers = {}, toggleHandlers = {};
let pending = new Map(), id = 0, visible = true;
global.setTimeout = (fn, delay) => { assert.equal(delay,4000); pending.set(++id,fn); return id; };
global.clearTimeout = key => pending.delete(key);
const radios = [0,1,2].map(i=>({get checked(){return active===i;},set checked(value){if(value)active=i;}}));
let active = 0;
const toggle = {hidden:true,addEventListener:(name,fn)=>toggleHandlers[name]=fn,setAttribute:(name,val)=>toggle[name]=val};
const carousel = {querySelectorAll:()=>radios,querySelector:()=>toggle,
 getClientRects:()=>visible?[{}]:[],contains:node=>node==='inside',addEventListener:(name,fn)=>handlers[name]=fn};
const motion = {matches:false,addEventListener:(_,fn)=>motion.change=fn};
global.window = {matchMedia:()=>motion,addEventListener:(name,fn)=>windowHandlers[name]=fn};
global.document = {hidden:false,querySelectorAll:()=>[carousel],addEventListener:(name,fn)=>documentHandlers[name]=fn};
function tick(){ assert.equal(pending.size,1); const fn=[...pending.values()][0];pending.clear();fn(); }
'''
    checks = r'''
assert.equal(toggle.hidden,false);assert.equal(toggle['aria-pressed'],'false');
tick();assert.equal(active,1);tick();tick();assert.equal(active,0);
handlers.mouseenter();assert.equal(pending.size,0);handlers.mouseleave();assert.equal(pending.size,1);
handlers.focusin();assert.equal(pending.size,0);handlers.focusout({relatedTarget:'inside'});assert.equal(pending.size,0);
handlers.focusout({relatedTarget:null});assert.equal(pending.size,1);
toggleHandlers.click();assert.equal(toggle['aria-pressed'],'true');assert.equal(pending.size,0);
document.hidden=true;documentHandlers.visibilitychange();toggleHandlers.click();assert.equal(pending.size,0);
document.hidden=false;documentHandlers.visibilitychange();assert.equal(pending.size,1);
visible=false;windowHandlers.hashchange();assert.equal(pending.size,0);
visible=true;windowHandlers.hashchange();assert.equal(pending.size,1);
active=2;handlers.change();tick();assert.equal(active,0);assert.equal(pending.size,1);
motion.matches=true;motion.change();assert.equal(pending.size,0);assert.equal(toggle.textContent,'开始自动轮播');
toggleHandlers.click();assert.equal(pending.size,1);
windowHandlers.pagehide();assert.equal(pending.size,0);windowHandlers.pageshow();assert.equal(pending.size,1);
'''
    subprocess.run(['node', '-e', stub + CAROUSEL_JS + checks], check=True, capture_output=True, text=True)
    reduced = stub.replace('matches:false', 'matches:true')
    subprocess.run(['node', '-e', reduced + CAROUSEL_JS + "assert.equal(pending.size,0);assert.equal(toggle['aria-pressed'],'true');"],
                   check=True, capture_output=True, text=True)
    single = stub.replace('map(i=>', 'slice(0,1).map(i=>')
    subprocess.run(['node', '-e', single + CAROUSEL_JS + 'assert.equal(pending.size,0);assert.equal(toggle.hidden,true);'],
                   check=True, capture_output=True, text=True)
