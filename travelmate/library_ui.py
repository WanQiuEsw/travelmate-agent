"""Reuse the existing seven guide panels inside the guide library shell."""
from html import escape
from pathlib import Path


def cover(destination):
    cities = {'厦门': 'xiamen', '北京': 'beijing', '上海': 'shanghai', '杭州': 'hangzhou',
              '成都': 'chengdu', '广州': 'guangzhou', '西安': 'xian'}
    return next((f'/assets/visual/cities/{slug}.webp' for name, slug in cities.items() if name in destination),
                '/assets/visual/town.webp')


def detail_page(document, item, versions, current):
    text = lambda value: escape(str(value), quote=True)
    key, title = item['id'], text(item['title'])
    prefix = f'/api/guides/{key}/versions/{current}'
    inner = document.split('<body><main>', 1)[1].split('</main>', 1)[0]
    styles = document.split('<style>', 1)[1].split('</style>', 1)[0]
    script = document.split('</main>', 1)[1].removesuffix('</body></html>')
    timeline = ''.join(
        f'<li class="{"current" if row["version"] == current else ""}"><a href="/guides/{key}/versions/{row["version"]}">'
        f'<strong>V{row["version"]} · {"首次生成" if row["version"] == 1 else "保存的方案"}</strong>'
        f'<small>{text(row["saved_at"][:10] or "历史版本")}</small>'
        f'{"<span>当前查看</span>" if row["version"] == current else ""}</a></li>' for row in versions)
    options = ''.join(f'<option value="/guides/{key}/versions/{row["version"]}"'
                      f'{" selected" if row["version"] == current else ""}>V{row["version"]}'
                      f'{" · 最新版" if row["version"] == item["latest"] else ""}</option>' for row in versions)
    body = f'''
      <div class="library-breadcrumb"><a href="/guides">我的攻略</a><span>/</span>{title}</div>
      <header class="library-heading detail-heading"><div><h1>{title}</h1><p>已自动保存 · 当前查看 V{current}</p></div>
        <div class="detail-actions"><details class="download-menu"><summary>↓ 下载攻略</summary><div>
          <a href="{prefix}/pdf">PDF 文档</a><a href="{prefix}/html">离线 HTML</a><a href="{prefix}/md">Markdown</a></div></details>
          <button type="button" class="library-primary" data-resume="{key}">从最新版继续调整 ↗</button></div></header>
      <section class="detail-cover"><img src="{cover(item.get('destination') or '')}" alt="旅行意境参考图"><div><p>YOUR NEXT JOURNEY</p><h2>{title}</h2><span>{text(item.get('days') or '—')} 天</span><span>{text(item.get('travelers') or '—')} 人同行</span><span>{text(item.get('start_date') or '出发日期未定')}</span></div></section>
      <p id="library-status" class="library-status" role="status" aria-live="polite"></p>
      <div class="detail-layout"><div class="detail-document">{inner}</div><aside class="version-rail" aria-label="方案版本">
        <h2>方案版本</h2><label>选择查看版本<select id="guide-version" aria-label="选择攻略版本">{options}</select></label>
        <ol>{timeline}</ol><p>旧版本独立保留。继续调整会生成新版本。</p>
        <a class="back-library" href="/guides">← 返回我的攻略</a>
        <p class="version-notice">出发前请再次核实票价与开放时间。预算修改后点击保存，可在本版本中再次查看并导出。</p>
      </aside></div>'''
    template = Path(__file__).with_name('library.html').read_text(encoding='utf-8')
    start, tail = template.split('<!-- BODY_START -->', 1)
    _, end = tail.split('<!-- BODY_END -->', 1)
    return (start + body + end).replace('<!-- GUIDE_STYLES -->', f'<style>{styles}</style>')\
        .replace('<body class="library-page">', '<body class="library-page guide-detail-page">')\
        .replace('<title>我的攻略 · TravelMate</title>', f'<title>{title} · TravelMate</title>')\
        .replace('</body>', script + '</body>')
