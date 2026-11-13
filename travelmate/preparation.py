"""Version-scoped preparation tasks persisted with the existing SQLite checkpoints."""
from hashlib import sha256
import re


# shortcut: only recognized packing items are split; extend this list when new compound items recur.
PACKING_ITEMS = re.compile(
    r'身份证|学生证|老年证|护照|签证|驾驶证|充电宝|充电线|数据线|充电器|插排|'
    r'薄外套|外套|步行鞋|运动鞋|鞋子|鞋|帽子|手套|创可贴|肠胃药|晕车药|'
    r'雨伞|防晒霜|耳机|12306|高德(?:地图)?|百度地图|大众点评|[^，、；：。\s]*景区公众号'
)


def split_task(item):
    names = list(dict.fromkeys(match.group() for match in PACKING_ITEMS.finditer(item['text'])))
    if len(names) < 2:
        return [item]
    return [dict(item, id=item['id'] if i == 0 else f'{item["id"]}-part-{i}',
                 text=name, detail=item['text'], category=category({'text': name}))
            for i, name in enumerate(names)]


def initial_tasks(guide):
    tasks = [{'id': f'seed-{i}', 'text': item['text'], 'done': False}
             for section in guide['sections'] if section['title'] == '行前准备'
             for i, item in enumerate(section['items'])]
    return expand_tasks(tasks)


def expand_tasks(tasks, originals=None):
    result = []
    ids = {item['id'] for item in tasks}
    for index, item in enumerate(tasks):
        parts = split_task(item) if originals is None or originals.get(item['id']) == item['text'] else [item]
        if len(result) + len(parts) + len(tasks) - index - 1 > 100 or any(p['id'] in ids for p in parts[1:]):
            parts = [item]
        result.extend(parts)
    return result


def overlay(guide, saved=None):
    data = saved if saved is not None else {'revision': 0, 'items': initial_tasks(guide)}
    if saved is not None:
        originals = {f'seed-{i}': item['text'] for section in guide['sections'] if section['title'] == '行前准备'
                     for i, item in enumerate(section['items'])}
        data = dict(saved, items=expand_tasks(saved['items'], originals))
    guide['preparation'] = data
    for section in guide['sections']:
        if section['title'] == '行前准备':
            section['items'] = [{'text': ('[x] ' if item['done'] else '[ ] ') + item['text'] + (f'（{item["detail"]}）' if item.get('detail') else '')} for item in data['items']]
    sections = guide['sections']
    preparation = [s for s in sections if s['title'] == '行前准备']
    sections = [s for s in sections if s['title'] != '行前准备']
    index = next((i for i, s in enumerate(sections) if s['kind'] == 'day'), len(sections))
    guide['sections'] = sections[:index] + preparation + sections[index:]
    return guide


CATEGORIES = ('证件', '随身用品', '出发确认')


def category(item):
    if item.get('category') in CATEGORIES:
        return item['category']
    value = item['text']
    if any(word in value for word in ('证件', '身份证', '护照', '签证', '学生证', '老年证', '驾驶证')):
        return '证件'
    if any(word in value for word in ('充电', '数据线', '衣', '外套', '鞋', '药', '雨伞', '背包', '防晒', '洗漱', '行李', '耳机', '插排', '帽子', '手套', '创可贴')):
        return '随身用品'
    return '出发确认'


ICONS = {
    'checklist': '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V3h6v2M9 13l2 2 4-5"/>',
    '证件': '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="11" r="2"/><path d="M5 16c0-3 6-3 6 0m3-6h4m-4 4h4"/>',
    '随身用品': '<rect x="4" y="6" width="16" height="15" rx="2"/><path d="M9 6V3h6v3M8 6v15M16 6v15"/>',
    '出发确认': '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    'edit': '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z"/>',
    'delete': '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    'cloud': '<path d="M6 18a5 5 0 0 1-1-10 7 7 0 0 1 13-1 5 5 0 0 1 0 11M12 20V10m-4 4 4-4 4 4"/>',
}


def icon(name):
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[name] + '</svg>'


