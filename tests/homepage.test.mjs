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
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this[name] = value; },
    removeAttribute(name) { delete this[name]; },
    setCustomValidity(message) { this.validationMessage = message; },
    focus() { this.focused = true; }, select() { this.selected = true; }, scrollIntoView() {},
    contains(target) { return this === target || this.children.some(child => child.contains(target)); },
  });
  const fields = Object.fromEntries(Object.entries({origin: '', destination: '', date: '2026-12-10', days: '3', budget: '3000', preference: '放松散心', people: '2', budget_scope: 'per_person', budget_includes: '往返交通、住宿、餐饮、门票和市内交通', pace: '适中', transport: '不限', mobility: '', dietary: '', extra_preferences: '', budget_scope: 'per_person', budget_includes: '往返交通、住宿、餐饮、门票和市内交通', transport: '不限', pace: '适中', extra_preferences: '', mobility: '', dietary: ''}).map(([key, value]) => [key, element(value)]));
  fields.budget.selectedOptions = [{textContent: '¥2000–3000'}];
  const elements = Object.fromEntries(['home-planner', 'planner-status', 'home-generate', 'send', 'random-destination', 'form', 'home-route', 'home-swap', 'home-city-panel', 'home-city-results', 'home-city-tabs', 'home-city-recent', 'home-city-title', 'home-city-caption', 'home-budget-label'].map(id => [id, element()]));
  elements['home-city-panel'].hidden = true;
  elements['home-route'].append(fields.origin, fields.destination, elements['home-city-panel']);
  elements['home-city-panel'].append(elements['home-city-results'], elements['home-city-tabs'], elements['home-city-recent']);
  elements['home-planner'].elements = fields;
  elements['home-planner'].reportValidity = () => !fields.origin.validationMessage && !fields.destination.validationMessage && !fields.date.validationMessage;
  elements.form.submissions = [];
  const tripInput = element();
  elements.form.requestSubmit = () => elements.form.submissions.push(tripInput.value);
  const cards = [...html.matchAll(/data-destination="([^"]+)" data-preference="([^"]+)"/g)].map(([, destination, preference]) => Object.assign(element(), {dataset: {destination, preference}}));
  let sync;
  const documentHandlers = {};
  vm.runInNewContext(source, {
    document: {querySelector: id => elements[id.slice(1)], querySelectorAll: () => cards, createElement: () => element(), addEventListener: (name, handler) => { documentHandlers[name] = handler; }},
    MutationObserver: class { constructor(callback) { sync = callback; } observe() {} },
    tripInput, matchMedia: () => ({matches: true}),
    Date: class extends Date { constructor() { super('2026-11-15T04:00:00+08:00'); } },
    fillTripDraft(text) { if (elements.send.disabled || tripInput.disabled) return false; tripInput.value = text; return true; },
  });
  return {fields, elements, cards, tripInput, sync, documentHandlers,
    submit: () => elements['home-planner'].handlers.submit({preventDefault() {}})};
}

