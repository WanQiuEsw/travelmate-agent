// Small Markdown subset for travel replies. Raw HTML is always literal text.
function inline(parent, text) {
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^\s)]+)\)|(https?:\/\/[^\s<>]+)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(offset, match.index)));
    let element;
    if (match[1]) {
      element = document.createElement('strong'); element.textContent = match[1];
    } else if (match[2]) {
      element = document.createElement('code'); element.textContent = match[2];
    } else {
      const url = match[4] || match[5];
      element = document.createElement('span');
      try {
        const parsed = new URL(url);
        if (['https:', 'http:'].includes(parsed.protocol)) {
          element = document.createElement('a');
          element.href = parsed.href;
          element.target = '_blank'; element.rel = 'noopener noreferrer';
        }
      } catch {}
      element.textContent = match[3] || url;
    }
    parent.append(element);
    offset = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(offset)));
}

export function renderMarkdown(target, text) {
  const fragment = document.createDocumentFragment();
  let references = null;
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  let list = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:参考来源|引用来源|参考资料|资料来源|来源说明|来源)(?:\*\*)?\s*[:：]?\s*$/.test(line)) {
      references = document.createElement('details');
      references.className = 'references';
      const summary = document.createElement('summary');
      summary.textContent = '参考来源 · 点击查看';
      references.append(summary); fragment.append(references); list = null;
      continue;
    }
    if (references) {
      if (line.trim()) {
        const row = document.createElement('p');
        inline(row, line.replace(/^\s*[-*]\s+/, '')); references.append(row);
      }
      continue;
    }
    if (!line.trim()) { list = null; continue; }
    if (line.startsWith('```')) {
      const code = [];
      while (++i < lines.length && !lines[i].startsWith('```')) code.push(lines[i]);
      const pre = document.createElement('pre'), node = document.createElement('code');
      node.textContent = code.join('\n'); pre.append(node); fragment.append(pre);
      list = null; continue;
    }
    if (line.includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] || '')) {
      const wrapper = document.createElement('div'); wrapper.className = 'table-scroll';
      wrapper.tabIndex = 0; wrapper.setAttribute('role', 'region'); wrapper.setAttribute('aria-label', '行程或预算表格');
      const table = document.createElement('table');
      const cells = row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|');
      const addRow = (row, tag) => {
        const tr = document.createElement('tr');
        for (const cell of cells(row)) {
          const td = document.createElement(tag); inline(td, cell.trim()); tr.append(td);
        }
        table.append(tr);
      };
      addRow(line, 'th'); i++;
      while (i + 1 < lines.length && lines[i + 1].includes('|') && lines[i + 1].trim()) addRow(lines[++i], 'td');
      wrapper.append(table); fragment.append(wrapper); list = null; continue;
    }
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const item = line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
    if (item) {
      const type = item[1] ? 'ul' : 'ol';
      if (!list || list.tagName.toLowerCase() !== type) {
        list = document.createElement(type); fragment.append(list);
      }
      const li = document.createElement('li'); inline(li, item[2]); list.append(li);
    } else {
      list = null;
      const node = document.createElement(heading ? 'h3' : 'p');
      inline(node, heading ? heading[1] : line); fragment.append(node);
    }
  }
  target.replaceChildren(fragment);
}
