import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';
const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const source = html.match(/<script id="quick-fill-script">([\s\S]*?)<\/script>/)[1];
function setup(fetch = async () => ({ok: true, json: async () => ({results: [], notice: "以12306为准"})})) {
  const elements = Object.fromEntries(['trip-form', 'form', 'input', 'quick-fill', 'quick-fill-open', 'quick-fill-close', 'quick-fill-cancel', 'send', 'preset', 'status', 'train-search', 'train-results', 'trip-step-label', 'trip-progress', 'trip-back', 'trip-skip', 'trip-submit', 'trip-rail', 'trip-review'].map(id => [id, {
    handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; },
    focus() { this.focused = true; }, dispatchEvent() {},
  }]));
  const reportValidity = () => {
    const invalid = Object.values(elements['trip-form'].elements).find(field => !field.disabled && (field.validationMessage || (field.required && !field.value)));
    invalid?.focus();
    return !invalid;
  };
  elements['trip-form'].reportValidity = reportValidity;
  elements['trip-form'].checkFields = reportValidity;
  elements.form.submissions = [];
  elements.form.requestSubmit = () => { elements.form.submissions.push(elements.input.value); elements.send.disabled = true; };
  elements['quick-fill'].open = false;
  elements['quick-fill'].showModal = function () { this.open = true; };
  elements['quick-fill'].close = function () { this.open = false; };
  elements['trip-form'].elements = Object.fromEntries(Object.entries({people: '2', date: '2026-12-10', origin: ' 福建厦门 ', destination: '北京', budget: '3000', days: '3', transport: '高铁', budgetIncludes: '交通、住宿、餐饮、门票全部费用', mobility: '每天10000步以内'}).map(([key, value]) => [key, {value, focus() { this.focused = true; }, setCustomValidity(message) { this.validationMessage = message; }}]));
  const fields = elements['trip-form'].elements;
  for (const key of ['destination', 'days', 'people', 'budget', 'budgetIncludes', 'mobility']) fields[key].required = true;
  elements.steps = [['destination'], ['date'], ['days', 'people'], ['budget', 'budgetIncludes'], ['origin'], ['transport'], ['mobility'], []].map((keys, index) => ({
    dataset: {title: String(index), optional: [1, 4].includes(index) ? 'true' : undefined},
    hidden: index !== 0,
    set disabled(value) { this.isDisabled = value; keys.forEach(key => { fields[key].disabled = value; }); },
    get disabled() { return this.isDisabled; },
    querySelectorAll() { return keys.map(key => fields[key]); },
    querySelector(selector) { return selector === 'input, select' ? fields[keys[0]] : {focus() {}}; },
  }));
  elements.steps.forEach((step, i) => { step.disabled = i !== 0; });
  elements['trip-form'].querySelectorAll = () => elements.steps;
  vm.runInNewContext(source, {document: {querySelector: id => elements[id.slice(1)]}, Event, fetch});
  return elements;
}
function next(e) { e['trip-form'].handlers.submit({preventDefault() {}}); }
function finish(e) { for (let step = 0; step < 8; step++) next(e); }

test('wizard gates later steps and waits for final confirmation', () => {
  const e = setup(); e['quick-fill-open'].handlers.click();
  assert.equal(e.steps[0].hidden, false);
  assert.ok(e.steps.slice(1).every(step => step.hidden && step.disabled));
  assert.equal(e['trip-skip'].hidden, true);
  e['trip-form'].elements.destination.value = '  ';
  next(e);
  assert.equal(e.steps[0].hidden, false);
  e['trip-skip'].handlers.click();
  assert.equal(e.steps[0].hidden, false);
  e['trip-form'].elements.destination.value = '杭州';
  next(e);
  assert.equal(e.steps[1].hidden, false);
  assert.equal(e['trip-skip'].hidden, false);
  for (let step = 1; step < 7; step++) next(e);
  assert.equal(e.steps[7].hidden, false);
  assert.equal(e['trip-submit'].textContent, '确认并发送');
  assert.match(e['trip-review'].textContent, /目的地：杭州/);
  assert.equal(e.form.submissions.length, 0);
  next(e);
  assert.equal(e.form.submissions.length, 1);
});

