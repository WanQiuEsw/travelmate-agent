import {apiFetch, refreshAccount, logout} from '/assets/auth.js';

const status = document.querySelector('#library-status');
const grid = document.querySelector('#guide-grid');
let guides = [], favoriteOnly = false, changing = false;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function request(url, options = {}) {
  const response = await apiFetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '操作未完成，请稍后重试');
  return data;
}

function jsonRequest(method, data) {
  return {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)};
}

function cover(destination = '') {
  const cities = [['厦门', 'xiamen'], ['北京', 'beijing'], ['上海', 'shanghai'], ['杭州', 'hangzhou'],
    ['成都', 'chengdu'], ['广州', 'guangzhou'], ['西安', 'xian']];
  const match = cities.find(([name]) => destination.includes(name));
  return match ? `/assets/visual/cities/${match[1]}.webp` : '/assets/visual/town.webp';
}

function displayDate(value) {
  if (!value) return '历史版本';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '历史版本' : date.toLocaleDateString('zh-CN', {timeZone: 'Asia/Shanghai'});
}

async function resume(id, button) {
  if (changing) return;
  changing = true; button.disabled = true;
  status.textContent = '正在打开已保存的旅行方案…';
  try {
    const data = await request(`/api/guides/${id}/resume`, {method: 'POST'});
    window.location.assign('/?session=' + encodeURIComponent(data.session_id));
  } catch (error) {
    status.textContent = error.message;
    changing = false; button.disabled = false;
  }
}

async function update(item, data) {
  if (changing) return;
  changing = true;
  try {
    const saved = await request(`/api/guides/${item.id}`, jsonRequest('PATCH', data));
    Object.assign(item, saved);
    render();
    status.textContent = data.title ? '攻略已重命名' : item.favorite ? '已加入收藏' : '已取消收藏';
  } catch (error) { status.textContent = error.message; }
  finally { changing = false; }
}

function card(item) {
  const article = node('article', 'guide-card');
  article.setAttribute('aria-label', item.title);
  const href = '/guides/' + item.id;
  const media = node('a', 'guide-card-cover'); media.href = href;
  media.setAttribute('aria-label', '查看攻略：' + item.title);
  const image = node('img'); image.src = cover(item.destination); image.alt = (item.destination || '旅行') + '意境参考图';
  image.width = 960; image.height = 640; image.loading = 'lazy';
  image.addEventListener('error', () => { if (!image.src.endsWith('/town.webp')) image.src = '/assets/visual/town.webp'; });
  media.append(image, node('span', 'guide-card-version', 'V' + item.latest));
  const bookmark = node('button', 'guide-bookmark'); bookmark.type = 'button';
  bookmark.setAttribute('aria-label', (item.favorite ? '取消收藏：' : '收藏攻略：') + item.title);
  bookmark.setAttribute('aria-pressed', String(item.favorite));
  bookmark.innerHTML = '<svg viewBox="0 0 20 24" aria-hidden="true"><path d="M4 2h12a1 1 0 0 1 1 1v18l-7-5-7 5V3a1 1 0 0 1 1-1Z"/></svg>';
  bookmark.addEventListener('click', () => update(item, {favorite: !item.favorite}));
  const body = node('div', 'guide-card-body');
  const title = node('h2'); const titleLink = node('a', '', item.title); titleLink.href = href; title.append(titleLink);
  const facts = node('p', 'guide-card-facts');
  facts.append(node('span', '', `${item.days || '—'} 天`), node('span', '', `${item.travelers || '—'} 人`));
  if (Number.isFinite(item.budget) && item.budget > 0) {
    const total = item.budget_scope === 'per_person' ? item.budget * item.travelers : item.budget;
    const currency = item.budget_currency === 'CNY' ? '¥' : (item.budget_currency || '');
    facts.append(node('span', '', `全员预算 ${currency}${Number(total).toLocaleString('zh-CN')}`));
  }
  if (item.start_date) facts.append(node('span', '', '出发 ' + item.start_date));
  const time = node('time', '', '保存于 ' + displayDate(item.updated_at)); time.dateTime = item.updated_at;
  const actions = node('div', 'guide-card-actions');
  const view = node('a', '', '查看攻略 →'); view.href = href;
  const adjust = node('button', '', '继续调整'); adjust.type = 'button';
  adjust.addEventListener('click', () => resume(item.id, adjust));
  const more = node('details', 'guide-more');
  const summary = node('summary', '', '⋯'); summary.setAttribute('aria-label', '更多操作：' + item.title);
  const menu = node('div');
  const rename = node('button', '', '重命名'); rename.type = 'button';
  rename.addEventListener('click', () => {
    if (changing) return;
    const title = window.prompt('攻略名称（1～80 个字）', item.title);
    if (title === null) return;
    if (!title.trim() || title.trim().length > 80) { status.textContent = '攻略名称须为 1～80 个字'; return; }
    update(item, {title: title.trim()});
  });
  const remove = node('button', 'guide-remove', '删除攻略'); remove.type = 'button';
  remove.addEventListener('click', async () => {
    if (changing || !window.confirm('删除这份攻略及全部历史版本？原聊天记录会保留，删除后无法撤销。')) return;
    changing = true; remove.disabled = true;
    try {
      await request(`/api/guides/${item.id}`, {method: 'DELETE'});
      guides = guides.filter(guide => guide.id !== item.id); render();
      status.textContent = '攻略已删除，原聊天记录仍保留';
    } catch (error) { status.textContent = error.message; }
    finally { changing = false; remove.disabled = false; }
  });
  menu.append(rename, remove); more.append(summary, menu);
  actions.append(view, adjust, more); body.append(title, facts, time, actions);
  article.append(media, bookmark, body); return article;
}

