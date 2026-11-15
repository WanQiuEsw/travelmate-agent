"""Destination-specific reminders from the saved itinerary."""
from travelmate.daily_ui import scenery
from travelmate.evidence import safe_url
from travelmate.carousel import highlight_stops


def specific_items(guide, sections):
    days = [section for section, _ in sections if section['kind'] == 'day']
    destination = guide.get('result', {}).get('destination') or guide['title'].split(' · ')[0].split(' → ')[-1]
    names = [destination] + [row[1] for _, _, row in highlight_stops(days)]
    names += [row[0] for section, _ in sections if section['kind'] == 'food' for row in section.get('rows', []) if row]
    seen, saved = set(), []
    for section, _ in sections:
        if section['kind'] != 'pitfalls':
            continue
        for item in section.get('items', []):
            value = item['text'].strip()
            if value not in seen and any(name and len(name) >= 2 and name in value for name in names):
                seen.add(value)
                saved.append(item)
    return saved


def panel(guide, sections, text, inline_images=False):
    destination = guide.get('result', {}).get('destination') or guide['title'].split(' · ')[0].split(' → ')[-1]
    saved = specific_items(guide, sections)
    out = ['<div class="pitfall-workspace"><header class="pitfall-hero"><img src="' + text(scenery(destination, inline_images)) + '" alt="目的地风景示意"><div><p class="pitfall-eyebrow">目的地专属提醒</p><h2>' + text(destination) + ' · 少走弯路</h2><p class="pitfall-subtitle">只看这次目的地与景点需要留意的事</p></div></header>']
    if not saved:
        return ''.join(out) + '<p class="daily-empty">本版暂无目的地专属避坑信息。</p></div>'
    out.append('<section class="pitfall-saved"><h3>本次行程 · 专属提醒</h3><ul>')
    for item in saved:
        value, url = item['text'], safe_url(item.get('link'))
        out.append('<li class="' + ('pitfall-priority' if value.startswith(('❌', '⚠')) else '') + '">' + text(value)
                   + (f' <a href="{text(url)}" target="_blank" rel="noopener noreferrer">{text(item.get("link_label", "公开来源"))}</a>' if url else '') + '</li>')
    return ''.join(out) + '</ul></section></div>'


CSS = """
.pitfall-workspace{color:#193c38}.pitfall-hero{position:relative;min-height:210px;display:flex;align-items:center;isolation:isolate;margin-bottom:24px}
.pitfall-hero>img{position:absolute;inset:0 0 0 auto;width:60%;height:100%;object-fit:cover;z-index:-1;mask-image:linear-gradient(90deg,transparent,#000);opacity:.6;border-radius:20px}
.pitfall-eyebrow{color:#b94d2a;font-size:14px;letter-spacing:2px}.pitfall-hero h2{font-size:clamp(28px,4vw,44px);border:0;padding:0;margin:8px 0}.pitfall-subtitle{color:#63736c}
.pitfall-saved{background:#fffefa;border:1px solid #d8ddcf;border-radius:20px;padding:24px 28px}.pitfall-saved h3{margin:0 0 18px;font-size:22px}.pitfall-saved ul{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.pitfall-saved li{padding:18px 22px;background:#eef2e7;border-left:3px solid #66927d;border-radius:4px 12px 12px 4px;line-height:1.8;overflow-wrap:anywhere}.pitfall-saved li.pitfall-priority{background:#fbf0df;border-left-color:#b94d2a}.pitfall-saved a{color:#285b48}
@media(max-width:700px){.pitfall-hero{min-height:180px}.pitfall-hero>img{width:75%;opacity:.4}.pitfall-saved{padding:18px}.pitfall-saved li{padding:14px}.pitfall-subtitle{font-size:14px}}
@media print{.pitfall-saved li{break-inside:avoid}}
"""