test('skip clears optional answers and back preserves required selections', () => {
  const e = setup(); e['quick-fill-open'].handlers.click();
  next(e);
  e['trip-skip'].handlers.click();
  assert.equal(e['trip-form'].elements.date.value, '');
  next(e); next(e);
  assert.equal(e.steps[4].hidden, false);
  e['trip-skip'].handlers.click();
  assert.equal(e['trip-form'].elements.origin.value, '');
  next(e); next(e);
  assert.equal(e.steps[7].hidden, false);
  e['trip-back'].handlers.click();
  assert.equal(e['trip-form'].elements.mobility.value, '每天10000步以内');
  e['trip-form'].elements.mobility.value = '每天5000步以内';
  next(e);
  assert.match(e['trip-review'].textContent, /每天5000步以内/);
  next(e);
  assert.match(e.form.submissions[0], /出发地待定，出发日期待定/);
  assert.ok(!e.form.submissions[0].includes('2026年12月10日'));
});
test('preset fills an editable bracketed draft without submitting', () => {
  const e = setup();
  e.preset.handlers.click();
  assert.match(e.input.value, /我们【2人】准备【\d{4}年\d{1,2}月\d{1,2}日】从【厦门】出发到【北京】/);
  assert.match(e.input.value, /交通方式【高铁】/);
  assert.equal(e.input.focused, true);
});
test('quick fields close the dialog and submit a complete travel request once', () => {
  const e = setup();
  e['quick-fill-open'].handlers.click();
  assert.equal(e['quick-fill'].open, true);
  let prevented = false;
  e['trip-form'].handlers.submit({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  for (let step = 1; step < 8; step++) next(e);
  assert.match(e.input.value, /从【福建厦门】出发到【北京】玩【3天】，全员总预算【3000元】/);
  assert.equal(e['quick-fill'].open, false);
  assert.equal(e.form.submissions.length, 1);
  assert.match(e.form.submissions[0], /人民币（CNY）/);
  assert.match(e.form.submissions[0], /预算包含【交通、住宿、餐饮、门票全部费用】/);
  assert.match(e.form.submissions[0], /步数与行动限制【每天10000步以内】/);
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.form.submissions.length, 1);
});
test('invalid fields and whitespace-only cities do not replace a draft', () => {
  const e = setup(); e.input.value = '保留我的草稿';
  e['trip-form'].reportValidity = () => false;
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
  e['trip-form'].reportValidity = e['trip-form'].checkFields;
  e['trip-form'].elements.destination.value = '   ';
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
  assert.match(e['trip-form'].elements.destination.validationMessage, /填写/);
  assert.equal(e.form.submissions.length, 0);
});
test('busy requests keep the existing draft', () => {
  const e = setup(); e.input.value = '保留我的草稿'; e.send.disabled = true;
  e.preset.handlers.click();
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e.input.value, '保留我的草稿');
  e['quick-fill-open'].handlers.click();
  assert.equal(e['quick-fill'].open, false);
  assert.equal(e.form.submissions.length, 0);
});

test('cancel and close preserve the chat draft without sending', () => {
  const e = setup(); e.input.value = '尚未发送的想法';
  for (const button of ['quick-fill-cancel', 'quick-fill-close']) {
    e['quick-fill-open'].handlers.click();
    assert.equal(e['quick-fill'].open, true);
    e[button].handlers.click();
    assert.equal(e['quick-fill'].open, false);
    assert.equal(e.input.value, '尚未发送的想法');
  }
  assert.equal(e.form.submissions.length, 0);
});

test('blank mobility does not close the dialog or send', () => {
  const e = setup(); e['quick-fill-open'].handlers.click();
  for (let step = 0; step < 6; step++) next(e);
  e['trip-form'].elements.mobility.value = '  ';
  e['trip-form'].handlers.submit({preventDefault() {}});
  assert.equal(e['quick-fill'].open, true);
  assert.equal(e['trip-form'].elements.mobility.focused, true);
  assert.equal(e.form.submissions.length, 0);
});


test('origin and date are optional and transport is included without an invented date', () => {
  const e = setup();
  const fields = e['trip-form'].elements;
  fields.origin.value = ''; fields.date.value = ''; fields.transport.value = '飞机';
  finish(e);
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
    assert.equal(options.headers['X-TravelMate-Request'], '1');
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
  finish(e);
  assert.match(e.input.value, /请帮我们规划行程/);
});
