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
      if (reads === 1) return {value: encoder.encode('event: status\ndata: {"text":"找到参考资料","sources":[{"title":"官方攻略","url":"https://example.com/guide"},{"title":"危险链接","url":"javascript:alert(1)"}]}\n\nevent: token\ndata: {"text":"## 隐藏的原始标记 **","id":"one"}\n\n'), done: false};
      if (reads === 2) {
        await gate;
        const frame = success ? 'event: done\ndata: {"answer":"## 完整行程\\n**西湖**","message_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n\n'
          : 'event: error\ndata: {"text":"失败"}\n\n';
        return {value: encoder.encode(frame), done: false};
      }
      return {done: true};
    }};
    const pageDocument = {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []};
    vm.runInNewContext(appSource, {
      document: pageDocument, renderMarkdown, TextDecoder, setInterval, clearInterval,
      localStorage: {getItem: () => 'test', setItem() {}},
      Option: class {},
      fetch: async url => url === '/chat/stream' ? {ok: true, body: {getReader: () => reader}}
        : {ok: true, json: async () => ({sessions: []})},
    });
    const completion = elements.form.handlers.submit({preventDefault() {}});
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(elements.messages.textContent.includes('已用时 0 秒'));
    assert.ok(nodes(elements.messages).find(node => node.className === 'progress').open);
    assert.ok(!elements.messages.textContent.includes('隐藏的原始标记'));
    assert.equal(elements.send.disabled, true);
    assert.ok(elements.messages.textContent.includes('官方攻略'));
    assert.equal(nodes(elements.messages).filter(node => node.tagName === 'A').length, 1);
    release();
    await completion;
    assert.ok(!elements.messages.textContent.includes('隐藏的原始标记'));
    if (success) {
      assert.equal(nodes(elements.messages).filter(node => node.className === 'export-pdf').length, 1);
      assert.ok(nodes(elements.messages).some(node => node.tagName === 'H3' && node.textContent === '完整行程'));
      assert.ok(nodes(elements.messages).some(node => node.tagName === 'STRONG' && node.textContent === '西湖'));
      assert.equal(elements.input.value, '');
    } else {
      assert.equal(nodes(elements.messages).filter(node => node.className === 'export-pdf').length, 0);
      assert.ok(elements.messages.textContent.includes('本次回复未完成'));
      assert.equal(elements.input.value, '规划杭州');
    }
    assert.equal(elements.send.disabled, false);
    assert.ok(elements.messages.textContent.includes(success ? '已完成 · 已用时' : '已中断 · 已用时'));
  });
}

test('each export link keeps its answer and session, without review controls', () => {
  const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history']
    .map(id => [id, new Node('div')]));
  const context = vm.createContext({
    document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
    renderMarkdown, localStorage: {getItem: () => 'session-shanghai', setItem() {}},
  });
  vm.runInContext(appSource, context);
  vm.runInContext(`const oldBody = appendMessage('TravelMate', '上海 12月1日');
    addExport(oldBody, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    session = 'session-chongqing';
    const newBody = appendMessage('TravelMate', '重庆 12月2日');
    addExport(newBody, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
    addExport(appendMessage('TravelMate', '未完成'), null);`, context);
  const links = nodes(elements.messages).filter(node => node.className === 'export-pdf');
  assert.equal(links.length, 2);
  assert.equal(links[0].href, '/sessions/session-shanghai/answers/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/pdf');
  assert.equal(links[1].href, '/sessions/session-chongqing/answers/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/pdf');
  assert.ok(!html.includes('id="trip-panel"'));
  assert.ok(!html.includes('保存并校验'));
});
