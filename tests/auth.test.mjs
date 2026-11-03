import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import vm from 'node:vm';

const authSource = (await readFile(new URL('../travelmate/auth.js', import.meta.url), 'utf8')).replaceAll('export ', '');

test('cookie requests attach the write header and expired sessions go to login', async () => {
  const calls = [], redirects = [];
  const elements = {'#account-name': {}, '#account-quota': {}};
  const context = vm.createContext({Headers, document: {querySelector: id => elements[id]}, window: {
    location: {replace: path => redirects.push(path)},
    fetch: async (url, options) => {
      calls.push({url, options});
      return {ok: url !== '/expired', status: url === '/expired' ? 401 : 200,
        json: async () => ({user: {display_name: '<旅行者>'}, quota: {remaining: 3, limit: 20}})};
    }
  }});
  vm.runInContext(authSource, context);
  await vm.runInContext('refreshAccount()', context);
  assert.equal(elements['#account-name'].textContent, '<旅行者>');
  assert.match(elements['#account-quota'].textContent, /3 \/ 20/);
  await vm.runInContext("apiFetch('/chat/stream', {method: 'POST', headers: {'Content-Type': 'application/json'}})", context);
  assert.equal(calls[1].options.headers.get('X-TravelMate-Request'), '1');
  assert.equal(calls[1].options.headers.get('Content-Type'), 'application/json');
  assert.equal(calls[1].options.credentials, 'same-origin');
  await vm.runInContext("apiFetch('/expired')", context);
  assert.deepEqual(redirects, ['/login']);
  await vm.runInContext('logout()', context);
  assert.equal(calls.at(-1).url, '/auth/logout');
  assert.deepEqual(redirects, ['/login', '/login']);
});

const loginHtml = await readFile(new URL('../travelmate/login.html', import.meta.url), 'utf8');
const loginSource = loginHtml.match(/<script type="module">([\s\S]*?)<\/script>/)[1];

test('invitation registration sends credentials, surfaces errors, and then opens chat', async () => {
  const elements = Object.fromEntries(['account-form', 'submit', 'toggle', 'error', 'description'].map(id => [id, {
    handlers: {}, addEventListener(event, callback) { this.handlers[event] = callback; }
  }]));
  const fields = elements['account-form'].elements = Object.fromEntries(Object.entries({username: ' Alice ', password: 'test-password-12345', display_name: '旅行者', invite_code: ' invitation '}).map(([name, value]) => [name, {value}]));
  const labels = [{hidden: true}, {hidden: true}], calls = [], redirects = [];
  let ok = false;
  const context = vm.createContext({document: {querySelector: id => elements[id.slice(1)], querySelectorAll: () => labels},
    window: {location: {replace: url => redirects.push(url)}}, fetch: async (url, options) => {
      calls.push({url, options});
      return {ok, json: async () => ({detail: '邀请码无效、已使用或已过期'})};
    }
  });
  vm.runInContext(loginSource, context);
  elements.toggle.handlers.click();
  assert.ok(labels.every(label => !label.hidden));
  assert.equal(fields.invite_code.required, true);
  assert.equal(fields.password.autocomplete, 'new-password');
  await elements['account-form'].handlers.submit({preventDefault() {}});
  assert.match(elements.error.textContent, /邀请码/);
  assert.equal(calls[0].url, '/auth/register');
  assert.equal(calls[0].options.headers['X-TravelMate-Request'], '1');
  assert.deepEqual(JSON.parse(calls[0].options.body), {username: 'Alice', password: 'test-password-12345', display_name: '旅行者', invite_code: 'invitation'});
  assert.equal(elements.submit.disabled, false);
  ok = true;
  await elements['account-form'].handlers.submit({preventDefault() {}});
  assert.deepEqual(redirects, ['/']);
  elements.toggle.handlers.click();
  assert.equal(fields.invite_code.required, false);
  assert.equal(fields.password.autocomplete, 'current-password');
  await elements['account-form'].handlers.submit({preventDefault() {}});
  const login = calls.findLast(call => call.url === '/auth/login');
  assert.deepEqual(Object.keys(JSON.parse(login.options.body)), ['username', 'password']);
  assert.equal(calls.at(-1).url, '/auth/me');
});

test('login shows useful network and non-JSON errors and avoids a cookie redirect loop', async () => {
  const elements = Object.fromEntries(['account-form', 'submit', 'toggle', 'error', 'description'].map(id => [id, {
    handlers: {}, addEventListener(event, callback) { this.handlers[event] = callback; }
  }]));
  elements['account-form'].elements = {username: {value: 'alice'}, password: {value: 'test-password-12345'}};
  let mode = 'network';
  const redirects = [];
  const context = vm.createContext({TypeError, document: {querySelector: id => elements[id.slice(1)]},
    window: {location: {replace: url => redirects.push(url)}}, fetch: async url => {
      if (mode === 'network') throw new TypeError('Failed to fetch');
      if (mode === 'server') return {ok: false, status: 502, json: async () => {throw new SyntaxError('not JSON');}};
      return {ok: url !== '/auth/me', status: url === '/auth/me' ? 401 : 200};
    }
  });
  vm.runInContext(loginSource, context);
  const submit = () => elements['account-form'].handlers.submit({preventDefault() {}});
  await submit();
  assert.match(elements.error.textContent, /无法连接登录服务/);
  assert.equal(elements.submit.disabled, false);
  mode = 'server';
  await submit();
  assert.match(elements.error.textContent, /HTTP 502/);
  mode = 'cookie';
  await submit();
  assert.match(elements.error.textContent, /登录状态未保存/);
  assert.deepEqual(redirects, []);
});
