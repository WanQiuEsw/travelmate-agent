import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../travelmate/budget_ui.py', import.meta.url), 'utf8').split('JS = r"""')[1].split('"""')[0];
const tick = () => new Promise(setImmediate);
const response = revision => ({ok: true, json: async () => ({revision})});

function setup({endpoint = '/budget', fetch = async () => response(1), storageError = false} = {}) {
  const timers = new Map(), events = {}, windowEvents = {}, documentEvents = {}, requests = [], storage = new Map(), downloads = [];
  let timerId = 0, reset;
  const input = value => ({value, validity: {valid: true, badInput: false}, style: {setProperty() {}}, matches: () => true});
  const amount = input('12.00'), limit = input('100.00'), check = {checked: true, matches: () => true};
  const row = {dataset: {category: '餐饮费用', order: '0', original: '12.00', originalIncluded: 'true'},
    querySelector: selector => selector.includes('number') ? amount : check};
  const body = {append() {}};
  row.parentElement = body;
  const node = () => ({style: {}, querySelector: () => ({})});
  const status = {}, filter = {value: ''}, sort = {value: 'desc'};
  const nodes = {'[data-budget-limit]': limit, '[data-budget-save-status]': status,
    '[data-budget-filter]': filter, '[data-budget-sort]': sort,
    '[data-budget-reset]': {addEventListener: (_, fn) => { reset = fn; }}};
  const workspace = {
    dataset: {endpoint, revision: '0', travelers: '2', storage: 'budget-test', originalLimit: '100.00'},
    querySelector: selector => nodes[selector] ?? (nodes[selector] = node()),
    querySelectorAll: selector => selector.includes('tr[') ? [row] : selector === '[data-ledger]' ? [body]
      : selector === 'input[type=number]' ? [amount, limit] : [],
    addEventListener: (name, fn) => { events[name] = fn; },
  };
  vm.runInNewContext(source, {
    document: {querySelector: () => workspace, addEventListener: (name, fn) => { documentEvents[name] = fn; }},
    window: {addEventListener: (name, fn) => { windowEvents[name] = fn; }, location: {assign: url => downloads.push(url)}},
    localStorage: {getItem: key => storage.get(key), setItem(key, value) {
      if (storageError) throw new Error('storage unavailable');
      storage.set(key, value);
    }},
    fetch: async (url, options) => { requests.push(JSON.parse(options.body)); return fetch(url, options); },
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
  });
  return {amount, limit, check, status, requests, storage, downloads,
    edit(value) { amount.value = value; events.input({target: amount}); },
    change() { events.change({target: check}); },
    reset: () => reset(),
    online: () => windowEvents.online(),
    unsaved() { let blocked = false; windowEvents.beforeunload({preventDefault() { blocked = true; }}); return blocked; },
    async runTimers() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); await tick(); },
    async download() {
      let blocked = false;
      await documentEvents.click({target: {closest: () => ({href: '/guide/pdf'})}, preventDefault() { blocked = true; }});
      return blocked;
    },
  };
}

test('amount and limit changes autosave after typing stops, without a save button', async () => {
  const page = setup();
  page.edit('2'); page.edit('25.50');
  page.limit.value = '200.00';
  assert.equal(page.requests.length, 0);
  await page.runTimers();
  assert.equal(page.requests.length, 1);
  assert.equal(page.requests[0].items[0].amount_cents, 2550);
  assert.equal(page.requests[0].limit_cents, 20000);
  assert.equal(page.unsaved(), false);
  assert.match(page.status.textContent, /已自动保存/);
});

test('edits during a pending request stay editable and use the next revision', async () => {
  let finish;
  const page = setup({fetch: () => new Promise(resolve => { finish = resolve; })});
  page.edit('20.00'); await page.runTimers();
  const first = finish;
  page.edit('30.00'); page.check.checked = false; page.change();
  await page.runTimers();
  assert.equal(page.requests.length, 1);
  assert.notEqual(page.amount.disabled, true);
  first(response(1)); await tick();
  assert.equal(page.requests.length, 2);
  assert.equal(page.requests[1].revision, 1);
  assert.equal(page.requests[1].items[0].amount_cents, 3000);
  assert.equal(page.requests[1].items[0].included, false);
  assert.equal(page.unsaved(), true);
  finish(response(2)); await tick();
  assert.equal(page.unsaved(), false);
});

test('invalid amounts and incomplete numeric input stay unsaved and block export', async () => {
  const page = setup();
  page.edit('1.234'); await page.runTimers();
  assert.equal(page.requests.length, 0);
  assert.equal(await page.download(), true);
  assert.equal(page.downloads.length, 0);
  assert.match(page.status.textContent, /最多两位小数/);
  page.edit(''); page.amount.validity.badInput = true; await page.runTimers();
  assert.equal(page.requests.length, 0);
  assert.equal(page.unsaved(), true);
});

test('network failure preserves input and reconnect automatically retries', async () => {
  let failed = true;
  const page = setup({fetch: async () => { if (failed) throw new Error('offline'); return response(1); }});
  page.edit('42.00'); await page.runTimers();
  assert.equal(page.amount.value, '42.00');
  assert.equal(page.unsaved(), true);
  assert.match(page.status.textContent, /尚未保存/);
  failed = false; page.online(); await tick();
  assert.equal(page.requests[1].revision, 0);
  assert.equal(page.unsaved(), false);
});

test('checkbox and reset autosave locally, and local storage errors keep unsaved warning', async () => {
  const page = setup({endpoint: ''});
  page.check.checked = false; page.change(); await page.runTimers();
  assert.equal(JSON.parse(page.storage.get('budget-test')).items[0].included, false);
  page.edit('99.00'); page.reset(); await page.runTimers();
  assert.equal(JSON.parse(page.storage.get('budget-test')).items[0].amount_cents, 1200);
  assert.equal(JSON.parse(page.storage.get('budget-test')).items[0].included, true);
  assert.equal(page.unsaved(), false);
  const unavailable = setup({endpoint: '', storageError: true});
  unavailable.edit('42.00'); await unavailable.runTimers();
  assert.equal(unavailable.unsaved(), true);
});

test('export flushes pending autosave and conflicts keep edits without downloading stale values', async () => {
  const page = setup();
  page.edit('88.00');
  assert.equal(await page.download(), true);
  assert.equal(page.requests[0].items[0].amount_cents, 8800);
  assert.deepEqual(page.downloads, ['/guide/pdf']);
  const conflict = setup({fetch: async () => ({ok: false, json: async () => ({detail: '预算已在其他页面更新，请刷新后重新编辑'})})});
  conflict.edit('90.00'); await conflict.runTimers();
  await conflict.download();
  assert.match(conflict.status.textContent, /其他页面/);
  assert.equal(conflict.unsaved(), true);
  assert.equal(conflict.downloads.length, 0);
});
