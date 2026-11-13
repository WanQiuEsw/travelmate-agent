"""Version-scoped preparation tasks persisted with the existing SQLite checkpoints."""
from hashlib import sha256


def initial_tasks(guide):
    return [{'id': f'seed-{i}', 'text': item['text'], 'done': False}
            for section in guide['sections'] if section['title'] == '行前准备'
            for i, item in enumerate(section['items'])]


def overlay(guide, saved=None):
    data = saved if saved is not None else {'revision': 0, 'items': initial_tasks(guide)}
    guide['preparation'] = data
    for section in guide['sections']:
        if section['title'] == '行前准备':
            section['items'] = [{'text': ('[x] ' if item['done'] else '[ ] ') + item['text']} for item in data['items']]
    sections = guide['sections']
    preparation = [s for s in sections if s['title'] == '行前准备']
    sections = [s for s in sections if s['title'] != '行前准备']
    index = next((i for i, s in enumerate(sections) if s['kind'] == 'day'), len(sections))
    guide['sections'] = sections[:index] + preparation + sections[index:]
    return guide


def panel(guide, text):
    data = guide.get('preparation') or {'revision': 0, 'items': initial_tasks(guide)}
    endpoint = guide.get('_preparation_url', '')
    key = sha256((guide['title'] + str(guide['version']) + guide.get('saved_at', '')).encode()).hexdigest()[:24]
    out = [f'<section class="card preparation" data-endpoint="{text(endpoint)}" data-revision="{data["revision"]}" data-storage="travelmate-preparation-{key}"><h2>行前准备</h2>',
           '<p class="prep-notice">' + ('清单按本次旅行和方案版本保存到账号，刷新后仍保留。' if endpoint else '离线清单仅保存在当前浏览器，不会自动同步到账号。') + '</p>',
           '<ul data-prep-list>']
    for item in data['items']:
        out.append(f'<li data-task-id="{text(item["id"])}"><label><input type="checkbox" {"checked" if item["done"] else ""}><span>{text(item["text"])}</span></label><button type="button" data-edit>修改</button><button type="button" data-delete>删除</button></li>')
    out.append('</ul><form data-prep-add><label>新增准备事项<input name="task" maxlength="500" required placeholder="例如：带上充电宝"></label><button type="submit">添加</button></form><p data-prep-status role="status" aria-live="polite"></p><button type="button" data-prep-retry hidden>重试保存</button><noscript>启用 JavaScript 后可编辑清单。</noscript></section>')
    return ''.join(out)


CSS = """
.result:has(#panel-prepare:target) a[href="#panel-prepare"]{border-color:#b94d2a;color:#193c38;font-weight:700}
.prep-notice{color:#63736c;font-size:14px}.preparation li{display:flex;gap:10px;align-items:center}.preparation li label{display:flex;gap:12px;align-items:flex-start;flex:1;min-width:0}.preparation li span{overflow-wrap:anywhere}.preparation input[type=checkbox]{width:20px;height:20px;flex-shrink:0;accent-color:#087f7a;margin-top:5px}.preparation input:checked+span{text-decoration:line-through;color:#6f8077}.preparation button{border:1px solid #cad9ce;background:#fffefa;color:#087f7a;border-radius:10px;padding:8px 12px;cursor:pointer;min-height:40px}.preparation form{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.preparation form label{flex:1}.preparation input[name=task]{display:block;width:100%;padding:12px;border:1px solid #cad9ce;border-radius:10px;font:inherit;margin-top:8px}.preparation :focus-visible{outline:3px solid #b94d2a;outline-offset:2px}.preparation button:disabled{opacity:.5}.preparation [data-prep-status]{font-size:13px;color:#63736c}.preparation button[hidden]{display:none}@media(max-width:700px){.preparation li{flex-wrap:wrap}.preparation li label{flex-basis:100%}}@media print{.preparation button,.preparation form,.prep-notice{display:none}}
"""


