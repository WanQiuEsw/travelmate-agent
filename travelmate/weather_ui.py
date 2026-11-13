"""Weather view over saved forecast fields; no additional network requests."""
from base64 import b64encode
from pathlib import Path
from datetime import date
import re


WEATHER_CSS = """
.weather-shell{background:#fffefa;border:1px solid #d8e1d8;box-shadow:0 8px 24px #193c380a;border-radius:24px;padding:28px;color:#193c38;margin:12px 0}
.weather-shell h2{color:#193c38;border-left:5px solid #0b8c74;padding-left:16px;margin:0;font-size:28px}.weather-heading{display:flex;gap:24px;align-items:center;margin-bottom:26px;flex-wrap:wrap}.weather-heading p{margin:0;color:#60786e}
.weather-choice{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}.weather-scene{display:none;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:28px}.weather-hero{position:relative;isolation:isolate;overflow:hidden;min-height:355px;border-radius:20px;background:linear-gradient(145deg,#087c85,#299e98 55%,#7ec3b1);padding:32px;display:flex;flex-direction:column;justify-content:space-between;color:white}.weather-hero:after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,transparent 40%,#064c4a55);z-index:-1}.weather-hero h3{font-size:34px;margin:0;color:white}.weather-hero p{margin:8px 0;color:#f0fff9}.weather-hero .weather-art{position:absolute;width:55%;height:auto;right:-2%;top:24%;filter:drop-shadow(0 15px 20px #2354aa44);z-index:-1}.weather-temp{font-size:clamp(56px,6vw,88px);font-weight:650;line-height:1.15;letter-spacing:-3px}.weather-low{font-size:28px;color:#dff6ee;letter-spacing:0;font-weight:400}.weather-condition{font-size:22px}.weather-hero .weather-unavailable{font-size:30px;letter-spacing:0}
.weather-scenery{position:absolute;inset:auto 0 0;width:100%;height:62%;object-fit:cover;opacity:.7;mask-image:linear-gradient(transparent,#000 32%);z-index:-2}.weather-hero>div{position:relative;z-index:1;text-shadow:0 2px 12px #073f3e33}.weather-hero .weather-art{width:42%;right:0;top:20%}
.weather-side{min-width:0;display:flex;flex-direction:column;gap:18px}.weather-dates{display:flex;gap:10px;overflow-x:auto;padding:3px 3px 10px}.weather-date{flex:1 0 88px;max-width:150px;display:flex;align-items:center;flex-direction:column;gap:6px;border:1px solid #d1ded5;border-radius:17px;padding:14px 10px;cursor:pointer;background:#fffefa;color:#345c50;font-size:14px}.weather-date svg{width:42px;height:34px}.weather-date.active{background:linear-gradient(135deg,#eaf6ec,#d6ede0);color:#154c3d;border-color:#198c6c;box-shadow:0 5px 15px #1674510a}.weather-date small{font-size:12px}.weather-date:hover{border-color:#198c6c}.weather-metrics{margin:0;display:grid;grid-template-columns:auto 1fr;gap:17px 16px;align-items:center;font-size:16px}.weather-metrics dt{color:#60786e}.weather-metrics dd{margin:0;text-align:right;overflow-wrap:anywhere}.weather-divider{grid-column:1/-1;border-top:1px solid #dce5dc}.weather-advice{display:flex;gap:14px;align-items:center;border:1px solid #d9e9dc;border-radius:16px;padding:18px 22px;margin:24px 0 0;background:#e9f4ec;color:#234d3e;line-height:1.7}.weather-advice span{font-size:25px;color:#168367}.weather-footer{font-size:12px;color:#667f71;margin:20px 0 0;line-height:1.8}.weather-history{color:#60786e;line-height:1.8}
@media(max-width:700px){.weather-shell{padding:18px;border-radius:18px}.weather-heading{gap:8px;margin-bottom:18px}.weather-heading h2{font-size:24px}.weather-heading p{font-size:13px}.weather-scene{grid-template-columns:1fr;gap:20px}.weather-hero{min-height:285px;padding:24px}.weather-hero h3{font-size:28px}.weather-temp{font-size:72px}.weather-metrics{font-size:15px}.weather-date{max-width:none}.weather-advice{padding:14px;font-size:14px}}
@media print{.weather-shell{background:white;color:#193c38;border-color:#ccd4cb}.weather-shell h2,.weather-hero h3{color:#193c38}.weather-shell .weather-scene{display:grid!important;margin-bottom:20px;break-inside:avoid}.weather-dates,.weather-choice{display:none}.weather-hero{background:#eaf3ee;min-height:220px;color:#193c38}.weather-hero p,.weather-low,.weather-metrics dt,.weather-heading p,.weather-footer,.weather-history{color:#425b60}.weather-advice{color:#193c38;background:white}.weather-hero .weather-art{opacity:.6}}
"""


def weather_icon(condition):
    # Reusable inline art keeps offline exports self-contained.
    if not condition:
        art = '<text x="60" y="65" text-anchor="middle" fill="#b5c8dc" font-size="48">—</text>'
    elif '雨' in condition:
        art = '<path d="M30 63h61a17 17 0 0 0-2-34 25 25 0 0 0-47-2 18 18 0 0 0-12 36" fill="#d3e7df"/><path d="m40 74-5 10m25-10-5 10m25-10-5 10" stroke="#75bcff" stroke-width="5" stroke-linecap="round"/>'
    elif '雪' in condition:
        art = '<text x="60" y="72" text-anchor="middle" fill="#d3e7df" font-size="72">❄</text>'
    else:
        art = ('<circle cx="69" cy="37" r="25" fill="#ffe090"/>' if '晴' in condition or '多云' in condition else '')
        if '云' in condition or '阴' in condition or '雾' in condition:
            art += '<path d="M25 77h68a19 19 0 0 0-2-38 26 26 0 0 0-49-2 20 20 0 0 0-17 40" fill="#e3f1eb" stroke="#609787" stroke-width="2"/>'
    return '<svg class="weather-art" viewBox="0 0 120 100" aria-hidden="true">' + art + '</svg>'