test('planner initializes editable cities and sends canonical route values with structured conditions', () => {
  const {fields, elements, submit} = setup();
  assert.equal(fields.origin.value, '上海');
  assert.equal(fields.destination.value, '杭州');
  assert.match(html, /<input id="home-destination"[^>]+role="combobox"/);
  fields.people.value = '4'; fields.budget.value = '5000';
  fields.budget.selectedOptions = [{textContent: '¥3000–5000'}];
  fields.days.value = '5'; fields.preference.value = '美食寻味';
  submit();
  assert.equal(elements.form.submissions.length, 1);
  assert.match(elements.form.submissions[0], /上海.*杭州.*5天.*4人/);
  const requirements = JSON.parse(elements.form.dataset.planningRequirements);
  assert.equal(requirements.origin, '上海'); assert.equal(requirements.destination, '杭州');
  assert.equal(requirements.budget, 5000); assert.equal(requirements.budget_scope, 'per_person');
  assert.equal(requirements.travelers, 4);
  assert.match(elements.form.submissions[0], /美食寻味/);
  assert.match(elements.form.submissions[0], /2026-12-10/);
  assert.doesNotMatch(elements.form.submissions[0], /日期待定/);
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
    assert.equal(fields.date.value, '2026-12-10');
    assert.equal(fields.people.value, '2');
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

test('departure date rejects the past and accepts today or an unspecified date', () => {
  const {fields, elements, submit} = setup();
  assert.equal(fields.date.min, '2026-11-15');
  for (const value of ['2026-11-14']) {
    fields.date.value = value; submit();
    assert.ok(fields.date.validationMessage);
    assert.equal(elements.form.submissions.length, 0);
  }
  fields.date.value = '2026-11-15'; fields.date.handlers.input();
  assert.equal(fields.date.validationMessage, '');
  submit();
  assert.equal(elements.form.submissions.length, 1);
  assert.match(elements.form.submissions[0], /2026-11-15/);
  fields.date.value = ''; fields.date.handlers.input(); submit();
  assert.equal(elements.form.submissions.length, 2);
  assert.equal(JSON.parse(elements.form.dataset.planningRequirements).start_date, null);
});

test('preferences describe general interests and all recommendations map to a supported preference', () => {
  const choices = html.match(/<select name="preference"[^>]*>([\s\S]*?)<\/select>/)[1];
  assert.match(choices, /美食寻味/);
  assert.match(choices, /名胜古迹/);
  assert.match(choices, /放松散心/);
  assert.doesNotMatch(choices, /海边|山野|古城/);
  for (const [, preference] of html.matchAll(/data-preference="([^"]+)"/g)) {
    assert.ok(choices.includes(`<option>${preference}</option>`), preference);
  }
});

test('city picker opens popular cities, searches Chinese, pinyin and initials, and closes after choosing', () => {
  const {fields, elements} = setup();
  const results = elements['home-city-results'];
  fields.destination.handlers.focus();
  assert.equal(fields.destination['aria-expanded'], 'true');
  assert.equal(fields.destination.selected, true);
  assert.equal(elements['home-city-panel'].hidden, false);
  assert.ok(results.children.some(option => option.children[0].textContent === '黄山'));
  for (const query of ['黄山', 'huang', 'HUANGSHAN', 'hs', 'huang shan', "huang'shan"]) {
    fields.destination.value = query; fields.destination.handlers.input();
    assert.deepEqual(results.children.map(option => option.children[0].textContent), ['黄山']);
    assert.equal(elements['home-city-tabs'].hidden, true);
  }
  results.children[0].handlers.click();
  assert.equal(fields.destination.value, '黄山');
  assert.equal(fields.destination['aria-expanded'], 'false');
  assert.equal(elements['home-city-panel'].hidden, true);
  assert.equal(elements.form.submissions.length, 0);
  fields.origin.handlers.focus();
  assert.equal(elements['home-city-title'].textContent, '选择出发地');
  assert.ok(elements['home-city-recent'].children.some(button => button.textContent === '黄山'));
});

test('letter groups filter by pinyin and keyboard navigation chooses a canonical city without submitting', () => {
  const {fields, elements} = setup();
  fields.destination.handlers.focus();
  elements['home-city-tabs'].children.find(tab => tab.textContent === 'G–L').handlers.click();
  let names = elements['home-city-results'].children.map(option => option.children[0].textContent);
  assert.ok(names.includes('黄山') && names.includes('杭州') && names.includes('丽江'));
  assert.ok(!names.includes('北京') && !names.includes('重庆'));
  assert.equal(elements['home-city-tabs'].children.find(tab => tab.textContent === 'G–L')['aria-pressed'], 'true');
  fields.destination.value = 'c'; fields.destination.handlers.input();
  const key = key => fields.destination.handlers.keydown({key, preventDefault() {}});
  key('ArrowUp');
  const options = elements['home-city-results'].children;
  const selected = options.find(option => option['aria-selected'] === 'true');
  assert.equal(fields.destination['aria-activedescendant'], selected.id);
  key('Enter');
  assert.equal(fields.destination.value, selected.children[0].textContent);
  assert.equal(elements.form.submissions.length, 0);
  assert.equal(elements['home-city-panel'].hidden, true);
});

test('empty search, IME, Escape, focus leaving and outside clicks are safe', () => {
  const {fields, elements, documentHandlers} = setup();
  fields.destination.handlers.focus();
  fields.destination.value = 'unknown'; fields.destination.handlers.input();
  assert.equal(elements['home-city-results'].children.length, 0);
  assert.match(elements['home-city-caption'].textContent, /没有匹配/);
  fields.destination.handlers.keydown({key: 'ArrowDown', preventDefault() {}});
  fields.destination.handlers.keydown({key: 'Enter', isComposing: true});
  assert.equal(elements['home-city-panel'].hidden, false);
  fields.destination.handlers.keydown({key: 'Escape', preventDefault() {}});
  assert.equal(elements['home-city-panel'].hidden, true);
  fields.destination.handlers.click();
  documentHandlers.pointerdown({target: fields.destination});
  assert.equal(elements['home-city-panel'].hidden, false);
  documentHandlers.pointerdown({target: elements['home-generate']});
  assert.equal(elements['home-city-panel'].hidden, true);
  fields.destination.handlers.click();
  elements['home-route'].handlers.focusout({relatedTarget: null});
  assert.equal(elements['home-city-panel'].hidden, true);
});

test('manual Chinese destinations work, invalid text cannot submit, and corrected pinyin resolves before sending', () => {
  const {fields, elements, submit} = setup();
  fields.destination.value = '景德镇'; fields.destination.handlers.focus(); fields.destination.handlers.input();
  assert.equal(elements['home-city-results'].children[0].children[0].textContent, '景德镇');
  submit();
  assert.match(elements.form.submissions[0], /景德镇/);
  for (const value of ['', 'unknown', '<script>', 'hs123']) {
    fields.destination.value = value; submit();
    assert.ok(fields.destination.validationMessage);
    assert.equal(elements.form.submissions.length, 1);
  }
  fields.origin.value = 'shanghai'; fields.destination.value = 'huangshan'; submit();
  assert.equal(fields.origin.value, '上海'); assert.equal(fields.destination.value, '黄山');
  assert.equal(elements.form.submissions.length, 2);
  assert.match(elements.form.submissions[1], /上海.*黄山/);
  fields.origin.value = '上海市'; fields.destination.value = '上海'; submit();
  assert.equal(elements.form.submissions.length, 2);
  assert.match(fields.destination.validationMessage, /不能相同/);
});

test('swapping retains date, budget, preference and draft and is blocked during generation', () => {
  const {fields, elements, tripInput} = setup();
  fields.destination.value = '黄山'; fields.preference.value = '自然风光'; tripInput.value = '保留草稿';
  elements['home-swap'].handlers.click();
  assert.equal(fields.origin.value, '黄山'); assert.equal(fields.destination.value, '上海');
  assert.equal(fields.date.value, '2026-12-10'); assert.equal(fields.budget.value, '3000');
  assert.equal(fields.preference.value, '自然风光'); assert.equal(tripInput.value, '保留草稿');
  assert.equal(elements.form.submissions.length, 0);
  tripInput.disabled = true; elements['home-swap'].handlers.click();
  assert.equal(fields.origin.value, '黄山'); assert.equal(fields.destination.value, '上海');
});


test('unknown date and explicit total budget are submitted as typed conditions', () => {
  const {fields, elements, submit} = setup();
  fields.date.value = ''; fields.budget_scope.value = 'total'; fields.mobility.value = '带老人，不爬山';
  submit();
  const request = JSON.parse(elements.form.dataset.planningRequirements);
  assert.equal(request.start_date, null);
  assert.equal(request.budget_scope, 'total');
  assert.equal(request.travelers, 2);
  assert.equal(request.days, 3);
  assert.equal(request.mobility, '带老人，不爬山');
  assert.equal(request.budget_currency, 'CNY');
});