JS = r"""
for (const box of document.querySelectorAll('.preparation')) {
  const list = box.querySelector('[data-prep-list]'), status = box.querySelector('[data-prep-status]');
  const form = box.querySelector('form'), retry = box.querySelector('[data-prep-retry]');
  const endpoint = box.dataset.endpoint;
  let revision = Number(box.dataset.revision), busy = false, dirty = false;
  let items = [...list.children].map(row => ({id:row.dataset.taskId,text:row.querySelector('span').textContent,done:row.querySelector('input').checked}));
  function render() {
    list.replaceChildren();
    for (const item of items) {
      const row = document.createElement('li'); row.dataset.taskId = item.id;
      const label = document.createElement('label'), check = document.createElement('input'), span = document.createElement('span');
      check.type = 'checkbox'; check.checked = item.done; span.textContent = item.text;
      label.append(check, span); row.append(label);
      for (const [action, title] of [['edit','修改'],['delete','删除']]) {
        const button = document.createElement('button'); button.type = 'button'; button.dataset[action] = ''; button.textContent = title; row.append(button);
      }
      list.append(row);
    }
  }
  if (!endpoint) {
    try { const saved = JSON.parse(localStorage.getItem(box.dataset.storage));
      if (Array.isArray(saved) && saved.length <= 100 && saved.every(i => i && typeof i.id === 'string' && typeof i.text === 'string' && i.text.length <= 500 && typeof i.done === 'boolean')) { items = saved; render(); }
    } catch { status.textContent = '浏览器存储不可用，关闭页面后可能丢失修改。'; }
  }
  async function save() {
    if (busy) return;
    busy = true; dirty = true; retry.hidden = true;
    box.querySelectorAll('input,button').forEach(el => el.disabled = true);
    status.textContent = '正在保存…';
    try {
      if (endpoint) {
        const response = await fetch(endpoint, {method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json','X-TravelMate-Request':'1'},body:JSON.stringify({revision,items})});
        if (!response.ok) throw new Error(response.status === 409 ? '清单已在另一页面修改，请刷新后再编辑。当前草稿未保存。' : response.status === 401 ? '登录已过期，请重新登录。当前草稿未保存。' : '保存失败，当前草稿尚未保存，请重试。');
        const data = await response.json(); revision = data.revision;
      } else { localStorage.setItem(box.dataset.storage, JSON.stringify(items)); }
      status.textContent = endpoint ? '已保存到账号' : '已保存到当前浏览器';
      dirty = false;
    } catch (error) { status.textContent = error.message || '保存失败，请重试。'; retry.hidden = false; }
    finally { busy = false; box.querySelectorAll('input,button').forEach(el => el.disabled = false); }
  }
  list.addEventListener('change', event => {
    if (busy) return;
    const row = event.target.closest('li'), item = items.find(i => i.id === row.dataset.taskId);
    item.done = event.target.checked; save();
  });
  list.addEventListener('click', event => {
    if (busy) return;
    const row = event.target.closest('li'); if (!row) return;
    const item = items.find(i => i.id === row.dataset.taskId);
    if (event.target.closest('[data-edit]')) {
      const value = window.prompt('修改准备事项（最多500字）', item.text);
      if (value === null) return;
      if (!value.trim() || value.trim().length > 500) { status.textContent = '请输入1至500字。'; return; }
      item.text = value.trim();
    } else if (event.target.closest('[data-delete]')) { items = items.filter(i => i.id !== item.id); }
    else return;
    render(); save();
  });
  form.addEventListener('submit', event => {
    event.preventDefault(); if (busy) return;
    const input = form.elements.task, value = input.value.trim();
    if (!value || value.length > 500 || items.length >= 100) { status.textContent = '每项1至500字，最多100项。'; return; }
    items.push({id:crypto.randomUUID(),text:value,done:false}); input.value = ''; render(); save();
  });
  retry.addEventListener('click', save);
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
}
"""