def weather_panel(meta, days, selected_date, text):
    out = ['<div class="weather-shell"><header class="weather-heading"><h2>出行天气</h2>']
    rows = meta.get('weather') or []
    city = next((row.get('city') for row in rows if row.get('city')), '')
    out.append('<p>' + text(' · '.join(filter(None, (city, selected_date)))) + ' · 保存时的预报</p></header>')
    if not rows:
        # shortcut: 旧快照只解析程序曾生成的固定标题格式，不从自由文本猜天气。
        out.append('<details class="weather-history"><summary>查看历史天气记录</summary><p>历史方案未保存结构化天气详情，以下保留原有记录。</p>')
        out.extend('<p>' + text(day['title']) + '</p>' for day in days)
        out.append('</details>')
        for day in days:
            match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', day['title'])
            if not match:
                continue
            try:
                value = date(*map(int, match.groups())).isoformat()
            except ValueError:
                continue
            row = {'date': value}
            forecast = re.search(r'天气预报：白天([^，]+)，夜间([^，]+)(?:，(-?\d+(?:\.\d+)?)至(-?\d+(?:\.\d+)?)℃)?', day['title'])
            if forecast:
                row.update(zip(('dayweather', 'nightweather', 'nighttemp', 'daytemp'), forecast.groups()))
            rows.append(row)
    image = next((Path(__file__).with_name('images') / 'cities' / (name + '.webp')
                  for name, label in (('hangzhou', '杭州'), ('beijing', '北京'), ('shanghai', '上海'),
                                      ('xian', '西安'), ('chengdu', '成都'), ('guangzhou', '广州'), ('xiamen', '厦门'))
                  if label in city), None)
    scenery = ('<img class="weather-scenery" alt="目的地风景示意图，非实时天气照片" src="data:image/webp;base64,'
               + b64encode(image.read_bytes()).decode('ascii') + '">' if image and image.is_file() else '')
    labels = []
    for i, row in enumerate(rows):
        try:
            moment = date.fromisoformat(row.get('date') or '')
            labels.append((f"星期{'一二三四五六日'[moment.weekday()]}", f'{moment.month}月{moment.day}日'))
        except ValueError:
            labels.append((f'第{i+1}天', '日期未定'))
        out.append(f'<input class="weather-choice" type="radio" name="weather-day" id="weather-{i}" aria-label="查看{ text(row.get("date") or str(i+1)) }天气" {"checked" if i == 0 else ""}>')
    rules = ''.join(f'.weather-shell:has(#weather-{i}:checked) .weather-scene-{i}' + '{display:grid}'
                    + f'.weather-shell:has(#weather-{i}:focus-visible) label[for="weather-{i}"]' + '{outline:3px solid #198c6c;outline-offset:3px}' for i in range(len(rows)))
    out.append('<style>' + rules + '</style>')
    temp = lambda value: text(str(value)) + '°' if value is not None and value != '' else '—'
    for i, row in enumerate(rows):
        condition = row.get('dayweather') or ''
        unavailable = '超出预报范围' if i < len(days) and '超出预报范围' in days[i]['title'] else '暂无预报'
        out.append(f'<article class="weather-scene weather-scene-{i}" aria-label="{text(row.get("date") or labels[i][0])}天气详情"><div class="weather-hero"><div><h3>{labels[i][0]}</h3><p>{labels[i][1]} · {text(city)}</p></div>' + scenery + weather_icon(condition))
        out.append('<div><div class="weather-temp' + ('' if condition else ' weather-unavailable') + '">' + (temp(row.get('daytemp')) if condition else unavailable) + '<span class="weather-low"> / ' + temp(row.get('nighttemp')) + '</span></div><p class="weather-condition">' + text(condition or '未取得该日天气，出行前请复查') + '</p></div></div><div class="weather-side"><div class="weather-dates">')
        for j, other in enumerate(rows):
            out.append(f'<label class="weather-date{" active" if i == j else ""}" for="weather-{j}">' + weather_icon(other.get('dayweather')) + f'<strong>{labels[j][0]}</strong><small>{labels[j][1]}</small><span>{temp(other.get("daytemp"))} / {temp(other.get("nighttemp"))}</span></label>')
        out.append('</div><dl class="weather-metrics">')
        for title, value in [('白天', text(row.get('dayweather') or '暂无数据') + ' · ' + temp(row.get('daytemp'))),
                             ('夜间', text(row.get('nightweather') or '暂无数据') + ' · ' + temp(row.get('nighttemp'))),
                             ('风力', ' '.join(str(v) for v in (row.get('daywind'), (str(row['daypower']) + '级') if row.get('daypower') else None) if v) or '暂无数据'),
                             ('降水概率', '暂无数据'), ('湿度', '暂无数据')]:
            if title == '风力':
                out.append('<div class="weather-divider"></div>')
            out.append('<dt>' + title + '</dt><dd>' + (value if title in ('白天', '夜间') else text(value)) + '</dd>')
        out.append('</dl></div></article>')
    out.append('<p class="weather-advice"><span aria-hidden="true">☂</span>出发前复查预报；遇雨可选择室内备选，户外活动预留调整时间。</p><p class="weather-footer">预报查询时间：' + text('；'.join(dict.fromkeys(meta.get('weather_times', []))) or '本版未记录可用查询时间') + ' · 天气为预报而非保证；未提供的指标不作推测。</p></div>')
    return ''.join(out)
