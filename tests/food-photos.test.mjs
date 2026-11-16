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

test('timeouts release the queue and a rejected login stops the remaining batch', async () => {
  const requests = [], timers = new Map();
  let id = 0;
  const images = [1, 2, 3].map(n => ({dataset: {photoUrl: '/photo/' + n}, parentElement: {querySelector: () => null}}));
  const context = vm.createContext({images, document: {hidden: false, addEventListener() {}}, AbortController,
    setTimeout(fn, delay) {timers.set(++id, {fn, delay}); return id;}, clearTimeout(id) {timers.delete(id);},
    fetch: (url, {signal}) => new Promise((resolve, reject) => {
      requests.push({url, resolve});
      signal.addEventListener('abort', () => reject(new Error('timeout')));
    }),
  });
  vm.runInContext(loader + '\nimages.forEach(image => loadPlacePhoto(image));', context);
  [...timers.values()].find(timer => timer.delay === 45000).fn();
  await tick();
  assert.equal(images[0].dataset.photoState, 'failed');
  assert.equal(requests.length, 2);
  requests[1].resolve({ok: false, status: 503, json: async () => ({error: 'login_or_risk_control'})});
  await tick();
  assert.equal(images[2].dataset.photoState, 'failed');
  assert.equal(requests.length, 2, 'do not keep contacting XHS after login rejection');
});

test('all food images preload without scrolling or changing tabs, sharing one request per dish', async () => {
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
