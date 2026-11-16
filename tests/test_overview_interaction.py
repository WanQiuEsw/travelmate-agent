import subprocess
from pathlib import Path


def test_portrait_carousel_navigation_focus_and_swipe():
    script = Path('travelmate/overview.js').read_text(encoding='utf-8')
    stub = r'''
const assert = require('node:assert/strict');
let now=1000;Date.now=()=>now;
function node() {
  return {listeners:{}, attrs:{}, style:{setProperty(k,v){this[k]=v;}},
    classList:{toggle(){},add(){},contains(){return true;}}, addEventListener(k,fn){this.listeners[k]=fn;},
    setAttribute(k,v){this.attrs[k]=v;}, focus(){this.focused=true;}};
}
function fixture(size) {
  const cards=Array.from({length:size},(_,i)=>{
    const card=node(), link=node();
    card.querySelector=s=>s==='h3'?{textContent:`景点${i}`}:link;
    return card;
  });
  const indicators=cards.map(()=>node()), carousel=node(), prev=node(), next=node(), count={};
  const feed=node();
  feed.querySelectorAll=s=>s==='.overview-card'?cards:indicators;
  feed.querySelector=s=>({'.overview-carousel':carousel,'.overview-prev':prev,'.overview-next':next,'.overview-count':count})[s];
  return {feed,cards,indicators,carousel,prev,next,count};
}
'''
    checks = r'''
const f=fixture(SIZE);
global.document={querySelectorAll:()=>[f.feed]};
eval(SCRIPT);
if (!SIZE) {assert.equal(f.prev.listeners.click,undefined);}
else {
  const label=i=>`${String(i+1).padStart(2,'0')} / ${String(SIZE).padStart(2,'0')}`;
  assert.equal(f.count.textContent,label(0));
  f.prev.listeners.click();assert.equal(f.count.textContent,label(SIZE-1));
  f.next.listeners.click();assert.equal(f.count.textContent,label(0));
  f.indicators[SIZE-1].listeners.click();assert.equal(f.count.textContent,label(SIZE-1));
  const key=k=>f.feed.listeners.keydown({key:k,target:{closest:()=>true},preventDefault(){}});
  key('Home');assert.equal(f.count.textContent,label(0));
  key('End');assert.equal(f.count.textContent,label(SIZE-1));
  key('ArrowRight');assert.equal(f.count.textContent,label(0));
  assert.equal(f.cards[0].querySelector('a').focused,true);
  assert.equal(f.indicators[0].attrs['aria-current'],'true');
  if(SIZE>1) {
    let prevented=false;
    f.cards[1].listeners.click({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);assert.equal(f.count.textContent,label(1));
    let activePrevented=false;
    f.cards[1].listeners.click({preventDefault(){activePrevented=true;}});
    assert.equal(activePrevented,false);
  }
  key('Home');
  const swipe=(x,y)=>{
    f.carousel.listeners.touchstart({touches:[{clientX:200,clientY:200}]});
    f.carousel.listeners.touchend({changedTouches:[{clientX:x,clientY:y}]});
  };
  swipe(100,205);assert.equal(f.count.textContent,label(1%SIZE));
  now+=500;
  let blocked=false;
  f.carousel.listeners.click({preventDefault(){blocked=true;},stopPropagation(){}});
  assert.equal(blocked,false,'a completed swipe must not swallow the next normal click');
  swipe(200,320);assert.equal(f.count.textContent,label(1%SIZE));
  if(SIZE>4) assert.ok(f.cards.some(card=>card.inert));
}
'''
    import json
    for size in (0, 1, 2, 3, 12):
        subprocess.run(['node', '-'], input=stub + f'const SIZE={size}, SCRIPT={json.dumps(script)};\n' + checks,
                       text=True, encoding='utf-8', capture_output=True, check=True)
