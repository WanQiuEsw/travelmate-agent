// Run with Node's standard library only: node --test tests/markdown.test.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';

// Minimal DOM stand-in records which nodes and attributes the renderer creates.
class Node {
  constructor(tag, text = '') {
    this.tagName = tag.toUpperCase(); this.text = text; this.children = [];
    this.handlers = {}; this.value = ''; this.classList = {add() {}, remove() {}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(event, handler) { this.handlers[event] = handler; }
  focus() {}
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
}
globalThis.document = {
  createElement: tag => new Node(tag),
  createTextNode: text => new Node('#text', text),
  createDocumentFragment: () => new Node('#fragment'),
};
const source = await readFile(new URL('../travelmate/markdown.js', import.meta.url), 'utf8');
const {renderMarkdown} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
function nodes(root) { return [root, ...root.children.flatMap(nodes)]; }

test('renders travel headings, lists, table, code and safe source links', () => {
  const root = new Node('div');
  renderMarkdown(root, '## 行程\n**西湖** 与 `预算`\n- 休息\n- 慢行\n\n| 日期 | 费用 |\n| --- | --- |\n| 一 | 600元 |\n\n[来源](https://example.com)\n```\n<code>\n```');
  const tags = nodes(root).map(node => node.tagName);
  for (const tag of ['H3', 'STRONG', 'UL', 'LI', 'TABLE', 'TH', 'TD', 'CODE', 'PRE', 'A']) assert.ok(tags.includes(tag));
  assert.equal(nodes(root).find(node => node.tagName === 'A').rel, 'noopener noreferrer');
  assert.ok(root.textContent.includes('<code>'));
});

test('does not create HTML or executable links from untrusted content', () => {
  const root = new Node('div');
  renderMarkdown(root, '<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[bad](javascript:alert)\n[bad](data:text/html,test)');
  assert.ok(root.textContent.includes('<script>'));
  assert.ok(!nodes(root).some(node => ['SCRIPT', 'IMG', 'A'].includes(node.tagName)));
  renderMarkdown(root, '新回复');
  assert.equal(root.textContent, '新回复');
});

test('sources are collapsed with safe readable links', () => {
  const root = new Node('div');
  renderMarkdown(root, '行程正文\n## 参考来源\n- [杭州攻略](https://example.com/guide)');
  const details = nodes(root).find(node => node.tagName === 'DETAILS');
  assert.ok(details);
  assert.ok(!details.open);
  assert.ok(details.textContent.includes('杭州攻略'));
  assert.equal(nodes(details).find(node => node.tagName === 'A').href, 'https://example.com/guide');
});

const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const appSource = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]
  .replace(/import \{renderMarkdown\} from '[^']+';/, '')
  .replace('  initialize();', '');

for (const success of [true, false]) {
  test(`hides raw streamed Markdown until completion (${success ? 'success' : 'failure'})`, async () => {
    const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history',
      'trip-panel', 'trip-data', 'trip-status', 'trip-confirm', 'trip-save', 'trip-pdf', 'trip-preview']
      .map(id => [id, new Node('div')]));
    elements.input.value = '规划杭州';
    elements.history.options = [];
    elements.history.add = () => {};
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const encoder = new TextEncoder();
    let reads = 0;
    const reader = {async read() {
      reads++;
      if (reads === 1) return {value: encoder.encode('event: token\ndata: {"text":"## 隐藏的原始标记 **","id":"one"}\n\n'), done: false};
      if (reads === 2) {
        await gate;
        const frame = success ? 'event: done\ndata: {"answer":"## 完整行程\\n**西湖**"}\n\n'
          : 'event: error\ndata: {"text":"失败"}\n\n';
        return {value: encoder.encode(frame), done: false};
      }
      return {done: true};
    }};
    const pageDocument = {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []};
    vm.runInNewContext(appSource, {
      document: pageDocument, renderMarkdown, TextDecoder,
      localStorage: {getItem: () => 'test', setItem() {}},
      Option: class {},
      fetch: async url => url === '/chat/stream' ? {ok: true, body: {getReader: () => reader}}
        : {ok: true, json: async () => ({sessions: []})},
    });
    const completion = elements.form.handlers.submit({preventDefault() {}});
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(elements.messages.textContent.includes('完成排版后'));
    assert.ok(!elements.messages.textContent.includes('隐藏的原始标记'));
    assert.equal(elements.send.disabled, true);
    release();
    await completion;
    assert.ok(!elements.messages.textContent.includes('隐藏的原始标记'));
    if (success) {
      assert.ok(nodes(elements.messages).some(node => node.tagName === 'H3' && node.textContent === '完整行程'));
      assert.ok(nodes(elements.messages).some(node => node.tagName === 'STRONG' && node.textContent === '西湖'));
      assert.equal(elements.input.value, '');
    } else {
      assert.ok(elements.messages.textContent.includes('本次回复未完成'));
      assert.equal(elements.input.value, '规划杭州');
    }
    assert.equal(elements.send.disabled, false);
  });
}

for (const mode of ['success', 'invalid-json', 'server-error', 'timeout']) {
  test(`trip save recovers controls (${mode})`, async () => {
    const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history',
      'trip-panel', 'trip-data', 'trip-status', 'trip-confirm', 'trip-save', 'trip-pdf', 'trip-preview']
      .map(id => [id, new Node('div')]));
    const plan = {days: [], other_cost: 100, cost_notes: '估算'};
    let calls = 0;
    const context = vm.createContext({
      document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
      renderMarkdown, TextDecoder, AbortController, setTimeout, clearTimeout,
      localStorage: {getItem: () => 'test', setItem() {}},
      fetch: async () => {
        calls++;
        if (mode === 'timeout') throw Object.assign(new Error(), {name: 'AbortError'});
        if (mode === 'server-error') return {ok: false, json: async () => ({detail: '正在生成回复，请稍后保存'})};
        return {ok: true, json: async () => ({status: 'review', total: 100, plan})};
      },
    });
    vm.runInContext(appSource, context);
    vm.runInContext(`displayTrip(${JSON.stringify({status: 'review', total: 100, plan})})`, context);
    if (mode === 'invalid-json') elements['trip-data'].value = '{bad';
    const original = elements['trip-data'].value;
    await elements['trip-save'].handlers.click();
    assert.equal(elements.send.disabled, false);
    assert.equal(elements['trip-save'].disabled, false);
    assert.equal(elements['trip-data'].disabled, false);
    assert.equal(elements['trip-data'].value, original);
    assert.equal(elements['trip-confirm'].disabled, mode === 'invalid-json');
    assert.equal(calls, mode === 'invalid-json' ? 0 : 1);
    if (mode === 'timeout') assert.ok(elements['trip-status'].textContent.includes('请求超时'));
    if (mode === 'server-error') assert.ok(elements['trip-status'].textContent.includes('正在生成回复'));
  });
}
