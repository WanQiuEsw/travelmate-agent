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
  querySelectorAll(selector) {
    const descendants = this.children.flatMap(nodes);
    if (selector === '[aria-current]') return descendants.filter(node => node['aria-current'] !== undefined);
    if (selector === '.history-tools span') return descendants.filter(node => node.tagName === 'SPAN');
    return [];
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
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

test('Enter sends, Ctrl/Command+Enter inserts a newline, and IME confirmation stays untouched', () => {
  const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history']
    .map(id => [id, new Node('div')]));
  let submissions = 0;
  elements.form.requestSubmit = () => { submissions++; };
  const input = elements.input;
  input.setRangeText = (text, start, end) => {
    input.value = input.value.slice(0, start) + text + input.value.slice(end);
    input.selectionStart = input.selectionEnd = start + text.length;
  };
  input.dispatchEvent = () => {};
  vm.runInNewContext(appSource, {
    document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
    renderMarkdown, Event, localStorage: {getItem: () => 'test', setItem() {}},
  });
  function press(overrides = {}) {
    let prevented = false;
    input.handlers.keydown({key: 'Enter', preventDefault() { prevented = true; }, ...overrides});
    return prevented;
  }
  assert.equal(press(), true);
  assert.equal(submissions, 1);
  for (const modifier of ['ctrlKey', 'metaKey']) {
    input.value = 'before selected after';
    input.selectionStart = 7;
    input.selectionEnd = 15;
    assert.equal(press({[modifier]: true}), true);
    assert.equal(input.value, 'before \n after');
    assert.equal(input.selectionStart, 8);
    assert.equal(submissions, 1);
  }
  for (const event of [{isComposing: true}, {keyCode: 229}, {shiftKey: true}, {key: 'a'}]) {
    assert.equal(press(event), false);
  }
  assert.equal(submissions, 1);
});

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
    assert.equal(nodes(elements.messages).find(node => node.className === 'progress').open, !success);
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

test('sidebar loads a conversation and new chat clears messages and selection', async () => {
  const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history', 'sidebar']
    .map(id => [id, new Node('div')]));
  const context = vm.createContext({
    document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
    renderMarkdown, crypto: {randomUUID: () => 'new-session'},
    localStorage: {getItem: () => 'old-session', setItem() {}},
    fetch: async url => ({ok: true, json: async () => url === '/sessions'
      ? {sessions: [{title: '<旅行计划>', session_id: 'old-session'}]}
      : {messages: [{role: 'user', content: '去杭州'}, {role: 'assistant', content: '好的'}]}}),
  });
  vm.runInContext(appSource, context);
  await vm.runInContext('refreshSessions()', context);
  const button = nodes(elements.history).find(node => node.className === 'history-open');
  assert.equal(button.textContent, '<旅行计划>');
  assert.equal(button['aria-current'], 'true');
  await button.handlers.click();
  assert.equal(elements.messages.children[0].className, 'message user');
  assert.equal(elements.messages.children[1].className, 'message');
  elements.input.value = '未发送';
  elements.new.handlers.click();
  assert.equal(elements.messages.children.length, 0);
  assert.equal(elements.input.value, '');
  assert.ok(nodes(elements.history).filter(node => node.className === 'history-open').every(node => node['aria-current'] === 'false'));
  assert.equal(elements.sidebar.open, false);
});


test('closing advice and later headings stay outside collapsed references', () => {
  for (const ending of ['如需把交通改成飞机，告诉我即可调整。', '## 温馨提示\n出行前核实开放时间。']) {
    const root = new Node('div');
    renderMarkdown(root, '正文\n## 参考来源\n- 重庆旅行知识库\n- 高德地图\n\n' + ending);
    const details = nodes(root).find(node => node.tagName === 'DETAILS');
    assert.ok(details.textContent.includes('重庆旅行知识库'));
    assert.ok(!details.textContent.includes('告诉我'));
    assert.ok(!details.textContent.includes('温馨提示'));
    assert.ok(nodes(root).some(node => node.tagName === 'P' && (node.textContent.includes('告诉我') || node.textContent.includes('出行前'))));
  }
});

