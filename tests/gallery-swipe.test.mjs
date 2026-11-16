import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
import assert from 'node:assert/strict';

test('overview touch swipes select slides, wrap, and do not open the itinerary accidentally', () => {
  const script = readFileSync(new URL('../travelmate/carousel.py', import.meta.url), 'utf8').split('CAROUSEL_JS = r"""')[1].split('"""')[0];
  let active = 0;
  const carousel = new EventTarget();
  const radios = [0, 1, 2].map(i => ({get checked() {return active === i;}, set checked(value) {if (value) active = i;}}));
  carousel.querySelectorAll = () => radios;
  carousel.querySelector = selector => selector.includes(':checked') ? null : {};
  carousel.getClientRects = () => [1];
  vm.runInNewContext(script, {
    Event, document: {hidden: false, addEventListener() {}, querySelectorAll: selector => selector === '.carousel' ? [carousel] : []},
    window: {addEventListener() {}}, IntersectionObserver: class {observe() {}},
    setTimeout, clearTimeout,
  });
  const touch = (type, point) => carousel.dispatchEvent(Object.assign(new Event(type), {[type === 'touchstart' ? 'touches' : 'changedTouches']: [point]}));
  const swipe = (x, y) => {touch('touchstart', {clientX: 150, clientY: 150}); touch('touchend', {clientX: x, clientY: y});};
  swipe(70, 150);
  assert.equal(active, 1);
  const click = new Event('click', {cancelable: true});
  carousel.dispatchEvent(click);
  assert.equal(click.defaultPrevented, true);
  swipe(145, 50);
  assert.equal(active, 1, 'vertical scrolling must not change slides');
  swipe(240, 150);
  assert.equal(active, 0);
  swipe(240, 150);
  assert.equal(active, 2);
});
