// Run with Node's standard library only: node --test tests/markdown.test.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';

// Minimal DOM stand-in records which nodes and attributes the renderer creates.
class Node {
  constructor(tag, text = '') { this.tagName = tag.toUpperCase(); this.text = text; this.children = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
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