test('pinning persists selection on failure and deletion clears the current conversation', async () => {
  const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history', 'sidebar']
    .map(id => [id, new Node('div')]));
  let sessions = [{session_id: 'old-session', title: '重庆'}, {session_id: 'other', title: '杭州', pinned: false}];
  const calls = [];
  let fail = false;
  let approve = true;
  const context = vm.createContext({
    document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
    renderMarkdown, crypto: {randomUUID: () => 'new-session'}, confirm: () => approve,
    localStorage: {getItem: () => 'old-session', setItem() {}},
    fetch: async (url, options) => {
      if (url === '/sessions') return {ok: true, json: async () => ({sessions})};
      const data = JSON.parse(options.body); calls.push({url, data});
      if (fail) return {ok: false};
      if (url === '/sessions/pin') sessions = sessions.map(item => data.session_ids.includes(item.session_id) ? {...item, pinned: data.pinned} : item);
      if (url === '/sessions/delete') sessions = sessions.filter(item => !data.session_ids.includes(item.session_id));
      return {ok: true};
    },
  });
  vm.runInContext(appSource, context);
  await vm.runInContext('refreshSessions()', context);
  await vm.runInContext("selectedSessions.add('old-session'); selectedSessions.add('other'); manageSessions('/sessions/pin', [...selectedSessions], true)", context);
  assert.equal(calls[0].data.session_ids.length, 2);
  assert.equal(sessions[0].pinned, true);
  assert.ok(elements.history.textContent.includes('取消置顶'));
  assert.ok(!elements.history.textContent.includes('移动所选'));
  const actions = nodes(elements.history).find(node => node.className === 'history-actions');
  assert.equal(actions.children[1].disabled, true);
  assert.equal(elements.history.children[0].children[0].textContent, '全选 / 取消');
  fail = true;
  await vm.runInContext("selectedSessions.add('old-session'); manageSessions('/sessions/delete', [...selectedSessions])", context);
  assert.equal(vm.runInContext('selectedSessions.size', context), 1);
  assert.equal(sessions.length, 2);
  fail = false; approve = false;
  await vm.runInContext("manageSessions('/sessions/delete', [...selectedSessions])", context);
  assert.equal(sessions.length, 2);
  approve = true;
  elements.messages.append(new Node('p', '旧对话'));
  await vm.runInContext("manageSessions('/sessions/delete', [...selectedSessions])", context);
  assert.equal(sessions.length, 1);
  assert.equal(vm.runInContext('session', context), 'new-session');
  assert.equal(elements.messages.children.length, 0);
});

test('progress hides intermediate errors, deduplicates updates, and has no numbered steps', () => {
  const elements = Object.fromEntries(['form', 'input', 'messages', 'status', 'send', 'new', 'history']
    .map(id => [id, new Node('div')]));
  const context = vm.createContext({
    document: {...document, querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => []},
    renderMarkdown, setInterval, clearInterval,
    localStorage: {getItem: () => 'test', setItem() {}},
  });
  vm.runInContext(appSource, context);
  vm.runInContext(`
    const userBody = appendMessage('你', '旅行需求', true);
    const replyBody = appendMessage('TravelMate', '');
    const progress = createProgress(replyBody);
    progress.add('正在通过高德查询…');
    progress.add('正在通过高德查询…');
    progress.add('通过高德查询失败，相关信息尚未核实。');
    progress.finish(true);
  `, context);
  const user = elements.messages.children[0];
  assert.equal(user.children.length, 1);
  assert.equal(user.textContent, '旅行需求');
  assert.equal(user['aria-label'], '你的消息');
  const progress = nodes(elements.messages).find(node => node.className === 'progress');
  assert.equal(progress.open, false);
  assert.equal(nodes(progress).filter(node => node.tagName === 'OL').length, 0);
  assert.equal(nodes(progress).filter(node => node.tagName === 'LI' && node.textContent === '正在通过高德查询…').length, 1);
  assert.ok(!progress.textContent.includes('失败'));
});
