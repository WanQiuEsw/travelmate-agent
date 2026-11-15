import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';

const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const source = html.match(/<script id="homepage-script">([\s\S]*?)<\/script>/)[1];

function setup() {
  const element = (value = '') => ({
    value, handlers: {}, children: [], dataset: {},
    addEventListener(name, handler) { this.handlers[name] = handler; },
    append(child) { this.children.push(child); },
    setAttribute(name, value) { this[name] = value; },
    setCustomValidity(message) { this.validationMessage = message; },
    focus() { this.focused = true; }, scrollIntoView() {},
  });
  const fields = Object.fromEntries(Object.entries({origin: '', destination: '', days: '3', budget: '3000', preference: '自然风光', people: '2'}).map(([key, value]) => [key, element(value)]));
  fields.budget.selectedOptions = [{textContent: '¥2000–3000'}];
  const elements = Object.fromEntries(['home-planner', 'planner-status', 'home-generate', 'send', 'random-destination', 'form'].map(id => [id, element()]));
  elements['home-planner'].elements = fields;
  elements['home-planner'].reportValidity = () => !fields.destination.validationMessage;
  elements.form.submissions = [];
  const tripInput = element();
  elements.form.requestSubmit = () => elements.form.submissions.push(tripInput.value);
  const cards = [...html.matchAll(/data-destination="([^"]+)" data-preference="([^"]+)"/g)].map(([, destination, preference]) => Object.assign(element(), {dataset: {destination, preference}}));
  let sync;
  vm.runInNewContext(source, {
    document: {querySelector: id => elements[id.slice(1)], querySelectorAll: () => cards, createElement: () => element()},
    MutationObserver: class { constructor(callback) { sync = callback; } observe() {} },
    tripInput, matchMedia: () => ({matches: true}),
    fillTripDraft(text) { if (elements.send.disabled || tripInput.disabled) return false; tripInput.value = text; return true; },
  });
  return {fields, elements, cards, tripInput, sync,
    submit: () => elements['home-planner'].handlers.submit({preventDefault() {}})};
}

test('planner initializes real select options and sends one complete request with an explicit total budget', () => {
  const {fields, elements, submit} = setup();
  assert.equal(fields.origin.value, '上海');
  assert.equal(fields.destination.value, '杭州');
  assert.ok(fields.destination.children.some(option => option.value === '三亚'));
  fields.people.value = '4'; fields.budget.value = '5000';
  fields.budget.selectedOptions = [{textContent: '¥3000–5000'}];
  fields.days.value = '5'; fields.preference.value = '美食寻味';
  submit();
  assert.equal(elements.form.submissions.length, 1);
  assert.match(elements.form.submissions[0], /4人.*上海.*杭州.*5天/);
  assert.match(elements.form.submissions[0], /全员总预算【20000元】/);
  assert.match(elements.form.submissions[0], /美食寻味/);
  assert.match(elements.form.submissions[0], /出发日期待定/);
});

test('recommendation cards choose destination and preference without sending or replacing the draft', () => {
  const {fields, elements, cards, tripInput} = setup();
  assert.equal(cards.length, 4);
  tripInput.value = '已有草稿';
  for (const card of cards) {
    card.handlers.click();
    assert.equal(fields.destination.value, card.dataset.destination);
    assert.equal(fields.preference.value, card.dataset.preference);
    assert.equal(card['aria-pressed'], 'true');
    assert.equal(cards.filter(item => item['aria-pressed'] === 'true').length, 1);
    assert.equal(elements.form.submissions.length, 0);
    assert.equal(tripInput.value, '已有草稿');
  }
  tripInput.disabled = true;
  cards[0].handlers.click();
  assert.equal(fields.destination.value, '大理');
});

test('random destination excludes origin and current choice and retains other preferences', () => {
  const {fields, elements} = setup();
  fields.preference.value = '美食寻味';
  for (let i = 0; i < 30; i++) {
    const previous = fields.destination.value;
    elements['random-destination'].handlers.click();
    assert.notEqual(fields.destination.value, fields.origin.value);
    assert.notEqual(fields.destination.value, previous);
    assert.equal(fields.preference.value, '美食寻味');
  }
  assert.equal(elements.form.submissions.length, 0);
});

test('same-city validation can recover and unavailable generation never overwrites a draft', () => {
  const {fields, elements, tripInput, submit, sync} = setup();
  fields.destination.value = fields.origin.value;
  submit();
  assert.equal(elements.form.submissions.length, 0);
  assert.ok(fields.destination.validationMessage);
  fields.destination.value = '杭州';
  elements['home-planner'].handlers.change();
  assert.equal(fields.destination.validationMessage, '');
  tripInput.value = '保留草稿'; elements.send.disabled = true; sync();
  assert.equal(elements['home-generate'].disabled, true);
  submit();
  assert.equal(tripInput.value, '保留草稿');
  assert.equal(elements.form.submissions.length, 0);
  elements.send.disabled = false; sync(); submit();
  assert.equal(elements['home-generate'].disabled, false);
  assert.equal(elements.form.submissions.length, 1);
});
