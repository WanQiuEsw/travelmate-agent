"""Daily itinerary cards over saved guide rows."""
from base64 import b64encode
from pathlib import Path

CSS = """
.day-plan-choice{border:0;padding:0;margin:16px 0;display:flex;gap:10px;flex-wrap:wrap}.day-plan-choice legend{font-size:13px;color:#63736c;margin-bottom:8px}.day-plan-choice label{display:flex;align-items:center;gap:8px;cursor:pointer;padding:10px 16px;background:#fffefa;border:1px solid #cadbd1;border-radius:10px;min-height:44px}.day-plan-choice label:has(input:checked){background:#e8efe2;border-color:#287a70;color:#165b50}.day-plan-choice input{accent-color:#287a70}.rain-route{display:none}.daily-view:has(.rain-choice:checked) .original-route{display:none}.daily-view:has(.rain-choice:checked) .rain-route{display:block}.rain-notice{padding:14px 18px;background:#eef2e7;border-radius:12px;line-height:1.8}.daily-view input:focus-visible{outline:3px solid #b94d2a;outline-offset:4px}.rain-note{color:#40604e}.rain-unavailable{color:#63736c}.daily-footer a{color:inherit}@media print{.day-plan-choice{display:none}}
.daily-heading{display:flex;align-items:baseline;gap:24px;flex-wrap:wrap;margin:4px 0 24px}.daily-heading h2{border:0;border-left:5px solid #087f7a;padding:0 0 0 18px;margin:0;font:700 36px/1.3 Georgia,'Songti SC',SimSun,serif}.daily-heading p{color:#63736c;margin:0}.panel-days .day-picker{gap:10px}.panel-days .day-picker a{border-radius:10px;background:transparent;color:#193c38;display:flex;gap:12px;align-items:center;padding:10px 18px}.day-picker span{font-size:13px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.panel-days:not(:has(.day-anchor:target)) .day-picker a:first-child,.panel-days:has(#day-1:target) a[href="#day-1"]{background:#b94d2a;color:#fff;border-color:#b94d2a}
.daily-view{display:none}.panel-days:not(:has(.day-anchor:target)) .daily-view:first-of-type,.panel-days .daily-view:target{display:block}.daily-banner{position:relative;border-radius:18px;overflow:hidden;height:180px;margin:20px 0 16px;background:#326b5c}.daily-banner img{width:100%;height:100%;object-fit:cover}.daily-banner:after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,#092d27b8,transparent 85%)}.daily-banner-title{position:absolute;z-index:1;left:30px;bottom:24px;color:#fff;border-left:3px solid #e8ead1;padding-left:20px;max-width:85%}.daily-banner-title small{letter-spacing:3px;font:italic 22px Georgia,serif}.daily-banner-title h3{font:700 30px/1.3 Georgia,'Songti SC',SimSun,serif;margin:8px 0 0;overflow-wrap:anywhere}.daily-image-note{position:absolute;right:12px;bottom:10px;background:#193c38c9;color:#fff;padding:2px 9px;border-radius:6px;font-size:11px;z-index:2}
.daily-date{color:#326b5c;margin:18px 0 12px;font-size:15px}.daily-stops{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 24px}.daily-stop{min-width:0;background:#fffefa;border:1px solid #d8ddcf;border-radius:16px;padding:16px;box-shadow:0 3px 8px #193c3809}.daily-stop-heading{display:flex;gap:14px;align-items:center;margin-bottom:12px}.daily-stop-heading span{background:#bb623f;color:#fff;border-radius:16px 6px 16px 6px;padding:3px 14px;font-size:14px;flex-shrink:0}.daily-stop-heading h4{font:700 23px/1.4 Georgia,'Songti SC',SimSun,serif;margin:0;overflow-wrap:anywhere}.daily-stop-content{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:18px}.daily-stop-photo{position:relative;min-height:140px;overflow:hidden;border-radius:12px}.daily-stop-photo img{position:absolute;width:100%;height:100%;object-fit:cover}.daily-stop-copy{min-width:0}.daily-stop-copy p{font-size:14px;line-height:1.8;margin:0 0 10px;overflow-wrap:anywhere}.daily-stop-copy .daily-travel{display:inline-block;background:#e8efe2;color:#285b48;border-radius:14px;padding:4px 10px;font-size:12px}.daily-stop-copy .daily-cost{color:#63736c;font-size:12px;margin:0}.daily-notes{padding:16px 20px;margin:18px 0;background:#eef1e6;border-radius:12px;font-size:14px;color:#40604e}.daily-notes li+li{margin-top:6px}.daily-break{text-align:center;color:#63736c;font-size:14px;margin:20px 0 28px}.daily-empty{padding:24px;background:#fffefa;border-radius:12px}
.result{background:#faf8f3;border:0;border-radius:0;padding:0}.daily-masthead .actions{margin-left:auto}.daily-masthead .actions .btn{font-size:13px;padding:7px 12px;color:#fff;background:#287a70;border:1px solid #287a70}.daily-masthead .actions .btn.ghost{color:#285b48;background:transparent;border-color:#9db7a7}.daily-masthead strong{font:700 34px Georgia,serif}.daily-masthead span{min-width:0;overflow-wrap:anywhere;border-left:1px solid #849d8b;padding-left:22px;font:22px Georgia,'Songti SC',SimSun,serif}.result .daily-masthead{display:flex;align-items:center;gap:24px;border-bottom:1px solid #a8b7a6;padding:0 12px 16px}.result .result-nav{justify-content:space-between;gap:20px;margin-bottom:22px}.result .result-nav a{font-family:Georgia,'Songti SC',SimSun,serif;color:#193c38}.daily-heading{align-items:center;margin-bottom:14px}.daily-heading p{font-family:Georgia,'Songti SC',SimSun,serif;color:#285b48}.daily-heading .day-picker{margin:0 0 0 auto}.daily-heading .day-picker a{font-size:14px;padding:7px 14px}.daily-heading h2{font-size:38px}.daily-banner{height:160px;margin-top:12px}.daily-banner-title h3{font-size:34px}.daily-stop{position:relative;padding:12px 16px}.daily-stop-heading{margin-bottom:8px}.daily-stop-photo{min-height:126px}.daily-stop-heading span{font-family:Georgia,'Songti SC',SimSun,serif;background:linear-gradient(100deg,#c97853,#b95b37);border-radius:48% 19% 39% 15%}.daily-stop-copy p{line-height:1.65}.daily-notes{background:transparent;padding:0 4px;margin:14px 0;color:#63736c;font-size:12px}.daily-notes summary{cursor:pointer}.daily-notes ul{padding-left:20px}.daily-break{display:flex;align-items:center;justify-content:center;gap:20px;margin:14px 0}.daily-break:before,.daily-break:after{content:'';height:1px;background:#b8c8b4;flex:1;max-width:130px}.daily-footer{display:grid;grid-template-columns:1fr 1fr;gap:24px;border-radius:16px;background:linear-gradient(110deg,#f7e8d9,#f2efe4);padding:16px 22px;font-size:13px}.daily-footer p{margin:0;display:flex;align-items:baseline;gap:14px}.daily-footer strong{white-space:nowrap;font-size:17px;color:#b94d2a}.daily-footer p+p{border-left:1px solid #a6b9a1;padding-left:24px}.daily-footer p+p strong{color:#087f7a}.daily-footer a{color:inherit}.daily-stop:nth-child(odd):not(:last-child):after{content:'→';position:absolute;right:-23px;top:50%;color:#b94d2a;font-size:23px}
body main{max-width:1586px;padding:24px 30px 36px}.panel-pitfalls>.daily-heading{margin-bottom:24px}

@media(min-width:1000px){.panel-days .day-picker{justify-content:flex-end}.daily-heading{margin-bottom:0}}
@media(max-width:800px){.daily-stops{grid-template-columns:1fr}.daily-stop:after{display:none}.daily-footer{grid-template-columns:1fr;gap:14px}.daily-footer p+p{border-left:0;border-top:1px solid #cad3bd;padding:14px 0 0}.daily-masthead{flex-wrap:wrap}.daily-masthead span{font-size:16px}.daily-heading .day-picker{margin:0;width:100%}body main{padding:16px}.daily-heading h2{font-size:28px}.daily-heading{gap:12px}.daily-banner{height:160px}.daily-banner-title{left:18px}.daily-banner-title h3{font-size:26px}.panel-days .day-picker{flex-wrap:nowrap;overflow-x:auto;padding-bottom:8px}.day-picker a{flex-shrink:0}.day-picker span{max-width:110px}}
@media(max-width:420px){.daily-stop-content{grid-template-columns:1fr}.daily-stop-photo{height:150px}.daily-stop-heading h4{font-size:21px}}
@media print{.panel-days .daily-view{display:block!important}.daily-stops{display:block}.daily-stop{break-inside:avoid;margin-bottom:12px}.daily-banner{height:140px}.daily-stop-photo{min-height:120px}}
"""


