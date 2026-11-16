import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const script = readFileSync(new URL('../travelmate/food_ui.py', import.meta.url), 'utf8').split('FOOD_JS = r"""')[1].split('"""')[0];
const loader = readFileSync(new URL('../travelmate/carousel.py', import.meta.url), 'utf8').split('CAROUSEL_JS = r"""')[1].split("window.addEventListener('pagehide'")[0];
const tick = () => new Promise(setImmediate);

test('a selected image jumps ahead of queued prefetches without duplicate downloads', async () => {
  const requests = [];
  const images = [1, 2, 3].map(n => ({dataset: {foodPhoto: '/photo/' + n},
    parentElement: {querySelector: () => null}, closest: () => null}));
  const context = vm.createContext({document: {hidden: false, addEventListener() {}},
    AbortController, setTimeout, clearTimeout, URL: {createObjectURL: () => 'blob:photo'},
    fetch: url => new Promise(resolve => requests.push({url, resolve})),
  });
  vm.runInContext(loader, context);
  context.images = images;
  vm.runInContext('images.forEach(image => loadPlacePhoto(image)); loadPlacePhoto(images[2], true);', context);
  assert.deepEqual(requests.map(r => r.url), ['/photo/1']);
  requests[0].resolve({ok: true, blob: async () => ({})});
  await tick();
  assert.deepEqual(requests.map(r => r.url), ['/photo/1', '/photo/3']);
  requests[1].resolve({ok: true, blob: async () => ({})});
  await tick();
  assert.equal(requests[2].url, '/photo/2');
  requests[2].resolve({ok: true, blob: async () => ({})});
  await tick();
});

test('prefetch obeys Retry-After and retries a rate-limited request once', async () => {
  const timers = new Map();
  let id = 0, requests = 0;
  const image = {dataset: {foodPhoto: '/photo/1'}, parentElement: {querySelector: () => null}, closest: () => null};
  const context = vm.createContext({image, document: {hidden: false, addEventListener() {}}, AbortController,
    setTimeout(fn, delay) {timers.set(++id, {fn, delay}); return id;}, clearTimeout(id) {timers.delete(id);},
    URL: {createObjectURL: () => 'blob:photo'},
    fetch: async () => ++requests === 1 ? {status: 429, headers: {get: () => '12'}} : {ok: true, blob: async () => ({})},
  });
  vm.runInContext(loader + '\nloadPlacePhoto(image);', context);
  await tick();
  assert.equal(requests, 1);
  assert.equal(timers.size, 1);
  assert.equal([...timers.values()][0].delay, 12000);
  [...timers.values()][0].fn();
  await tick();
  assert.equal(requests, 2);
  assert.equal(image.hidden, false);
});

test('all food images preload without visibility or a slide change, sharing one request per dish', async () => {
  let finish;
  const requests = [], events = {};
  const images = ['same-dish', 'same-dish', 'failure'].map(name => {
    const image = {hidden: true, dataset: {foodPhoto: '/photo/' + name}, closest: () => null};
    image.parentElement = {querySelector: selector => selector === '[data-food-photo]' ? image : null, getClientRects: () => [1]};
    return image;
  });
  const document = {hidden: true, querySelectorAll: selector => selector === '[data-food-photo]' ? images : [], addEventListener: (name, fn) => {events[name] = fn;}};
  vm.runInNewContext(loader + script, {
    document, window: {addEventListener: (name, fn) => {events[name] = fn;}},
    setTimeout, clearTimeout, AbortController,
    URL: {createObjectURL: () => 'blob:food-photo'},
    fetch: async url => {
      requests.push(url);
      if (url.endsWith('failure')) return {ok: false, status: 404, json: async () => ({error: 'no_photo'})};
      await new Promise(resolve => {finish = resolve;});
      return {ok: true, blob: async () => ({})};
    },
  });
  assert.equal(requests.length, 0);
  document.hidden = false;
  events.visibilitychange();
  await tick();
  assert.deepEqual(requests, ['/photo/same-dish']);
  finish();
  await tick();
  assert.deepEqual(requests, ['/photo/same-dish', '/photo/failure']);
  assert.equal(images[0].src, images[1].src);
  assert.equal(images[0].hidden, false);
  assert.equal(images[2].hidden, true);
  images[0].onerror();
  assert.equal(images[0].hidden, true);
  events.hashchange();
  await tick();
  assert.equal(requests.length, 2, 'revisiting the panel must reuse loaded photos');
});

test('buttons, thumbnails, keyboard and touch scrolling synchronize selection and wrap', () => {
  const events = {}, active = new Set(), count = {};
  const strip = {scrollLeft: 0, clientWidth: 180, scrollTo({left}) { this.scrollLeft = left; }};
  const cards = [0, 1, 2].map(i => ({offsetLeft: 140 + i * 740, offsetWidth: 720, querySelector: () => null,
    classList: {toggle: (_, enabled) => enabled ? active.add(i) : active.delete(i)}}));
  const thumbs = cards.map((_, i) => ({offsetLeft: i * 120, offsetWidth: 108, parentElement: strip,
    setAttribute(name, value) {this[name] = value;}, addEventListener(_, fn) {this.click = fn;}}));
  const steps = [-1, 1].map(step => ({dataset: {foodStep: String(step)}, addEventListener(_, fn) {this.click = fn;}}));
  const track = {scrollLeft: 0, clientWidth: 1000, querySelectorAll: () => cards,
    addEventListener(name, fn) {events[name] = fn;}, scrollTo({left}) {this.scrollLeft = left;}};
  const food = {querySelector: selector => selector === '.food-track' ? track : count,
    querySelectorAll: selector => selector === '[data-food-index]' ? thumbs : steps};
  let resize;
  vm.runInNewContext(script, {document: {querySelectorAll: selector => selector === '.food-shell' ? [food] : []}, matchMedia: () => ({matches: true}),
    ResizeObserver: class {constructor(callback) {resize = callback;} observe() {}}, loadPlacePhoto() {}});
  steps[0].click();
  assert.equal(count.textContent, '03 / 03');
  assert.equal(track.scrollLeft, 1480);
  assert.equal(thumbs[2]['aria-pressed'], 'true');
  assert.ok(strip.scrollLeft > 0);
  steps[1].click();
  assert.equal(count.textContent, '01 / 03');
  thumbs[1].click();
  assert.equal(track.scrollLeft, 740);
  let prevented = false;
  events.keydown({key: 'End', target: track, preventDefault() {prevented = true;}});
  assert.equal(count.textContent, '03 / 03');
  assert.equal(prevented, true);
  track.clientWidth = 800;
  events.scroll();
  resize();
  assert.equal(track.scrollLeft, 1580);
  assert.equal(count.textContent, '03 / 03');
  events.keydown({key: 'ArrowLeft', target: {}, preventDefault() {throw Error('nested control intercepted');}});
  track.scrollLeft = 0;
  events.scroll();
  assert.equal(count.textContent, '01 / 03');
  assert.deepEqual([...active], [0]);
});
