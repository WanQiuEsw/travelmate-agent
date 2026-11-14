import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
import assert from 'node:assert/strict';

test('dish photos load only when visible, in sequence, and keep placeholders on failure', async () => {
  const source = readFileSync(new URL('../travelmate/food_ui.py', import.meta.url), 'utf8');
  const script = source.split('FOOD_JS = r"""')[1].split('"""')[0];
  let observer;
  const requests = [];
  const images = ['success', 'failure'].map(name => {
    const image = {hidden: true, dataset: {foodPhoto: '/photo/' + name}};
    image.parentElement = {querySelector: () => image, getClientRects: () => [1]};
    Object.defineProperty(image, 'src', {set(url) { requests.push(url); }});
    return image;
  });
  vm.runInNewContext(script, {
    Promise,
    document: {querySelectorAll: () => images},
    IntersectionObserver: class {
      constructor(callback) { this.callback = callback; this.observed = new Set(); observer = this; }
      observe(node) { this.observed.add(node); }
      unobserve(node) { this.observed.delete(node); }
    },
  });
  assert.equal(requests.length, 0);
  observer.callback(images.map(image => ({isIntersecting: true, target: image.parentElement})));
  await new Promise(setImmediate);
  assert.deepEqual(requests, ['/photo/success']);
  images[0].onload();
  await new Promise(setImmediate);
  assert.equal(images[0].hidden, false);
  assert.deepEqual(requests, ['/photo/success', '/photo/failure']);
  images[1].onerror();
  await new Promise(setImmediate);
  assert.equal(images[1].hidden, true);
  assert.equal(observer.observed.size, 0);
});