def panel(guide, text):
    from travelmate.daily_ui import scenery
    data = guide.get('preparation') or {'revision': 0, 'items': initial_tasks(guide)}
    endpoint = guide.get('_preparation_url', '')
    key = sha256((guide['title'] + str(guide['version']) + guide.get('saved_at', '')).encode()).hexdigest()[:24]
    done = sum(item['done'] for item in data['items'])
    total = len(data['items'])
    out = [f'<section class="card preparation" data-endpoint="{text(endpoint)}" data-revision="{data["revision"]}" data-storage="travelmate-preparation-{key}">',
           '<header class="prep-heading"><div class="prep-title">' + icon('checklist') + '<div><h2>行前准备</h2><p>把准备做在前面，出发时轻松一点。</p></div></div>',
           f'<div class="prep-progress"><strong data-prep-count>已完成 {done} / {total} 项</strong><progress max="{total or 1}" value="{done}" aria-label="行前准备完成进度"></progress></div>',
           '<div class="prep-filters" role="group" aria-label="筛选准备状态"><button type="button" data-filter="all" aria-pressed="true">全部</button><button type="button" data-filter="pending" aria-pressed="false">待准备</button><button type="button" data-filter="done" aria-pressed="false">已完成</button></div><button type="button" data-add-category="证件" class="prep-primary">＋ 新增事项</button></header>',
           '<h3 class="prep-section-title">分类准备清单<span>逐项确认，从容出发</span></h3><div class="prep-groups" data-prep-list>']
    descriptions = ('有效证件提前备齐，重要资料随身带。', '整理行李与物品，查漏补缺。', '出发前最后确认，轻装出发。')
    for index, name in enumerate(CATEGORIES):
        entries = [item for item in data['items'] if category(item) == name]
        out.append(f'<section class="prep-group" data-category="{name}"><header>{icon(name)}<h3>{name}</h3><span data-group-count>{sum(i["done"] for i in entries)} / {len(entries)} 项</span><p>{descriptions[index]}</p></header><ul>')
        for item in entries:
            out.append(f'<li data-task-id="{text(item["id"])}" data-detail="{text(item.get("detail") or '')}"><label><input type="checkbox" {"checked" if item["done"] else ""}><span>{text(item["text"])}</span></label><button type="button" data-edit aria-label="修改{text(item["text"])}">{icon("edit")}</button><button type="button" data-delete aria-label="删除{text(item["text"])}">{icon("delete")}</button></li>')
        out.append(f'</ul><p class="prep-empty" hidden>当前分类暂无事项</p><button class="prep-group-add" type="button" data-add-category="{name}">＋ 添加事项</button></section>')
    out.append('</div><form data-prep-add hidden><label class="prep-sr-only" for="prep-task-' + key + '">准备事项</label><input id="prep-task-' + key + '" name="task" maxlength="500" required placeholder="补充需要准备的事项…"><input type="hidden" name="category" value="证件"><button type="submit" class="prep-primary" aria-label="确认事项">✓</button><button type="button" data-prep-cancel aria-label="取消编辑">×</button></form>')
    out.append('<figure class="prep-scenery"><img src="' + text(scenery(guide['title'], not endpoint)) + '" alt="目的地风景示意"><figcaption>目的地 · 风景示意</figcaption></figure>')
    out.append('<footer class="prep-footer"><p class="prep-notice">' + icon('cloud') + ('按本次旅行与方案版本保存到账号' if endpoint else '离线清单仅保存在当前浏览器，不会自动同步到账号。') + '</p><p data-prep-status role="status" aria-live="polite"></p><button type="button" data-prep-retry hidden>重试保存</button><span class="prep-footer-label">' + icon('随身用品') + ' 出发前清单</span></footer><noscript>启用 JavaScript 后可编辑清单。</noscript></section>')
    out.append('<template data-prep-edit-icon>' + icon('edit') + '</template><template data-prep-delete-icon>' + icon('delete') + '</template>')
    return ''.join(out)


