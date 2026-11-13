"""Budget cards and local-only calculations over the saved expense ledger."""
from decimal import Decimal, ROUND_HALF_UP


def icon(kind):
    paths = {
        'bed': '<path d="M3 18v-9m18 9v-6H3m3 0V7h5v5m2 0V7h5a3 3 0 0 1 3 3v2M3 18v3m18-3v3"/>',
        'train': '<rect x="5" y="3" width="14" height="16" rx="4"/><path d="M5 11h14M9 3v8m6-8v8M8 22l2-3m6 3-2-3M8 15h1m6 0h1"/>',
        'food': '<path d="M5 3v7m4-7v7M3 3v5a4 4 0 0 0 8 0V3M7 12v9m12 0V3c-5 2-5 11 0 11"/>',
        'ticket': '<path d="M3 7l15-3 3 5a3 3 0 0 0 0 6l-3 5-15-3v-4a3 3 0 0 0 0-6Z"/>',
        'coins': '<ellipse cx="9" cy="12" rx="6" ry="3"/><path d="M3 12v7c0 4 12 4 12 0v-7m-12 4c0 4 12 4 12 0m-6-7V6c0-4 12-4 12 0v8c0 2-3 3-6 3M9 6c0 4 12 4 12 0"/>',
        'people': '<circle cx="9" cy="7" r="4"/><path d="M2 21v-3c0-6 14-6 14 0v3ZM17 3c5 0 5 8 0 8m2 3c3 1 3 4 3 7"/>',
        'edit': '<path d="m15 4 5 5M3 21l5-1L21 7a2 2 0 0 0-5-5L4 15Z"/>',
        'reset': '<path d="M3 10a9 9 0 0 1 16-5l2 3M3 4v6h6m12 4a9 9 0 0 1-16 5l-2-3m18 6v-6h-6"/>',
        'alert': '<circle cx="12" cy="12" r="10"/><path d="M12 6v7m0 4v1"/>',
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths.get(kind, paths['ticket']) + '</svg>'


def panel(meta, text):
    ledger = meta['ledger']
    categories = list(dict.fromkeys(['酒店住宿', '交通费用', '餐饮费用', '景点门票'] + [r['category'] for r in ledger]))
    labels = {'酒店住宿': ('住宿', 'bed'), '交通费用': ('交通', 'train'), '餐饮费用': ('餐饮', 'food'), '景点门票': ('景点', 'ticket')}
    cents = lambda v: int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    money = lambda v: f'¥{v / 100:,.2f}'
    known = {r['category'] for r in ledger if r['amount'] is not None}
    pending = {r['category'] for r in ledger if r['amount'] is None}
    totals = {c: sum(cents(r['amount']) for r in ledger if r['category'] == c and r['amount'] is not None) for c in categories}
    total = sum(totals.values())
    unknown = sum(r['amount'] is None for r in ledger)
    travelers = meta.get('travelers') or 1
    budget = cents(meta['budget']) if meta.get('budget') is not None and meta.get('budget_currency', 'CNY') == 'CNY' else None
    limit = (f'<label class="budget-limit-value"><span>¥</span><input data-budget-limit type="number" min="0" max="100000000" step="0.01" value="{budget / 100:.2f}" aria-label="行程总预算上限"></label>'
             if budget is not None else '<b>待确认</b>')
    currency = meta.get('budget_currency', 'CNY')
    scope = ('人民币' if currency == 'CNY' else currency) + ' · ' + meta.get('budget_includes', '范围待确认')
    def expense(row, i):
        name = '其他综合费用' if row['category'] == '综合费用' and not row.get('split') else row['name']
        description = (row.get('detail') or row['name']).replace('other_cost', '其他费用')
        value = f'{cents(row["amount"])/100:.2f}' if row['amount'] is not None else ''
        detail = text(description)
        if len(description) > 90:
            detail = '<details class="expense-explanation"><summary>费用说明</summary><p>' + detail + '</p></details>'
        return (f'<tr data-category="{text(row["category"])}" data-order="{i}"><td><input type="checkbox" {"checked" if value else ""} aria-label="计入{text(name)}"></td>'
                f'<td>{text(name)}<small>{text(row["status"])}</small></td><td><label class="budget-money"><span>¥</span><input type="number" min="0" max="100000000" step="0.01" value="{value}" placeholder="待核实" aria-label="{text(name)}全员费用"></label></td><td>{detail}</td></tr>')
    out = [f'<div class="budget-workspace" data-travelers="{travelers}" data-limit="{budget if budget is not None else ""}"><header class="budget-heading"><h2>{icon("coins")}预算明细</h2><p>每一笔心里有数，把钱花在喜欢的地方。</p><span class="budget-leaf">❧ 设计参考</span><span class="budget-scope">预算范围：全员 · {text(scope)}</span><small>ⓘ 含待核实项目，最终费用可能变化。</small></header>',
           f'<section class="budget-overview" aria-label="费用汇总"><div class="budget-party">{icon("people")}<strong>{travelers} 人出行</strong></div><div class="budget-limit"><strong>行程总预算（上限）</strong>{limit}</div><div class="budget-distribution"><h3>已列估算费用：<strong data-total>{money(total) if total or not unknown else "待核实"}</strong> <small>（不含待核实项目）</small></h3><div class="budget-bar" aria-label="费用占比">']
    bar_categories = ['交通费用', '酒店住宿', '餐饮费用', '景点门票'] + [c for c in categories if c not in labels]
    for c in bar_categories:
        out.append(f'<span data-segment="{text(c)}" style="flex-grow:{totals[c]};" class="budget-color-{categories.index(c) % 6}"><span class="budget-segment-label">{money(totals[c])}</span></span>')
    balance = max(0, (budget or total) - total)
    out.append(f'<span data-balance-bar style="flex-grow:{balance}" class="budget-color-balance"><span class="budget-segment-label">{money(balance)}</span></span></div><div class="budget-legend">')
    for c in bar_categories:
        out.append(f'<span><i class="budget-color-{categories.index(c) % 6}"></i>{text(labels.get(c, (c,))[0])} <b data-category-total="{text(c)}">{money(totals[c]) if c in known else '待核实' if c in pending else '未单列'}</b></span>')
    out.append(f'<span><i class="budget-color-balance"></i>余量 <b data-balance>{money(balance) if budget is not None else "待确认"}</b></span></div></div><div class="budget-metrics"><p>{icon("people")}人均 <strong data-person>{money(int((Decimal(total) / travelers).quantize(Decimal("1"), rounding=ROUND_HALF_UP))) if total or not unknown else "待核实"}</strong><small>（估算）</small></p><p data-budget-notice role="status">{icon("alert")}<strong data-unknown>{unknown} 项待核实</strong></p></div></section>')
    out.append('<div class="budget-toolbar"><label>类型筛选：<select data-budget-filter aria-label="筛选费用类型"><option value="">全部类型</option>' + ''.join(f'<option>{text(c)}</option>' for c in categories) + '</select></label><label>排序方式：<select data-budget-sort aria-label="排序费用"><option value="desc" selected>金额从高到低</option><option value="original">日程顺序</option><option value="asc">金额从低到高</option></select></label><small>ⓘ 本页试算，不修改已保存方案。</small><button type="button" data-budget-reset>' + icon('reset') + '恢复方案金额</button></div><div class="budget-cards" aria-label="逐项费用">')
    for c in categories:
        title, symbol = labels.get(c, (c, 'coins'))
        rows = [(i, r) for i, r in enumerate(ledger) if r['category'] == c and r['amount'] is not None]
        if not rows and c not in labels:
            continue
        rows.sort(key=lambda pair: -pair[1]['amount'])
        out.append(f'<section class="budget-category" data-card="{text(c)}"><header><span class="budget-category-icon">{icon(symbol)}</span><h3>{text(title)}</h3><p>小计：<strong data-card-total="{text(c)}">{money(totals[c])}</strong><small>（估算）</small></p><button type="button" data-edit-category aria-label="编辑{text(title)}费用">{icon("edit")}</button></header><div class="budget-table-scroll"><table><thead><tr><th>计入</th><th>费用项目</th><th>金额（估算）</th><th>费用说明</th></tr></thead><tbody data-ledger>')
        out.extend(expense(r, i) for i, r in rows)
        if not rows:
            out.append('<tr class="budget-empty"><td colspan="4">暂无已列费用，未单列金额不视为免费。</td></tr>')
        out.append('</tbody></table></div></section>')
    out.append('</div><section class="budget-pending"><header>' + icon('alert') + f'<h3>待核实项目（{unknown} 项）</h3><p>查清价格后再计入试算。</p></header><div class="budget-table-scroll"><table><tbody data-ledger>')
    out.extend(expense(r, i) for i, r in enumerate(ledger) if r['amount'] is None)
    if not unknown:
        out.append('<tr><td>暂无待核实项目。</td></tr>')
    out.append('</tbody></table></div></section><p class="budget-footnote">人均已列费用按同行人数计算；未知金额不按免费处理。<noscript>启用 JavaScript 后可筛选、排序和试算。</noscript></p></div>')
    return ''.join(out)


CSS = """
.budget-brand-mark{display:none}.result:has(#panel-budget:target) .budget-brand-mark{display:inline-block;width:58px;height:36px;margin-right:12px;vertical-align:middle}.budget-header-art{display:none}.result:has(#panel-budget:target){position:relative}.result:has(#panel-budget:target) .budget-header-art{display:block;position:absolute;right:-20px;top:-15px;width:440px;height:115px;opacity:.7;pointer-events:none}.result:has(#panel-budget:target) .daily-masthead{position:relative;z-index:1}.result:has(#panel-budget:target) .daily-masthead .actions{margin-right:310px}@media(max-width:1200px){.result:has(#panel-budget:target) .daily-masthead .actions{margin-right:0}.result:has(#panel-budget:target) .budget-header-art{opacity:.25}}@media(max-width:760px){.result:has(#panel-budget:target) .budget-header-art{display:none}.result:has(#panel-budget:target) .budget-brand-mark{width:40px;margin-right:8px}}

body:has(#panel-budget:target) main{max-width:1600px;padding:14px 24px 32px}body:has(#panel-budget:target){background:radial-gradient(ellipse at top right,#f3efdf55,transparent 60%),#faf8f3}.result:has(#panel-budget:target) .daily-masthead{padding:0 22px 12px;border:0}.result:has(#panel-budget:target) .daily-masthead strong{font-size:36px}.result:has(#panel-budget:target) .result-nav{justify-content:flex-start;gap:56px;padding:0 38px;margin:0;border-bottom:1px solid #bcc8be}.result:has(#panel-budget:target) .result-nav a{font-size:19px;padding:12px 10px}.result:has(#panel-budget:target) .daily-masthead .btn{background:#fffdf9;color:#165b50;border:1px solid #65958a;border-radius:10px}.budget-workspace{display:block;margin:0;color:#132f2a;font-size:16px}.budget-workspace svg{width:28px;height:28px;flex-shrink:0}.budget-heading{display:flex;align-items:center;gap:20px;flex-wrap:wrap;padding:23px 20px 20px}.budget-heading h2{border:0;padding-left:0;display:flex;align-items:center;gap:18px;font-size:36px;line-height:1.3;margin:0;color:#073f36}.budget-heading h2 svg{width:42px;height:42px;color:#a24e35}.budget-heading p{margin:0;color:#666;font-size:18px}.budget-leaf,.budget-scope{border:1px solid #d4ddbf;border-radius:15px;padding:2px 13px;background:#f3f6e9;font-size:14px}.budget-leaf{color:#4d7040}.budget-scope{margin-left:auto}.budget-heading>small{color:#73716d;font-size:14px}.budget-overview{display:grid;grid-template-columns:145px minmax(190px,230px) minmax(0,1fr) minmax(210px,245px);align-items:center;gap:24px;background:#ffffffc9;border:1px solid #e5e0d6;border-radius:18px;padding:20px 18px;box-shadow:0 4px 10px #493c2310}.budget-party{display:flex;align-items:center;gap:16px;padding:12px 22px 12px 10px;border-right:1px solid #dad8d0;white-space:nowrap;font-size:20px}.budget-party svg{width:36px;height:36px;color:#14695e}.budget-limit{min-width:0;padding-right:16px;border-right:1px solid #dad8d0;line-height:1.5}.budget-limit>strong{font-size:18px}.budget-limit b{display:block;color:#b44017;font-size:46px;line-height:1.4;font-weight:650}.budget-distribution{min-width:0}.budget-distribution h3{margin:0 0 10px;font-size:19px;font-weight:600}.budget-distribution h3 strong{font-size:24px;color:#333}.budget-distribution h3 small{font-size:14px;font-weight:400;color:#555}.budget-bar{display:flex;width:100%;height:33px;overflow:hidden;border-radius:9px;background:#ecebdf}.budget-bar>span{flex-basis:0;min-width:0;overflow:hidden;text-align:center;font-size:17px;line-height:33px;color:white;font-weight:600;white-space:nowrap;transition:flex-grow .2s}.budget-color-0{background:linear-gradient(100deg,#537f5c,#43836c)}.budget-color-1{background:linear-gradient(100deg,#19675f,#0a514d)}.budget-color-2{background:linear-gradient(100deg,#d3ab63,#c5964b)}.budget-color-3{background:linear-gradient(100deg,#b77c68,#a56d60)}.budget-color-4{background:#8b9e88}.budget-color-5{background:#999270}.budget-color-balance{background:#cfd5b7;color:#3f443a!important}.budget-legend{display:flex;gap:14px;justify-content:space-between;margin-top:10px;font-size:13px;flex-wrap:wrap}.budget-legend>span{display:flex;align-items:center;gap:5px}.budget-legend i{width:15px;height:15px;border-radius:3px}.budget-legend b{font-weight:400}.budget-metrics{border-left:1px solid #dad8d0;padding-left:24px}.budget-metrics p{display:flex;align-items:center;justify-content:center;gap:9px;border-radius:15px;background:#e7f1eb;margin:0;padding:5px 8px;font-size:19px;white-space:nowrap}.budget-metrics p+p{background:#fbe8dd;color:#b44620;margin-top:10px;justify-content:flex-start;padding-left:18px}.budget-metrics strong{font-size:26px}.budget-metrics small{font-size:14px}.budget-metrics [data-unknown]{font-size:21px}.budget-toolbar{display:flex;flex-wrap:wrap;border:1px solid #e5e0d6;background:#ffffff66;border-radius:15px;margin:14px 0;padding:12px 18px;align-items:center;gap:24px;color:#333}.budget-toolbar label{display:flex;align-items:center;gap:8px;white-space:nowrap}.budget-toolbar label+label{border-left:1px solid #e7e3da;padding-left:22px}.budget-toolbar select{background:#fffefa;min-width:150px;font:inherit;padding:5px 12px;color:#252e2a;border-color:#c4c4b8}.budget-toolbar>small{margin-left:auto;color:#777;font-size:14px}.budget-toolbar button{display:flex;align-items:center;gap:8px;background:#fffefa;border:1px solid #287569;border-radius:9px;color:#176557;padding:7px 14px;font:inherit;cursor:pointer}.budget-toolbar button svg{width:23px;height:23px}.budget-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 14px}.budget-category{min-width:0;background:linear-gradient(120deg,#fff,#fbfcfc);border:1px solid #d7d5ca;border-radius:17px;padding:5px 16px 16px;box-shadow:0 3px 7px #493c2310;min-height:172px}.budget-category>header{display:flex;align-items:center;gap:12px;margin-bottom:6px;min-height:45px}.budget-category-icon{display:flex;align-items:center;justify-content:center;background:linear-gradient(120deg,#e4f2e8,#e9eed9);color:#08735a;border-radius:15px;width:62px;height:44px}.budget-category-icon svg{width:33px;height:33px}.budget-category h3{font-size:25px;margin:0;color:#073c32}.budget-category header p{margin:0 0 0 26px;font-size:18px;color:#242424}.budget-category header p strong{font-size:26px;color:#bc4318}.budget-category header small{color:#ba471f;font-size:15px}.budget-category button{margin-left:auto;background:none;border:0;color:#116c5a;padding:8px;cursor:pointer}.budget-table-scroll{overflow-x:auto}.budget-workspace table{margin:0;width:100%;table-layout:fixed;border-collapse:collapse;font-size:15px;color:#222;line-height:1.5}.budget-workspace th{min-width:0;background:#f1f0e9;font-weight:500;text-align:left;padding:5px 8px;border:0}.budget-workspace th:first-child{border-radius:8px 0 0 8px;width:10%}.budget-workspace th:nth-child(2){width:27%}.budget-workspace th:nth-child(3){width:21%}.budget-workspace th:last-child{border-radius:0 8px 8px 0}.budget-workspace td{min-width:0;padding:5px 8px;border:0;border-bottom:1px solid #e5e3db;vertical-align:top;overflow-wrap:anywhere}.budget-workspace tr:last-child td{border-bottom:0}.budget-workspace td:nth-child(2){font-weight:550}.budget-workspace td small{display:block;font-size:11px;color:#777;font-weight:400}.budget-workspace input[type=checkbox]{accent-color:#0b7865;width:19px;height:19px;cursor:pointer;vertical-align:middle}.budget-money{display:flex;align-items:center;border:1px solid #cccec4;border-radius:8px;background:linear-gradient(#fff,#fcfcfc);max-width:114px;padding:0 8px;line-height:26px}.budget-money input{font:inherit;color:#181c19;width:100%;min-width:0;padding:0;border:0;background:none;appearance:textfield;-moz-appearance:textfield}.budget-money input::-webkit-inner-spin-button{appearance:none}.budget-money:focus-within{outline:2px solid #25836e;outline-offset:2px}.budget-workspace tr:has(input[type=checkbox]:not(:checked)) td{color:#76726b}.budget-pending{border:1px solid #ffdbb4;border-radius:18px;background:linear-gradient(110deg,#fff3e3,#fce9d4);padding:7px 15px 12px;margin-top:20px}.budget-pending>header{display:flex;align-items:center;gap:12px;color:#ab3a10;margin:0 4px 8px}.budget-pending h3{font-size:22px;margin:0}.budget-pending header p{font-size:15px;border-left:1px solid #bf754b;padding-left:24px;margin:0 0 0 16px;color:#5b5347}.budget-pending .budget-table-scroll{background:#ffffff91;border-radius:14px;padding:5px 14px}.budget-pending td:first-child{width:5%}.budget-pending td:nth-child(2){width:22%}.budget-pending td:nth-child(3){width:18%}.budget-pending .budget-money{max-width:130px}.budget-footnote{font-size:12px;color:#817b6e;margin:8px 4px}.budget-source-notes{font-size:13px;color:#6c7266;margin-top:10px}.budget-source-notes>summary{cursor:pointer}.budget-empty{color:#888}.budget-workspace [hidden]{display:none!important}.budget-workspace button:focus-visible,.budget-workspace select:focus-visible{outline:2px solid #25836e;outline-offset:3px}
.budget-overview>*{min-width:0}.budget-party{padding-right:14px;gap:10px}.budget-limit-value{display:flex;align-items:baseline;min-width:0;color:#b44017;font-size:clamp(26px,2.8vw,42px);font-weight:650;line-height:1.5}.budget-limit-value input{width:100%;min-width:0;border:0;border-bottom:1px dashed #b4401740;padding:0;background:transparent;color:inherit;font:inherit;appearance:textfield}.budget-limit-value input::-webkit-inner-spin-button{appearance:none}.budget-limit-value input:focus-visible{outline:2px solid #25836e;border-radius:4px}.budget-metrics{padding-left:16px}.budget-metrics p{flex-wrap:wrap;gap:6px;white-space:normal}.budget-metrics strong{font-size:clamp(18px,1.8vw,25px);overflow-wrap:anywhere}.budget-heading .budget-scope{max-width:100%;overflow-wrap:anywhere}.budget-category>header{flex-wrap:wrap;row-gap:4px}.budget-category header p{margin-left:8px}.budget-category-icon{flex-shrink:0}.budget-category button{flex-shrink:0}.budget-bar>span{container-type:inline-size;container-name:budget-segment}.budget-segment-label{display:block;font-size:14px;overflow:hidden;white-space:nowrap}.budget-legend>span{white-space:nowrap}.budget-workspace tbody tr:nth-child(even){background:transparent}.budget-toolbar>small{flex:1 1 230px;text-align:right}.budget-toolbar button{flex-shrink:0}
@container budget-segment (max-width:80px){.budget-segment-label{visibility:hidden}}
@media(prefers-reduced-motion:reduce){.budget-bar>span{transition:none}}
@media(max-width:1350px) and (min-width:761px){.budget-overview{grid-template-columns:130px 200px minmax(0,1fr);gap:18px}.budget-metrics{grid-column:1/-1;border:0;padding:0;display:flex;gap:12px}.budget-metrics p{flex:1}.budget-metrics p+p{margin:0}.budget-category header small{font-size:12px}.budget-category header p{font-size:15px}}
@media(max-width:1200px){.budget-heading{gap:12px}.budget-heading .budget-scope{margin-left:0}.budget-overview{grid-template-columns:140px 180px 1fr;gap:16px}.budget-metrics{grid-column:1/-1;border:0;padding:0;display:flex;gap:16px}.budget-metrics p+p{margin:0}.budget-metrics p{flex:1}.budget-limit b{font-size:38px}.budget-category header p{margin-left:0}.budget-category h3{font-size:22px}.budget-category header p strong{font-size:23px}.budget-toolbar{gap:12px}.budget-toolbar>small{margin-left:0}.budget-toolbar label+label{padding-left:12px}}
@media(max-width:760px){body:has(#panel-budget:target) main{padding:12px}.result:has(#panel-budget:target){padding:0}.result:has(#panel-budget:target) .daily-masthead{padding:0 0 12px;gap:12px}.result:has(#panel-budget:target) .result-nav{padding:0;gap:20px}.result:has(#panel-budget:target) .result-nav a{font-size:16px;padding:10px 0}.budget-heading{padding:18px 0;gap:10px}.budget-heading h2{font-size:29px}.budget-heading p{font-size:14px}.budget-heading>small{font-size:12px}.budget-scope{max-width:100%;font-size:12px}.budget-overview{grid-template-columns:1fr 1fr;padding:16px;gap:14px}.budget-party{padding:5px;font-size:18px}.budget-limit{border:0}.budget-limit>strong{font-size:14px}.budget-limit b{font-size:34px}.budget-distribution{grid-column:1/-1}.budget-distribution h3{font-size:16px}.budget-distribution h3 strong{font-size:22px}.budget-distribution h3 small{display:block;font-size:12px}.budget-legend{gap:8px}.budget-metrics{gap:8px}.budget-metrics p{font-size:15px;gap:5px;padding:6px}.budget-metrics strong{font-size:21px}.budget-metrics svg{width:22px;height:22px}.budget-metrics small{font-size:11px}.budget-metrics [data-unknown]{font-size:16px}.budget-toolbar{padding:12px;gap:10px}.budget-toolbar label{width:100%;font-size:14px;justify-content:space-between}.budget-toolbar label+label{border:0;padding:0}.budget-toolbar select{max-width:none;width:65%}.budget-toolbar>small{flex:1 1 100%;text-align:left;font-size:12px}.budget-toolbar button{font-size:13px;margin-left:auto}.budget-cards{grid-template-columns:1fr;gap:14px}.budget-category{padding:6px 10px 12px;min-height:150px}.budget-category>header{display:grid;grid-template-columns:43px auto minmax(0,1fr) 30px;gap:6px}.budget-category>header h3{white-space:nowrap}.budget-category>header p{margin:0;font-size:13px}.budget-category>header p strong{font-size:20px}.budget-category>header button{padding:0}.budget-category-icon{width:43px;height:38px}.budget-category h3{font-size:22px}.budget-category header p{font-size:14px}.budget-category header p strong{font-size:22px}.budget-category header small{font-size:12px}.budget-workspace table{font-size:13px}.budget-workspace th,.budget-workspace td{min-width:0;padding:5px}.budget-workspace th:first-child{width:38px;white-space:nowrap}.budget-workspace th:nth-child(2){width:27%}.budget-workspace th:nth-child(3){width:25%}.budget-workspace input[type=checkbox]{width:17px;height:17px}.budget-pending{padding:10px}.budget-pending>header{flex-wrap:wrap;gap:8px}.budget-pending h3{font-size:19px}.budget-pending header p{width:100%;border:0;padding:0;margin:0;font-size:13px}.budget-pending .budget-table-scroll{padding:4px}.budget-pending td:first-child{width:9%}.budget-pending td:nth-child(2){width:27%}.budget-pending td:nth-child(3){width:25%}}
@media print{.budget-toolbar,.budget-category button,.budget-source-notes{display:none}.budget-cards{grid-template-columns:1fr 1fr}.budget-overview,.budget-category,.budget-pending{break-inside:avoid;box-shadow:none}}
"""

JS = r"""
const workspace = document.querySelector('.budget-workspace');
if (workspace) {
  const rows = [...workspace.querySelectorAll('[data-ledger] tr[data-category]')];
  const filter = workspace.querySelector('[data-budget-filter]');
  const sort = workspace.querySelector('[data-budget-sort]');
  const money = cents => '¥' + (cents / 100).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2});
  const limitInput = workspace.querySelector('[data-budget-limit]');
  const inputAmount = input => {
    if (!/^\d+(?:\.\d{1,2})?$/.test(input.value) || !input.validity.valid) return null;
    const [whole, fraction = ''] = input.value.split('.');
    return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  };
  const amount = row => inputAmount(row.querySelector('input[type=number]'));
  function update(reorder = true) {
    let total = 0, unknown = 0;
    const categories = new Map();
    for (const row of rows) {
      row.hidden = Boolean(filter.value && row.dataset.category !== filter.value);
      const value = amount(row);
      if (value === null) unknown++;
      if (!row.querySelector('input[type=checkbox]').checked) continue;
      if (value !== null) {
        total += value;
        categories.set(row.dataset.category, (categories.get(row.dataset.category) || 0) + value);
      }
    }
    workspace.querySelector('[data-total]').textContent = !total && unknown ? '待核实' : money(total);
    workspace.querySelector('[data-person]').textContent = !total && unknown ? '待核实' : money(Math.round(total / Number(workspace.dataset.travelers)));
    workspace.querySelector('[data-unknown]').textContent = unknown + ' 项待核实';
    for (const node of workspace.querySelectorAll('[data-category-total], [data-card-total]')) {
      const category = node.dataset.categoryTotal || node.dataset.cardTotal;
      const items = rows.filter(row => row.dataset.category === category);
      node.textContent = !items.length ? '未单列' : items.every(row => amount(row) === null) ? '待核实' : money(categories.get(category) || 0);
    }
    for (const card of workspace.querySelectorAll('[data-card]')) card.hidden = Boolean(filter.value && card.dataset.card !== filter.value);
    if (reorder) for (const body of workspace.querySelectorAll('[data-ledger]')) {
      const ordered = rows.filter(row => row.parentElement === body).sort((a,b) => {
        if (sort.value === 'original') return Number(a.dataset.order)-Number(b.dataset.order);
        const x = amount(a), y = amount(b);
        if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
        return sort.value === 'asc' ? x-y : y-x;
      });
      for (const row of ordered) body.append(row);
    }
    for (const segment of workspace.querySelectorAll('[data-segment]')) {
      const value = categories.get(segment.dataset.segment) || 0;
      segment.style.flexGrow = value;
      segment.querySelector('.budget-segment-label').textContent = money(value);
      segment.title = segment.dataset.segment + ' ' + money(value);
    }
    const limit = limitInput ? inputAmount(limitInput) : (workspace.dataset.limit === '' ? null : Number(workspace.dataset.limit));
    const balance = limit === null ? 0 : limit - total;
    workspace.querySelector('[data-balance]').textContent = limit === null ? '待确认' : money(balance);
    const bar = workspace.querySelector('[data-balance-bar]');
    bar.style.flexGrow = Math.max(0, balance);
    bar.querySelector('.budget-segment-label').textContent = money(Math.max(0, balance));
    bar.title = '余量 ' + (limit === null ? '待确认' : money(balance));
    workspace.querySelector('.budget-pending h3').textContent = '待核实项目（' + unknown + ' 项）';
  }
  workspace.addEventListener('input', event => {
    if (event.target.matches('input[type=number]')) update(false);
  });
  workspace.addEventListener('change', () => update());
  for (const button of workspace.querySelectorAll('[data-edit-category]')) {
    button.addEventListener('click', () => button.closest('[data-card]').querySelector('input[type=number]')?.focus());
  }
  workspace.querySelector('[data-budget-reset]').addEventListener('click', () => {
    for (const row of rows) {
      const input = row.querySelector('input[type=number]'); input.value = input.defaultValue;
      const check = row.querySelector('input[type=checkbox]'); check.checked = check.defaultChecked;
    }
    if (limitInput) limitInput.value = limitInput.defaultValue;
    filter.value = ''; sort.value = 'desc'; update();
  });
  update();
}
"""