def scenery(place, inline_images):
    name = ('cities/hangzhou.webp' if any(w in place for w in ('西湖', '杭州', '雷峰')) else
            'mountains.webp' if any(w in place for w in ('山', '茶', '峰', '林')) else
            'town.webp' if any(w in place for w in ('寺', '庙', '街', '镇', '馆')) else 'coast.webp')
    if inline_images:
        return 'data:image/webp;base64,' + b64encode((Path(__file__).with_name('images') / name).read_bytes()).decode('ascii')
    return '/assets/visual/' + name


def day_cards(day, number, text, inline_images=False):
    rows = day.get('rows', [])
    title = next((r[1] for r in rows if len(r) > 1), '当日安排')
    photo = lambda place: text(scenery(place, inline_images))
    out = [f'<style>.panel-days:has(#day-{number}:target) .day-picker a[href="#day-{number}"]' + '{background:#b94d2a;color:#fff;border-color:#b94d2a}</style>', f'<article id="day-{number}" class="day-anchor daily-view" aria-label="第 {number} 天">',
           f'<p class="daily-date">{text(day["title"])}</p>',
           f'<fieldset class="day-plan-choice"><legend>第 {number} 天 · 选择当日路线</legend><label><input type="radio" name="day-plan-{number}" value="original" checked>原定行程</label><label><input class="rain-choice" type="radio" name="day-plan-{number}" value="rain">雨天方案</label></fieldset>',
           f'<div class="original-route"><header class="daily-banner"><img src="{photo(title)}" alt="风景示意图，非景点实拍"><div class="daily-banner-title"><small>DAY {number:02d}</small><h3>{text(title)}</h3></div><span class="daily-image-note">风景示意</span></header>']
    out.append(stop_cards(rows, photo, text))
    if not rows:
        out.append('<p class="daily-empty">当天尚无具体安排，可返回对话补充。</p>')
    if day.get('items'):
        out.append('<details class="daily-notes"><summary>当日费用与安排说明</summary><ul>' + ''.join('<li>' + text(item['text']) + '</li>' for item in day['items']) + '</ul></details>')
    out.append('</div><div class="rain-route"><h3>雨天方案 · 当日路线</h3>')
    if day.get('rain_rows'):
        out.append('<p class="rain-note">' + text(day.get('rain_note') or '以下为普通雨天的当日安排，请确认场馆预约后再切换出行。') + '</p>')
        out.append(stop_cards(day['rain_rows'], photo, text))
    else:
        out.append('<p class="daily-empty rain-unavailable">本版尚无完整雨天路线。请在对话中提出“补充第' + str(number) + '天雨天方案”，保留已订交通、住宿与用餐安排后再调整。</p>')
    # shortcut: rain selection previews the day; sync budget, maps and exports when it becomes a saved plan change.
    out.append('<p class="rain-notice">适用于普通降雨；暴雨、台风、停运或闭馆时，请按当地公告暂停或调整出行。此处切换用于查看路线，预算明细、景点地图与 PDF / Markdown 导出仍对应原定行程，不会修改预订。</p></div>')
    return ''.join(out) + '<p class="daily-break">沿途适当休息，给风景留一点时间。</p><aside class="daily-footer" aria-label="当日提示"><p><strong>♧ 当日提醒</strong><span>活动卡片中查看预约与交通提醒，<a href="#panel-pitfalls">查看避坑指南 ↗</a></span></p><p><strong>☂ 雨天方案</strong><span>在当天上方切换查看，出行前确认开放与预约情况。</span></p></aside></article>'


def stop_cards(rows, photo, text):
    out = ['<ol class="daily-stops">']
    for row in rows:
        when, place, detail, travel, cost = (list(row) + [''] * 5)[:5]
        out.append(f'<li class="daily-stop"><div class="daily-stop-heading"><span>{text(when)}</span><h4>{text(place)}</h4></div><div class="daily-stop-content"><div class="daily-stop-photo"><img src="{photo(place)}" alt="风景示意图，非景点实拍" loading="lazy"><span class="daily-image-note">风景示意</span></div><div class="daily-stop-copy"><p>{text(detail).replace(chr(10), "<br>")}</p><p class="daily-travel">{text(travel)}</p><p class="daily-cost">全员费用 · {text(cost)}</p></div></div></li>')
    out.append('</ol>')
    return ''.join(out)
