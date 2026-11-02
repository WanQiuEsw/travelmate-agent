import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';
const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const source = html.match(/<script id="quick-fill-script">([\s\S]*?)<\/script>/)[1];
function setup(fetch = async () => ({ok: true, json: async () => ({results: [], notice: "以12306为准"})})) {
  const elements = Object.fromEntries(['trip-form', 'input', 'quick-fill', 'send', 'preset', 'status', 'train-search', 'train-results'].map(id => [id, {
    handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; },
    focus() { this.focused = true; }, dispatchEvent() {},
  }]));
  elements['trip-form'].reportValidity = () => true;
  elements['trip-form'].elements = Object.fromEntries(Object.entries({people: '2', date: '2026-12-10', origin: ' 福建厦门 ', destination: '北京', budget: '3000', days: '3', transport: '高铁'}).map(([key, value]) => [key, {value}]));
  vm.runInNewContext(source, {document: {querySelector: id => elements[id.slice(1)]}, Event, fetch});
  return elements;
}
test('preset fills an editable bracketed draft without submitting', () => {
  const e = setup();
  e.preset.handlers.click();
  assert.match(e.input.value, /我们【2人】准备【\d{4}年\d{1,2}月\d{1,2}日】从【厦门】出发到【北京】/);
  assert.match(e.input.value, /交通方式【高铁】/);
  assert.equal(e.input.focused, true);
});
test('quick fields generate a trimmed draft and close the panel', () => {
  const e = setup();
  let prevented = false;
  e['trip-form'].handlers.submit({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.match(e.input.value, /从【福建厦门】出发到【北京】玩【3天】，总预算【3000元】/);
  assert.equal(e['quick-fill'].open, false);
});
test('invalid fields and whitespace-only cities do not replace a draft', () => {
  const e = setup(); e.input.value = '保留我的草稿';
  e['trip-form'].reportValidity = () => false;
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
  e['trip-form'].reportValidity = () => true;
  e['trip-form'].elements.destination.value = '   ';
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
  assert.match(e.status.textContent, /请填写/);
});
test('busy requests keep the existing draft', () => {
  const e = setup(); e.input.value = '保留我的草稿'; e.send.disabled = true;
  e.preset.handlers.click();
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
});


test('origin and date are optional and transport is included without an invented date', () => {
  const e = setup();
  const fields = e['trip-form'].elements;
  fields.origin.value = ''; fields.date.value = ''; fields.transport.value = '飞机';
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.match(e.input.value, /出发地待定/);
  assert.match(e.input.value, /出发日期待定，按第几天规划/);
  assert.match(e.input.value, /交通方式【飞机】/);
  assert.ok(!e.input.value.includes('NaN'));
});

test('rail search skips non-rail modes and missing conditions', async () => {
  let calls = 0;
  const e = setup(async () => { calls++; });
  const fields = e['trip-form'].elements;
  fields.transport.value = '飞机';
  await e['train-search'].handlers.click();
  assert.match(e['train-results'].textContent, /请选择/);
  fields.transport.value = '高铁'; fields.date.value = '';
  await e['train-search'].handlers.click();
  assert.match(e['train-results'].textContent, /需要/);
  assert.equal(calls, 0);
});

test('rail search sends the chosen route, date and mode and safely displays seats', async () => {
  const e = setup(async (url, options) => {
    assert.equal(url, '/transport/trains');
    assert.deepEqual(JSON.parse(options.body), {origin: '福建厦门', destination: '北京', departure_date: '2026-12-10', transport: '高铁'});
    return {ok: true, json: async () => ({results: [{start_train_code: 'G123', from_station: '厦门北', to_station: '北京南', start_time: '08:00', arrive_time: '18:00', lishi: '10:00', prices: [{seat_name: '二等座', price: 600, num: '有'}]}], notice: '以12306为准'})};
  });
  await e['train-search'].handlers.click();
  assert.match(e['train-results'].textContent, /G123/);
  assert.match(e['train-results'].textContent, /二等座：600元/);
  assert.equal(e['train-search'].disabled, false);
});

test('rail search errors do not block trip drafting', async () => {
  const e = setup(async () => ({ok: true, json: async () => ({error: '服务未启动'})}));
  await e['train-search'].handlers.click();
  assert.equal(e['train-results'].textContent, '服务未启动');
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.match(e.input.value, /请帮我们规划行程/);
});