CSS = """
.preparation .prep-item-detail{flex-basis:100%;padding-left:31px;color:#63736c;font-size:12px}.prep-item-detail summary{font-size:12px;font-weight:400;cursor:pointer}.prep-item-detail p{margin:6px 0;line-height:1.6;overflow-wrap:anywhere}

.preparation.card{padding:12px 0 0;border:0;background:transparent;margin:0;box-shadow:none}.preparation svg{width:24px;height:24px;flex-shrink:0}.prep-heading{display:flex;align-items:center;gap:24px;margin:4px 0 32px}.prep-title{display:flex;align-items:center;gap:16px;margin-right:auto}.prep-title>svg{width:56px;height:64px;color:#54836a}.prep-heading h2{border:0;padding:0;font-size:38px;line-height:1.25;margin:0 0 4px;letter-spacing:1px}.prep-heading p{font-size:15px;color:#747874;margin:0}.prep-progress{border-left:1px solid #b9cdbc;padding-left:30px;min-width:220px;width:26%}.prep-progress strong{font-size:16px;font-weight:600}.prep-progress progress{display:block;width:100%;height:13px;margin-top:10px;accent-color:#087f7a;border:0;border-radius:20px;overflow:hidden;background:#d3dfcc}.prep-progress progress::-webkit-progress-bar{background:#d3dfcc}.prep-progress progress::-webkit-progress-value{background:linear-gradient(90deg,#008d89,#087d72);border-radius:20px}.prep-filters{display:flex;gap:8px;flex-shrink:0}.preparation button{font:inherit;cursor:pointer;border:1px solid #c2d0bf;border-radius:9px;padding:7px 14px;min-height:36px;background:transparent;color:#285d54;white-space:nowrap}.prep-filters button{border-radius:24px;padding:6px 18px;font-size:14px}.preparation .prep-primary,.preparation [aria-pressed=true]{background:linear-gradient(120deg,#008b86,#0b7369);border-color:#087f7a;color:#fff}.prep-section-title{display:flex;align-items:center;gap:14px;font-size:20px;margin:0}.prep-section-title span{font-weight:400;font-size:13px;color:#7d8980}.prep-groups{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:stretch}.prep-group{border:1px solid #c7d5c1;border-radius:13px;background:#fffefa;padding:0 13px 12px;display:flex;flex-direction:column;min-width:0;min-height:325px}.prep-group:last-child{background:#fffefa;border-color:#e9bfa7}.prep-group>header{background:#edf1e6;border-radius:12px 12px 0 0;margin:0 -13px 12px;padding:16px 19px 12px;display:flex;align-items:center;gap:9px;flex-wrap:wrap}.prep-group header>svg{color:#54836a}.prep-group h3{font-size:22px;margin:0;line-height:1.4}.prep-group [data-group-count]{margin-left:auto;font-size:13px;background:#dfe9d7;border-radius:20px;padding:1px 12px;white-space:nowrap}.prep-group:last-child>header{background:#faece2}.prep-group:last-child header>svg,.prep-group:last-child h3{color:#b94d2a}.prep-group:last-child [data-group-count]{background:#fae1ce;color:#a7431f}.prep-group header p{line-height:1.5;flex-basis:100%;font-size:13px;color:#666f65;margin:0}.preparation .prep-group ul{list-style:none;padding:0;margin:0 0 12px;display:grid;gap:7px}.preparation li{flex-wrap:wrap;margin:0;white-space:normal;display:flex;align-items:center;gap:4px;padding:7px 8px;min-height:42px;border:1px solid #d6dfd9;border-radius:10px;background:#ffffffa6}.preparation li:has(:checked){background:#e8efdf;border-color:transparent}.preparation li label{display:flex;align-items:center;gap:12px;flex:1;min-width:0;font-size:15px;color:#293b35;cursor:pointer}.preparation li span{overflow-wrap:anywhere}.preparation input[type=checkbox]{appearance:none;width:19px;height:19px;margin:0;border:1.5px solid #6c7770;border-radius:4px;background:white;flex-shrink:0;display:grid;place-items:center;cursor:pointer}.preparation input:checked{background:linear-gradient(120deg,#009590,#08776c);border-color:#087f7a}.preparation input:checked:after{content:'✓';color:white;font-size:15px;line-height:1}.preparation input:checked+span{text-decoration:line-through;color:#68756a}.preparation li button{border:0;padding:4px;min-height:28px;color:#587567;display:grid;place-items:center}.preparation li button svg{width:17px;height:17px}.preparation li button:hover{background:#dce8dc;color:#087f7a}.preparation .prep-group-add{margin-top:auto;width:100%;border-color:#77a89a;border-radius:9px;padding:6px 12px;font-weight:600}.prep-empty{font-size:13px;color:#7b867d;text-align:center;padding:16px 0}.preparation form{display:flex;gap:6px;margin:0 0 12px;align-items:center}.preparation input[name=task]{width:100%;min-width:0;border:1px solid #008d86;background:white;border-radius:8px;padding:9px 12px;font:inherit;font-size:14px;color:#193c38}.preparation form button{padding:4px 8px;min-height:32px;font-size:19px}.prep-sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%)}.prep-scenery{height:100px;position:relative;margin:20px 0 12px;border-radius:12px;overflow:hidden}.prep-scenery img{width:100%;height:100%;object-fit:cover;object-position:center 55%;display:block}.prep-scenery figcaption{position:absolute;right:12px;bottom:10px;background:#fffefaeb;border-radius:7px;padding:3px 10px;font-size:12px;color:#285d54}.prep-footer{display:flex;flex-wrap:wrap;align-items:center;gap:8px;color:#55766a;font-size:12px}.prep-footer p{margin:0}.prep-notice,.prep-footer-label{display:flex;align-items:center;gap:8px}.prep-footer-label{margin-left:auto}.prep-footer svg{width:21px;height:21px}.preparation :focus-visible{outline:3px solid #b94d2a;outline-offset:3px}.preparation [hidden]{display:none!important}.preparation button:disabled{opacity:.5}.preparation [data-prep-status]{color:#63736c}
@media(min-width:1400px){.prep-heading h2{border:0;padding:0;font-size:44px}.prep-heading p{font-size:18px}.prep-heading{gap:40px;margin-bottom:36px}.prep-group{min-height:380px}.preparation li label{font-size:18px}.preparation li{min-height:46px}.prep-scenery{height:112px}.prep-group h3{font-size:26px}}
@media(max-width:1100px){.prep-heading{flex-wrap:wrap;gap:20px}.prep-title{flex:1}.prep-progress{width:35%}.prep-filters{margin-right:auto}.prep-group{padding:0 13px 12px}.prep-group h3{font-size:19px}.prep-group [data-group-count]{padding:1px 7px}.preparation li label{font-size:14px;gap:7px}}
@media(max-width:760px){.prep-groups{grid-template-columns:1fr}.prep-title{flex-basis:100%}.prep-title>svg{width:44px;height:50px}.prep-heading h2{border:0;padding:0;font-size:32px}.prep-progress{width:100%;border:0;padding:0}.prep-heading{gap:16px;margin-bottom:24px}.prep-group{min-height:220px}.prep-group h3{font-size:22px}.preparation li label{font-size:16px}.prep-filters{gap:5px}.prep-filters button{padding:6px 12px}.prep-section-title span{display:none}.prep-scenery{height:100px}.prep-footer-label{display:none}}
@media print{.preparation button,.preparation form,.prep-filters,.prep-footer{display:none}.prep-groups{display:block}.prep-group{margin-bottom:12px;min-height:0}.preparation li[hidden]{display:flex!important}.prep-scenery{display:none}}
"""


