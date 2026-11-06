import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';

const html = await readFile(new URL('../travelmate/index.html', import.meta.url), 'utf8');
const source = html.match(/<script id="voice-script">([\s\S]*?)<\/script>/)[1];

function element(extra = {}) {
  return {
    value: '', textContent: '', hidden: false, disabled: false, dataset: {}, handlers: {}, open: false,
    addEventListener(name, handler) { (this.handlers[name] ||= []).push(handler); },
    fire(name, event = {}) { for (const handler of this.handlers[name] || []) handler(event); },
    showModal() { this.open = true; },
    close() { this.open = false; this.fire('close'); },
    focus() {}, ...extra,
  };
}

function setup({status = 200, payload = {text: '想从厦门去鼓浪屿玩三天', corrections: [{from: '鼓浪与', to: '鼓浪屿'}], provider: 'openai'}, supports = true, media = true} = {}) {
  const clock = {now: 1_000_000};
  const ids = ['voice', 'voice-text', 'voice-status', 'voice-hint', 'voice-record', 'voice-stop',
    'voice-cancel', 'voice-fill', 'voice-open', 'voice-retry', 'voice-close', 'input', 'status'];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  elements['voice-text'].value = '';
  const requests = [];
  const filled = [];
  let stopped = 0;
  class FakeRecorder {
    constructor(stream, options) {
      this.stream = stream;
      this.mimeType = options?.mimeType || '';
      this.state = 'inactive';
      this.handlers = {};
      FakeRecorder.last = this;
    }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      this.handlers.dataavailable?.({data: new Blob(['a'.repeat(4096)], {type: 'audio/webm'})});
      this.handlers.stop?.({});
    }
  }
  FakeRecorder.isTypeSupported = type => supports && type === 'audio/webm;codecs=opus';
  const context = {
    document: {querySelector: selector => elements[selector.replace('#', '')] || element()},
    window: {MediaRecorder: FakeRecorder, location: {replace() {}}},
    navigator: media ? {mediaDevices: {getUserMedia: async () => ({getTracks: () => [{stop() { stopped += 1; }}]})}} : {},
    MediaRecorder: FakeRecorder,
    Blob, console,
    Date: {now: () => clock.now},
    setInterval: () => 1, clearInterval() {}, setTimeout: () => 1, clearTimeout() {},
    fillTripDraft: text => { filled.push(text); elements.input.value = text; return true; },
    fetch: async (url, options = {}) => {
      requests.push({url, options});
      return {ok: status >= 200 && status < 300, status, json: async () => payload};
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return {elements, requests, filled, clock, advance: ms => { clock.now += ms; }, stopped: () => stopped};
}

const settle = () => new Promise(resolve => setTimeout(resolve, 10));

test('scripted ids all exist in the page', () => {
  const scripts = [source,
    html.match(/<script type="module">([\s\S]*?)<\/script>/)[1]];
  const ids = new Set(scripts.flatMap(body => [...body.matchAll(/querySelector\('#([\w-]+)'\)/g)].map(m => m[1])));
  assert.ok(ids.size > 10);
  for (const id of ids) assert.match(html, new RegExp(`id="${id}"`), `missing #${id}`);
});

test('voice intake turns audio into text and never calls /chat by itself', async () => {
  const app = setup();
  app.elements['voice-open'].fire('click');
  assert.equal(app.elements.voice.open, true);
  app.elements['voice-record'].fire('click');
  await settle();
  assert.equal(app.elements['voice-record'].hidden, true);
  assert.equal(app.elements['voice-stop'].hidden, false);
  app.advance(3200);
  app.elements['voice-stop'].fire('click');
  await settle();
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0].url, '/asr');
  assert.equal(app.requests[0].options.method, 'POST');
  assert.equal(app.requests[0].options.headers['X-TravelMate-Request'], '1');
  assert.match(app.requests[0].options.headers['Content-Type'], /^audio\/webm/);
  assert.equal(app.elements['voice-text'].value, '想从厦门去鼓浪屿玩三天');
  assert.match(app.elements['voice-hint'].textContent, /鼓浪屿/);
  assert.equal(app.elements['voice-fill'].disabled, false);
  // 关键：语音层只回填，不触发对话
  assert.deepEqual(app.requests.map(item => item.url), ['/asr']);
  app.elements['voice-fill'].fire('click');
  assert.deepEqual(app.filled, ['想从厦门去鼓浪屿玩三天']);
  assert.equal(app.elements.voice.open, false);
  assert.equal(app.elements.input.value, '想从厦门去鼓浪屿玩三天');
  assert.deepEqual(app.requests.map(item => item.url), ['/asr']);
});

test('cancelled or too short recordings do not upload', async () => {
  const app = setup();
  app.elements['voice-open'].fire('click');
  app.elements['voice-record'].fire('click');
  await settle();
  app.elements['voice-cancel'].fire('click');
  await settle();
  assert.deepEqual(app.requests, []);
  assert.match(app.elements['voice-status'].textContent, /已取消/);

  const short = setup();
  short.elements['voice-record'].fire('click');
  await settle();
  short.elements['voice-stop'].fire('click');
  await settle();
  assert.deepEqual(short.requests, []);
  assert.match(short.elements['voice-status'].textContent, /录音太短/);
});

test('asr failures surface as text and keep the dialog usable', async () => {
  const app = setup({status: 503, payload: {detail: '未配置语音识别：在 .env 填写 ASR_API_KEY'}});
  app.elements['voice-record'].fire('click');
  await settle();
  app.advance(2000);
  app.elements['voice-stop'].fire('click');
  await settle();
  assert.match(app.elements['voice-status'].textContent, /ASR_API_KEY/);
  assert.equal(app.elements['voice-status'].dataset.tone, 'error');
  assert.equal(app.elements['voice-fill'].disabled, true);
});

test('browsers without recording support fall back to typing', async () => {
  const app = setup({media: false});
  app.elements['voice-record'].fire('click');
  await settle();
  assert.match(app.elements['voice-status'].textContent, /不支持录音/);
  assert.deepEqual(app.requests, []);
});
