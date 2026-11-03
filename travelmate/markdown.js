// Small Markdown subset for travel replies. Raw HTML is always literal text.
function inline(parent, text) {
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^\s)]+)\)|(https?:\/\/[^\s<>]+)|\*([^*\n]+)\*|~~([^~\n]+)~~|<br\s*\/?\s*>/gi;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(offset, match.index)));
    let element;
    if (match[1]) {
      element = document.createElement('strong'); element.textContent = match[1];
    } else if (match[2]) {
      element = document.createElement('code'); element.textContent = match[2];
    } else if (match[6] || match[7]) {
      element = document.createElement(match[6] ? 'em' : 'del'); element.textContent = match[6] || match[7];
    } else if (/^<br/i.test(match[0])) {
      element = document.createElement('br');
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
    if (references && (/^#{1,6}\s/.test(line) || /^\s*(?:[-*]\s*)?(?:如需|如果|欢迎|你可以|告诉我|需要我)/.test(line))) {
      references = null;
      list = null;
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
      const head = document.createElement('thead'), body = document.createElement('tbody');
      table.append(head, body);
      const cells = row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map(cell => cell.replace(/\\\|/g, '|'));
      const alignment = cells(lines[i + 1]).map(cell => /:\s*$/.test(cell) ? (/^\s*:/.test(cell) ? 'center' : 'right') : 'left');
      const addRow = (row, tag, section) => {
        const tr = document.createElement('tr');
        for (const [index, cell] of cells(row).entries()) {
          const td = document.createElement(tag);
          if (tag === 'th') td.setAttribute('scope', 'col');
          td.setAttribute('style', 'text-align: ' + (alignment[index] || 'left'));
          inline(td, cell.trim()); tr.append(td);
        }
        section.append(tr);
      };
      addRow(line, 'th', head); i++;
      while (i + 1 < lines.length && lines[i + 1].includes('|') && lines[i + 1].trim()) addRow(lines[++i], 'td', body);
      wrapper.append(table); fragment.append(wrapper); list = null; continue;
    }
    if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) { fragment.append(document.createElement('hr')); list = null; continue; }
    if (/^>\s?/.test(line)) {
      const quote = document.createElement('blockquote'); inline(quote, line.replace(/^>\s?/, ''));
      fragment.append(quote); list = null; continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    const item = line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
    if (item) {
      const type = item[1] ? 'ul' : 'ol';
      if (!list || list.tagName.toLowerCase() !== type) {
        list = document.createElement(type); fragment.append(list);
      }
      const li = document.createElement('li'); inline(li, item[2]); list.append(li);
    } else {
      list = null;
      const node = document.createElement(heading ? 'h' + Math.max(2, heading[1].length) : 'p');
      inline(node, heading ? heading[2] : line); fragment.append(node);
    }
  }
  target.replaceChildren(fragment);
}
