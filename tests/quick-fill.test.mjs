import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';
const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const source = html.match(/<script id="quick-fill-script">([\s\S]*?)<\/script>/)[1];
function setup() {
  const elements = Object.fromEntries(['trip-form', 'input', 'quick-fill', 'send', 'preset', 'status'].map(id => [id, {
    handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; },
    focus() { this.focused = true; }, dispatchEvent() {},
  }]));
  elements['trip-form'].reportValidity = () => true;
  elements['trip-form'].elements = Object.fromEntries(Object.entries({people: '2', date: '2026-12-10', origin: ' 福建厦门 ', destination: '北京', budget: '3000', days: '3'}).map(([key, value]) => [key, {value}]));
  vm.runInNewContext(source, {document: {querySelector: id => elements[id.slice(1)]}, Event});
  return elements;
}
test('preset fills an editable bracketed draft without submitting', () => {
  const e = setup();
  e.preset.handlers.click();
  assert.equal(e.input.value, '我们【2人】准备【2026年12月10日】从【福建厦门】出发到【北京】玩【3天】，总预算【3000元】，请帮我们规划行程。');
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
  e['trip-form'].elements.origin.value = '   ';
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
