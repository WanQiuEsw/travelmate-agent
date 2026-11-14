import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../travelmate/back-to-top.js', import.meta.url), 'utf8');

function setup({chat = false, reduced = false} = {}) {
  const events = {}, clicks = {}, children = [], observers = [];
  const container = () => ({scrollTop: 0, scrollTo(options) { this.lastScroll = options; }});
  const page = container(), main = container();
  const conversation = {...container(), getBoundingClientRect: () => ({bottom: 600})};
  const messages = {children: []};
  const button = {style: {setProperty() {}}, setAttribute() {}, addEventListener: (name, fn) => { clicks[name] = fn; }};
  const document = {
    head: {append() {}}, body: {append: el => children.push(el)}, scrollingElement: page,
    createElement: tag => tag === 'button' ? button : {},
    querySelector: selector => ({
      '.back-to-top': children[0], '#messages': chat ? messages : null,
      '.conversation': chat ? conversation : null, main,
    })[selector],
    addEventListener: (name, fn) => { events[name] = fn; },
  };
  const context = vm.createContext({document, window: {addEventListener(name, fn) { if (name === 'DOMContentLoaded') events.ready = fn; }},
    matchMedia: () => ({matches: reduced}),
    MutationObserver: class { constructor(fn) { observers.push(fn); } observe() {} },
    ResizeObserver: class { observe() {} },
  });
  vm.runInContext(source, context);
  events.ready();
  return {button, page, main, conversation, messages, children, events, clicks, observers, context};
}

test('only appears after scrolling and returns the document smoothly to the top', () => {
  const ui = setup();
  assert.equal(ui.button.hidden, true);
  ui.page.scrollTop = 500;
  ui.events.scroll();
  assert.equal(ui.button.hidden, false);
  ui.clicks.click();
  assert.equal(ui.page.lastScroll.top, 0);
  assert.equal(ui.page.lastScroll.behavior, 'smooth');
  ui.page.scrollTop = 0;
  ui.events.scroll();
  assert.equal(ui.button.hidden, true);
});

test('switches from the homepage scroller to conversation and back', () => {
  const ui = setup({chat: true});
  ui.main.scrollTop = 400;
  ui.events.scroll();
  ui.clicks.click();
  assert.equal(ui.main.lastScroll.top, 0);
  ui.messages.children.push({});
  ui.observers[0]();
  assert.equal(ui.button.hidden, true);
  ui.conversation.scrollTop = 800;
  ui.events.scroll();
  ui.clicks.click();
  assert.equal(ui.conversation.lastScroll.top, 0);
  assert.equal(ui.page.lastScroll, undefined);
  ui.main.scrollTop = 0;
  ui.messages.children.length = 0;
  ui.observers[0]();
  assert.equal(ui.button.hidden, true);
});

test('respects reduced motion and avoids duplicate buttons in library details', () => {
  const ui = setup({reduced: true});
  ui.clicks.click();
  assert.equal(ui.page.lastScroll.behavior, 'instant');
  vm.runInContext(source, ui.context);
  ui.events.ready();
  assert.equal(ui.children.length, 1);
});