function render() {
  const query = document.querySelector('#guide-search').value.trim().toLocaleLowerCase();
  const sorting = document.querySelector('#guide-sort').value;
  const filtered = guides.filter(item => (!favoriteOnly || item.favorite)
    && `${item.title} ${item.destination || ''}`.toLocaleLowerCase().includes(query));
  filtered.sort((a, b) => sorting === 'departure'
    ? (a.start_date || '9999').localeCompare(b.start_date || '9999') || b.updated_at.localeCompare(a.updated_at)
    : b.updated_at.localeCompare(a.updated_at));
  document.querySelector('#filter-all span').textContent = guides.length;
  document.querySelector('#filter-favorite span').textContent = guides.filter(item => item.favorite).length;
  document.querySelector('#filter-all').setAttribute('aria-pressed', String(!favoriteOnly));
  document.querySelector('#filter-favorite').setAttribute('aria-pressed', String(favoriteOnly));
  const count = document.querySelector('#guide-count'); count.replaceChildren();
  count.append(document.createTextNode('已为你保存 '), node('strong', '', String(guides.length)), document.createTextNode(' 份旅行攻略'));
  grid.replaceChildren(...filtered.map(card));
  if (!filtered.length) {
    const empty = node('div', 'guide-empty');
    empty.append(node('span', 'guide-empty-mark', '▤'), node('h2', '', !guides.length ? '第一份旅行攻略，从这里开始' : '暂时没有找到攻略'),
      node('p', '', !guides.length ? '聊聊想去的地方，生成的攻略会自动保存在这里。' : query ? '换个目的地或名称试试。' : '点击攻略上的书签，把喜欢的旅行加入收藏。'));
    if (!guides.length) { const link = node('a', 'library-new', '＋ 规划第一段旅程'); link.href = '/?new=1'; empty.append(link); }
    grid.append(empty);
  }
}

async function load() {
  grid.setAttribute('aria-busy', 'true');
  status.textContent = '正在读取攻略…';
  try {
    guides = (await request('/api/guides')).guides;
    render(); status.textContent = '';
  } catch (error) {
    status.textContent = '攻略加载失败：' + error.message;
    const retry = node('button', '', '重新加载'); retry.type = 'button'; retry.addEventListener('click', load); status.append(retry);
  } finally { grid.setAttribute('aria-busy', 'false'); }
}

document.querySelector('#logout').addEventListener('click', async () => {
  try { await logout(); } catch (error) { status.textContent = error.message; }
});
document.querySelectorAll('[data-resume]').forEach(button => button.addEventListener('click', () => resume(button.dataset.resume, button)));
document.querySelector('#guide-version')?.addEventListener('change', event => window.location.assign(event.target.value));
if (grid) {
  document.querySelector('#guide-search').addEventListener('input', render);
  document.querySelector('#guide-sort').addEventListener('change', render);
  document.querySelector('#filter-all').addEventListener('click', () => { favoriteOnly = false; render(); });
  document.querySelector('#filter-favorite').addEventListener('click', () => { favoriteOnly = true; render(); });
}
try { await refreshAccount(); if (grid) await load(); }
catch (error) { status.textContent = error.message; if (grid) grid.setAttribute('aria-busy', 'false'); }
