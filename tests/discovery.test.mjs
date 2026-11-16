import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
import assert from 'node:assert/strict';

test('masonry follows image/content heights, preserves order, and lays out hidden tabs on opening', () => {
  const source = readFileSync(new URL('../travelmate/discovery.js', import.meta.url), 'utf8');
  const events = {}, observed = [];
  let resize, gap = 24;
  const cards = [200, 300, 150].map(height => ({style: {}, firstElementChild: {height, getBoundingClientRect() {return {height: this.height};}}}));
  const grid = {children: cards, clientWidth: 0, classList: {add() {}}};
  vm.runInNewContext(source, {
    document: {querySelectorAll: () => [grid], addEventListener: (name, fn) => {events[name] = fn;}},
    window: {addEventListener: (name, fn) => {events[name] = fn;}},
    getComputedStyle: () => ({columnGap: String(gap)}),
    ResizeObserver: class {constructor(fn) {resize = fn;} observe(node) {observed.push(node);}},
  });
  assert.equal(cards[0].style.gridRowEnd, undefined, 'hidden panels must not be collapsed to zero height');
  grid.clientWidth = 1000;
  events.hashchange();
  const fits = card => {
    const pixels = Number(card.style.gridRowEnd.split(' ')[1]) * 4;
    assert.ok(pixels >= card.firstElementChild.height + gap && pixels < card.firstElementChild.height + gap + 4);
  };
  cards.forEach(fits);
  assert.deepEqual(observed, cards.map(card => card.firstElementChild));
  cards[0].firstElementChild.height = 420;
  resize();
  cards.forEach(fits);
  gap = 14;
  events.resize();
  cards.forEach(fits);
  assert.deepEqual(grid.children, cards);
});

test('overview images all preload without scrolling and share results with daily cards', async () => {
  const source = readFileSync(new URL('../travelmate/carousel.py', import.meta.url), 'utf8').split('CAROUSEL_JS = r"""')[1].split('"""')[0];
  const requests = [];
  const images = [1, 2, 3].map(n => ({dataset: {photoUrl: '/photo/' + n}, complete: false,
    addEventListener() {}, parentElement: {querySelector: () => ({})}}));
  const daily = {dataset: {photoUrl: '/photo/1'}, parentElement: {querySelector: () => null}};
  const context = vm.createContext({document: {hidden: false, addEventListener() {},
    querySelectorAll: selector => selector === '.overview-feed img[data-photo-url]' ? images : []},
    window: {addEventListener() {}}, AbortController, setTimeout, clearTimeout,
    URL: {createObjectURL: blob => 'blob:' + blob.url},
    fetch: async url => {requests.push(url);return {ok: true, blob: async () => ({url})};}, daily,
  });
  vm.runInContext(source + '\nloadPlacePhoto(daily);', context);
  await new Promise(setImmediate);
  assert.deepEqual(requests, ['/photo/1', '/photo/2', '/photo/3']);
  assert.equal(daily.src, images[0].src);
  assert.ok(images.every(image => image.dataset.photoState === 'ready'));
});
