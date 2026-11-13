"""Accommodation area cards over the saved guide's lodging suggestions."""
import re
from base64 import b64encode
from pathlib import Path

from travelmate.evidence import safe_url


CSS = """
.lodging-eyebrow{display:inline-block;background:#e4eadb;border-radius:99px;padding:3px 18px;font-size:13px;margin:4px 0 10px}.panel-lodging>.daily-heading{margin:0 0 20px;gap:24px}.panel-lodging>.daily-heading h2{border:0;padding:0;font-size:48px}.panel-lodging>.daily-heading p{border-left:1px solid #849d8b;padding-left:24px;font-size:19px}
.lodging-lead{display:flex;align-items:center;gap:24px;background:linear-gradient(110deg,#e3ebdc,#f0f1e6);border-radius:18px;padding:20px 28px;margin-bottom:24px}.lodging-lead>p{min-width:0;overflow-wrap:anywhere;display:flex;align-items:center;gap:18px;margin:0;flex:1;font:700 25px/1.5 Georgia,'Songti SC',SimSun,serif}.lodging-lead em{font-style:normal;color:#b94d2a}.lodging-icon{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;flex-shrink:0;color:#49735d}.lodging-icon svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}.lodging-lead>p>.lodging-icon{background:#398b7f;color:white;width:50px;height:50px;border-radius:50%}.lodging-route{flex:1.5;min-width:0;display:flex;align-items:center;gap:18px;border-left:1px solid #8aa594;padding-left:24px;max-width:60%}.lodging-route>span{font-size:13px;white-space:nowrap}.lodging-route ol{flex:1;display:flex;list-style:none;margin:0;padding:0;gap:0;flex-wrap:wrap}.lodging-route li{flex:1;min-width:90px;position:relative;padding:16px 10px 0;border-top:2px solid #96b7a3;font-size:12px;text-align:center;overflow-wrap:anywhere}.lodging-route li:before{content:'';position:absolute;width:10px;height:10px;border:3px solid #398b7f;border-radius:50%;background:#faf8f3;top:-9px;left:calc(50% - 8px)}.lodging-route a{color:inherit;text-decoration:none}.lodging-route b{display:block}
.lodging-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.lodging-card{border:1px solid #d8ddcf;border-radius:17px;overflow:hidden;background:#fffefa;min-width:0;display:flex;flex-direction:column}.lodging-card:first-child{border-color:#398b7f;box-shadow:0 0 0 1px #398b7f}.lodging-photo{height:185px;position:relative;background:#e3ebdc}.lodging-photo img{width:100%;height:100%;object-fit:cover;display:block}.lodging-photo>strong{position:absolute;top:8px;left:0;background:#bf5832;color:white;padding:3px 22px 3px 18px;border-radius:0 0 24px 0;font-family:Georgia,'Songti SC',SimSun,serif}.lodging-photo>small{position:absolute;right:8px;bottom:8px;background:#193c38cf;color:white;border-radius:5px;padding:2px 7px;font-size:10px}.lodging-copy{padding:15px 20px;flex:1;display:flex;flex-direction:column}.lodging-card-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px}.lodging-card h3{font:700 29px/1.35 Georgia,'Songti SC',SimSun,serif;margin:0;overflow-wrap:anywhere}.lodging-price{font-size:12px;background:#edf0e3;border-radius:99px;padding:3px 9px;color:#63736c;overflow-wrap:anywhere}.lodging-price strong{color:#b94d2a;font-size:17px}.lodging-card dl{margin:0 0 8px}.lodging-card dl>div{display:grid;grid-template-columns:110px 1fr;border-bottom:1px solid #e0e1d7;padding:10px 0;gap:8px;font-size:14px;line-height:1.6}.lodging-card dt{display:flex;gap:8px;align-items:flex-start;font-weight:600}.lodging-card dd{margin:0;white-space:pre-line;overflow-wrap:anywhere;color:#303b34}.lodging-description{font-size:14px;white-space:pre-line;overflow-wrap:anywhere;color:#303b34;line-height:1.8;margin:5px 0 18px}.lodging-tags{display:flex;flex-wrap:wrap;gap:10px;margin-top:auto}.lodging-tags span{background:#e4eadb;border-radius:99px;padding:3px 16px;font-size:13px}
.lodging-checklist{display:flex;align-items:center;gap:24px;border:1px solid #d8ddcf;border-radius:18px;margin-top:24px;padding:22px 24px}.lodging-checklist>h3{font:700 24px/1.5 Georgia,'Songti SC',SimSun,serif;margin:0;white-space:nowrap}.lodging-checks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;border-left:1px solid #8aa594;padding-left:24px;flex:1}.lodging-checks>div{display:flex;gap:10px}.lodging-checks .lodging-icon{background:#e4eadb;border-radius:50%;width:42px;height:42px}.lodging-checks strong{font-size:16px}.lodging-checks p{font-size:12px;color:#63736c;line-height:1.7;margin:2px 0 0}.lodging-cta{display:inline-block;background:#bf5832;color:#fff!important;padding:12px 20px;border-radius:12px;text-decoration:none;white-space:nowrap;font-weight:600}.lodging-footnote{font-size:11px;color:#63736c;text-align:right;margin:12px 0 0}
@media(max-width:1100px){.lodging-lead{align-items:flex-start;flex-direction:column}.lodging-route{max-width:none;width:100%;border:0;padding:0}.lodging-route ol{flex:1}.lodging-card dl>div{grid-template-columns:1fr;gap:3px}.lodging-checklist{flex-wrap:wrap}.lodging-checks{min-width:65%}.lodging-cta{margin-left:auto}}
@media(max-width:760px){.panel-lodging>.daily-heading{gap:8px}.panel-lodging>.daily-heading h2{font-size:34px}.panel-lodging>.daily-heading p{border:0;padding:0;font-size:15px}.lodging-lead{padding:18px;gap:24px}.lodging-lead>p{font-size:21px}.lodging-route{display:block}.lodging-route>span{display:block;margin-bottom:18px}.lodging-route li{min-width:75px}.lodging-grid{grid-template-columns:1fr}.lodging-photo{height:200px}.lodging-card dl>div{grid-template-columns:110px 1fr}.lodging-checklist{padding:20px;gap:18px}.lodging-checks{grid-template-columns:1fr;width:100%;border:0;padding:0;gap:16px}.lodging-cta{width:100%;text-align:center}.lodging-footnote{text-align:left}}
@media print{.lodging-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.lodging-card,.lodging-checklist{break-inside:avoid}.lodging-cta{display:none}.lodging-photo{height:140px}}
"""