JS = r"""
for (const box of document.querySelectorAll('.preparation')) {
  const list = box.querySelector('[data-prep-list]'), status = box.querySelector('[data-prep-status]');
  const form = box.querySelector('form'), retry = box.querySelector('[data-prep-retry]');
  const endpoint = box.dataset.endpoint;
  let revision = Number(box.dataset.revision), busy = false, dirty = false;
  let filter = 'all', editingId = null;
  let items = [...list.querySelectorAll('li')].map(row => ({id:row.dataset.taskId,text:row.querySelector('span').textContent,done:row.querySelector('input').checked,category:row.closest('[data-category]').dataset.category,detail:row.dataset.detail || null}));
  function render() {
    for (const group of list.children) {
      group.querySelector('ul').replaceChildren();
      const entries = items.filter(i => i.category === group.dataset.category);
      group.querySelector('[data-group-count]').textContent = `${entries.filter(i => i.done).length} / ${entries.length} 项`;
      group.querySelector('.prep-empty').hidden = entries.some(i => filter === 'all' || (filter === 'done' ? i.done : !i.done));
      group.querySelector('.prep-empty').textContent = entries.length ? '没有符合筛选的事项' : '暂无事项，添加一项开始准备';
    }
    const done = items.filter(i => i.done).length;
    box.querySelector('[data-prep-count]').textContent = `已完成 ${done} / ${items.length} 项`;
    box.querySelector('progress').max = items.length || 1;
    box.querySelector('progress').value = done;
    for (const item of items) {
      const row = document.createElement('li'); row.dataset.taskId = item.id; row.hidden = filter !== 'all' && (filter === 'done' ? !item.done : item.done);
      const label = document.createElement('label'), check = document.createElement('input'), span = document.createElement('span');
      check.type = 'checkbox'; check.checked = item.done; span.textContent = item.text;
      label.append(check, span); row.append(label);
      for (const [action, title] of [['edit','修改'],['delete','删除']]) {
        const button = document.createElement('button'); button.type = 'button'; button.dataset[action] = ''; button.setAttribute('aria-label', title + item.text); button.append(box.parentElement.querySelector(`[data-prep-${action}-icon]`).content.cloneNode(true)); row.append(button);
      }
      if (item.detail) {
        const details = document.createElement('details'), summary = document.createElement('summary'), note = document.createElement('p');
        details.className = 'prep-item-detail'; summary.textContent = '准备说明'; note.textContent = item.detail;
        details.append(summary, note); row.append(details);
      }
      list.querySelector(`[data-category="${item.category}"] ul`).append(row);
    }
  }
  if (!endpoint) {
    try { const saved = JSON.parse(localStorage.getItem(box.dataset.storage));
      if (Array.isArray(saved) && saved.length <= 100 && saved.every(i => i && typeof i.id === 'string' && typeof i.text === 'string' && i.text.length <= 500 && typeof i.done === 'boolean' && (i.detail == null || typeof i.detail === 'string' && i.detail.length <= 500))) {
        const seeded = items;
        const expanded = saved.flatMap(item => {
          const source = seeded.find(i => i.id === item.id && i.detail === item.text);
          if (!source) return [item];
          const parts = seeded.filter(i => i.detail === item.text && (i.id === item.id || i.id.startsWith(item.id + '-part-')));
          return parts.some(i => i.id !== item.id && saved.some(s => s.id === i.id)) ? [item] : parts.map(i => ({...i,done:item.done}));
        });
        items = (expanded.length <= 100 ? expanded : saved).map(i => ({...i,category:['证件','随身用品','出发确认'].includes(i.category) ? i.category : '出发确认'}));
      }
    } catch { status.textContent = '浏览器存储不可用，关闭页面后可能丢失修改。'; }
  }
  render();
  box.addEventListener('click', event => {
    const button = event.target.closest('[data-filter], [data-add-category]');
    if (!button || busy) return;
    if (button.hasAttribute('data-filter')) {
      filter = button.dataset.filter;
      box.querySelectorAll('[data-filter]').forEach(el => el.setAttribute('aria-pressed', String(el === button)));
      render();
    } else {
      openForm(button.closest('.prep-group') || list.querySelector('[data-category]'), button.dataset.addCategory);
    }
  });
  function closeForm() {
    form.hidden = true; box.append(form); form.reset(); editingId = null;
  }
  function openForm(group, category, item = null) {
    closeForm(); editingId = item ? item.id : null;
    form.elements.category.value = category; form.elements.task.value = item ? item.text : '';
    group.insertBefore(form, group.querySelector('.prep-group-add')); form.hidden = false; form.elements.task.focus();
  }
  box.querySelector('[data-prep-cancel]').addEventListener('click', closeForm);
  form.addEventListener('keydown', event => { if (event.key === 'Escape') closeForm(); });
  async function save() {
    if (busy) return;
    busy = true; dirty = true; retry.hidden = true;
    box.querySelectorAll('input,button,select').forEach(el => el.disabled = true);
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
    finally { busy = false; box.querySelectorAll('input,button,select').forEach(el => el.disabled = false); }
  }
  list.addEventListener('change', event => {
    if (busy) return;
    const row = event.target.closest('li'), item = items.find(i => i.id === row.dataset.taskId);
    item.done = event.target.checked; render(); save();
  });
  list.addEventListener('click', event => {
    if (busy) return;
    const row = event.target.closest('li'); if (!row) return;
    const item = items.find(i => i.id === row.dataset.taskId);
    if (event.target.closest('[data-edit]')) {
      openForm(row.closest('.prep-group'), item.category, item); return;
    } else if (event.target.closest('[data-delete]')) { if (editingId === item.id) closeForm(); items = items.filter(i => i.id !== item.id); }
    else return;
    render(); save();
  });
  form.addEventListener('submit', event => {
    event.preventDefault(); if (busy) return;
    const input = form.elements.task, value = input.value.trim();
    if (!value || value.length > 500 || (!editingId && items.length >= 100)) { status.textContent = '每项1至500字，最多100项。'; return; }
    if (editingId) items.find(i => i.id === editingId).text = value;
    else items.push({id:crypto.randomUUID(),text:value,done:false,category:form.elements.category.value});
    closeForm(); render(); save();
  });
  retry.addEventListener('click', save);
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
}
"""