def icon(name):
    paths = {
        'bed': '<path d="M3 18V6m0 9h18v6M3 18h18M7 15V9h6v6m0-5h5a3 3 0 0 1 3 3v2M3 21v-3"/>',
        'people': '<circle cx="9" cy="7" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2Zm14-14a3 3 0 0 1 0 6m1 3a5 5 0 0 1 3 5"/>',
        'train': '<rect x="5" y="3" width="14" height="16" rx="3"/><path d="M5 12h14M8 22l2-3m6 3-2-3M9 16h.01M15 16h.01"/>',
        'balance': '<path d="M12 3v17m-5 1h10M4 6h16M5 6l-4 9h8Zm14 0-4 9h8Z"/>',
        'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 5 2 2 5-5"/>',
    }
    return '<span class="lodging-icon" aria-hidden="true"><svg viewBox="0 0 24 24">' + paths[name] + '</svg></span>'


def lodging_cards(section, days, text, inline_images=False):
    items = section.get('items', [])
    if not items:
        return '<p class="daily-empty">本版尚无住宿建议，可在对话中补充预算与住宿偏好。</p>'
    first_line = items[0]['text'].strip().split('\n')[0]
    lead = '优先看' + first_line if len(first_line) <= 16 and '\n' in items[0]['text'] else '先选顺路片区'
    out = ['<aside class="lodging-lead"><p>' + icon('bed') + '<span>这份行程，<em>' + text(lead) + '</em></span></p>']
    if days:
        out.append('<nav class="lodging-route" aria-label="住宿参考行程动线"><span>行程动线（' + str(len(days)) + '天）</span><ol>')
        for i, day in enumerate(days, 1):
            place = next((r[1] for r in day.get('rows', []) if len(r) > 1), '查看当日安排')
            out.append(f'<li><a href="#day-{i}"><b>D{i}</b>{text(place)}</a></li>')
        out.append('</ol></nav>')
    out.append('</aside><div class="lodging-grid" aria-label="住哪里更顺路">')
    for i, item in enumerate(items, 1):
        raw = item['text'].strip()
        lines = raw.splitlines()
        heading = re.split('[：:]', lines[0], maxsplit=1)[0] if lines else ''
        named = bool(heading and len(heading) <= 24 and (len(lines) > 1 or '：' in raw or ':' in raw))
        title = heading if named else f'住宿建议 {i:02d}'
        # Older snapshots contain free prose; keep it intact rather than infer facts.
        fields = re.findall(r'^(适合谁|出行便利|需要取舍|参考预算|标签)[：:]\s*(.+)$', raw, re.M)
        structured = named and lines[0].strip() == heading and len(lines) > 1 and len(fields) == len(lines) - 1 and len(dict(fields)) == len(fields)
        values = dict(fields) if structured else {}
        filename = ('lodging-room.webp', 'lodging-city.webp', 'lodging-canal.webp')[(i - 1) % 3]
        src = '/assets/visual/' + filename
        if inline_images:
            src = 'data:image/webp;base64,' + b64encode((Path(__file__).with_name('images') / filename).read_bytes()).decode('ascii')
        out.append('<article class="lodging-card"><div class="lodging-photo"><img src="' + text(src) + '" alt="住宿氛围示意，AI 生成，非酒店或目的地实拍" loading="lazy">' + ('<strong>先看这里</strong>' if i == 1 else '') + '<small>AI 参考图</small></div><div class="lodging-copy"><div class="lodging-card-heading"><h3>' + text(title) + '</h3><span class="lodging-price">' + ('参考预算 <strong>' + text(values['参考预算']) + '</strong>' if values.get('参考预算') else '房价待查询') + '</span></div>')
        if structured:
            out.append('<dl>')
            for label, symbol in (('适合谁', 'people'), ('出行便利', 'train'), ('需要取舍', 'balance')):
                out.append('<div><dt>' + icon(symbol) + label + '</dt><dd>' + text(values.get(label) or '方案未单列，请结合实际需求确认。') + '</dd></div>')
            out.append('</dl>')
        else:
            out.append('<p class="lodging-description">' + text(raw) + '</p>')
        if safe_url(item.get('link')):
            out.append('<p><a href="' + text(item['link']) + '" target="_blank" rel="noopener noreferrer">' + text(item.get('link_label', '公开来源')) + '</a></p>')
        tags = re.split('[、，,｜|]', values.get('标签', '片区参考、订前核实'))
        out.append('<div class="lodging-tags">' + ''.join('<span>' + text(tag.strip()) + '</span>' for tag in tags if tag.strip()) + '</div></div></article>')
    out.append('</div><aside class="lodging-checklist" aria-label="订房前确认"><h3>订房前看这三件事</h3><div class="lodging-checks">')
    for symbol, title, description in (
        ('calendar', '取消条款', '确认是否可免费取消、截止时间，预留行程调整空间。'),
        ('bed', '房型与人数', '根据同行人数选房型，关注床型、空间与设施。'),
        ('train', '到站交通', '核对车站或机场到酒店的交通方式与实际耗时。')):
        out.append('<div>' + icon(symbol) + '<div><strong>' + title + '</strong><p>' + description + '</p></div></div>')
    out.append('</div><a class="lodging-cta" href="#panel-prepare">查看订房准备 →</a></aside><p class="lodging-footnote">图片为 AI 生成的通用旅行参考图；预算如有列出为方案参考，以实际房价与房态为准。</p>')
    return ''.join(out)
