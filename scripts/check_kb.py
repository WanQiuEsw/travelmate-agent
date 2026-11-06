"""知识库体检：录入核查 → 召回核查 → 来源有效性判断。

    python scripts/check_kb.py                 # 全量 35 城，按城市过滤各查一次
    python scripts/check_kb.py --cities 杭州,厦门
    python scripts/check_kb.py --json output/kb-check.json

三件事分开看：
1. 录入：索引里到底有几个文档、名字对不对、索引是否 FINISH、标签是否为空。
2. 召回：用生产同款查询串去查，能否命中、命中哪个文档、分数多少、城市过滤开没开。
3. 有效性：命中的文档是不是请求的那个城市（串城市就是标签或文件名错了）。
脚本只读，不写知识库。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from alibabacloud_bailian20231229 import models as m
from alibabacloud_bailian20231229.client import Client
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
HIT_MIN_CHARS = 120  # planner.py 的命中判据：有原文 >= 120 字才算命中
QUERY_TAIL = "3天 行程 特色美食 必去景点 交通 住宿"


def client():
    load_dotenv(ROOT / '.env')
    missing = [k for k in ('ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET',
                           'ALIYUN_WORKSPACE_ID', 'ALIYUN_INDEX_ID') if not os.getenv(k)]
    if missing:
        sys.exit('缺少配置：' + ', '.join(missing))
    config = Config(access_key_id=os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'],
                    access_key_secret=os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'],
                    security_token=os.getenv('ALIBABA_CLOUD_SECURITY_TOKEN'))
    config.endpoint = 'bailian.cn-beijing.aliyuncs.com'
    return Client(config), os.environ['ALIYUN_WORKSPACE_ID'], os.environ['ALIYUN_INDEX_ID']


def index_documents(sdk, workspace, index_id, runtime):
    docs, page = [], 1
    while True:
        body = sdk.list_index_documents_with_options(
            workspace, m.ListIndexDocumentsRequest(index_id=index_id, page_number=page, page_size=100),
            {}, runtime).body
        if body is None or not body.success or body.data is None:
            sys.exit(f'列索引文档失败：{getattr(body, "message", "无响应")}')
        batch = body.data.documents or []
        docs += [{'name': d.name, 'status': d.status, 'code': d.code,
                  'size': d.size, 'source_id': d.source_id} for d in batch]
        if len(batch) < 100:
            return docs
        page += 1


def files_with_tags(sdk, workspace, runtime, category_ids):
    """标签挂在文件上，不在索引文档上，所以得回文件列表取。"""
    out = {}
    for category_id in category_ids:
        token = None
        while True:
            body = sdk.list_file_with_options(
                workspace, m.ListFileRequest(category_id=category_id, max_results=100, next_token=token),
                {}, runtime).body
            data = body.data if body else None
            if not data:
                break
            for item in data.file_list or []:
                out[Path(item.file_name).stem] = list(item.tags or [])
            token = data.next_token
            if not token:
                break
    return out


def retrieve(sdk, workspace, index_id, runtime, query, city=None):
    filters = [{'tags': json.dumps([city], ensure_ascii=False)}] if city else None
    request = m.RetrieveRequest(index_id=index_id, query=query,
                                dense_similarity_top_k=10, sparse_similarity_top_k=10,
                                enable_reranking=True, rerank_top_n=3,
                                enable_rewrite=False, save_retriever_history=False,
                                search_filters=filters)
    body = sdk.retrieve_with_options(workspace, request, {},
                                     RuntimeOptions(read_timeout=20000, connect_timeout=5000)).body
    if body is None or body.success is not True or body.data is None:
        code = getattr(body, 'code', '') or ''
        raise RuntimeError(f'{code} {getattr(body, "message", "无响应")}'.strip())
    nodes = []
    for node in body.data.nodes or []:
        metadata = node.metadata or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = {}
        nodes.append({'doc': str(metadata.get('doc_name') or metadata.get('title') or ''),
                      'score': float(node.score or 0),
                      'chars': len(node.text or ''),
                      'meta_keys': sorted(metadata.keys())})
    return nodes


def check_via_tool(cities, top, json_path, provider_override=''):
    """走生产同一条路：create_knowledge_tool → 真工具 → evidence.normalize。
    和 ①②③ 的区别是这里不复制检索逻辑，直接调 travelmate 里的那个工具。
    """
    sys.path.insert(0, str(ROOT))
    load_dotenv(ROOT / '.env')
    if provider_override:
        os.environ['KNOWLEDGE_PROVIDER'] = provider_override
    from travelmate.evidence import normalize
    from travelmate.knowledge import create_knowledge_tool

    provider = os.getenv('KNOWLEDGE_PROVIDER', 'local')
    directory = Path(os.getenv('KNOWLEDGE_DIR', 'knowledge'))
    kn = create_knowledge_tool(directory if directory.is_absolute() else ROOT / directory)

    print('=' * 78)
    print(f'工具链路核查（provider={provider}，目录={directory}）')
    print('=' * 78)

    rows, failures = [], []
    for city in cities:
        query = f'{city} {QUERY_TAIL}'
        args = {'query': query, 'city': city}
        try:
            data = kn.invoke(args)
        except Exception as exc:
            data = {'error': f'工具异常：{exc}'}
        rows_ = data.get('results') or []
        records = normalize('search_knowledge', args, data, 'probe', {'destination': city})
        rec = next(iter(records.values()))
        chars = max((len(str(r.get('content') or '')) for r in rows_ if isinstance(r, dict)), default=0)
        hit = chars >= HIT_MIN_CHARS
        source = str(rows_[0].get('source') if rows_ else '')
        same = bool(source and city in source)
        row = {'city': city, 'query': query, 'error': data.get('error'),
               'city_filter': data.get('city_filter', '-'), 'n': len(rows_),
               'source': source, 'chars': chars, 'hit': hit, 'same_city': same,
               'evidence': {'title': rec['title'], 'verification': rec['verification'],
                            'query_status': rec['query_status'], 'kind': rec['kind'],
                            'url': rec.get('url')}}
        rows.append(row)
        if data.get('error'):
            failures.append(row)
        if top or data.get('error'):
            flag = 'OK ' if hit and same else '⚠  '
            print(f'{flag}[{city}] filter={row["city_filter"]} n={len(rows_)} 首条={source or "无"} '
                  f'{chars}字 → 证据:{rec["query_status"]}/{rec["verification"]}'
                  + (f'  错误:{data["error"]}' if data.get('error') else ''))
            for r in rows_[:top]:
                print(f'      {r.get("source", ""):<10} {len(str(r.get("content") or "")):>5}字')
        if provider == 'aliyun':
            time.sleep(1.1)

    hits = [r for r in rows if r['hit']]
    right = [r for r in rows if r['hit'] and r['same_city']]
    off = [r for r in rows if r['city_filter'] == 'off']
    print()
    print(f'查询城市数 {len(rows)}')
    print(f'调不通/报错 {len(failures)}' + (f' → {[r["city"] for r in failures]}' if failures else ''))
    print(f'命中（首条 ≥{HIT_MIN_CHARS} 字）{len(hits)}/{len(rows)}')
    print(f'命中且来源是请求城市 {len(right)}/{len(rows)}')
    if off:
        print(f'城市过滤回退全库 {len(off)} → {[r["city"] for r in off]}')
    if hits:
        print('证据标注分布：' + ', '.join(sorted({f'{r["evidence"]["kind"]}/{r["evidence"]["verification"]}' for r in hits})))
        print('参考来源标题抽样：' + ', '.join(f'{r["city"]}→「{r["evidence"]["title"]}」' for r in hits[:3]))
        print(f'能点到来源链接：{sum(1 for r in hits if r["evidence"]["url"])}/{len(hits)}（0 = 参考来源里那条没法点开核对）')

    payload = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'provider': provider, 'cities': rows}
    if json_path:
        path = Path(json_path)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'明细已写 {path}')
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cities', default='', help='逗号分隔；默认读 kb/_index.json 全量')
    parser.add_argument('--json', default='', help='把明细写到该路径')
    parser.add_argument('--top', type=int, default=0, help='每城打印前 N 条（0 = 不打明细）')
    parser.add_argument('--via-tool', action='store_true',
                        help='走 travelmate 的真工具（create_knowledge_tool），链路与线上一致')
    parser.add_argument('--provider', default='', help='覆盖 KNOWLEDGE_PROVIDER，只影响本次进程')
    args = parser.parse_args()

    meta = json.loads((ROOT / 'kb/_index.json').read_text(encoding='utf-8'))
    local_cities = list(meta)
    cities = [c.strip() for c in args.cities.split(',') if c.strip()] or local_cities

    if args.via_tool:
        return check_via_tool(cities, args.top, args.json, args.provider)

    sdk, workspace, index_id = client()
    runtime = RuntimeOptions(read_timeout=20000, connect_timeout=5000)

    print('=' * 78)
    print('① 录入核查')
    print('=' * 78)
    docs = index_documents(sdk, workspace, index_id, runtime)
    names = [d['name'] for d in docs]
    tags = files_with_tags(sdk, workspace, runtime, sorted({d['source_id'] for d in docs}))
    bad_status = [d for d in docs if d['status'] != 'FINISH']
    empty_tags = [n for n in names if not tags.get(n)]
    tag_mismatch = [f'{n} {tags.get(n)}' for n in names if tags.get(n) and tags.get(n) != [n]]
    missing = [c for c in local_cities if c not in names]
    extra = [n for n in names if n not in local_cities]

    print(f'索引文档 {len(docs)} 个 / 本地 kb/cities {len(local_cities)} 个')
    print(f'索引构建失败(非 FINISH)：{len(bad_status)}' + (f' → {[d["name"] for d in bad_status]}' if bad_status else ''))
    print(f'标签为空：{len(empty_tags)}' + (f' → {empty_tags}' if empty_tags else ''))
    print(f'标签与文件名不一致：{len(tag_mismatch)}' + (f' → {tag_mismatch}' if tag_mismatch else ''))
    print(f'本地有、云端无：{len(missing)}' + (f' → {missing}' if missing else ''))
    print(f'云端有、本地无：{len(extra)}' + (f' → {extra}' if extra else ''))

    print()
    print('=' * 78)
    print('② 召回核查（生产同款查询串 + 城市标签过滤，串行避开 10 次/10 秒限频）')
    print('=' * 78)

    def probe(city):
        """百炼同一知识库限 10 次/10 秒（THROTTLING.pipelineQPSLimit），串行 + 退避重试。"""
        query = f'{city} {QUERY_TAIL}'
        for attempt in (1, 2, 3):
            try:
                nodes = retrieve(sdk, workspace, index_id, runtime, query, city)
                filtered = bool(nodes)
                if not nodes:
                    nodes = retrieve(sdk, workspace, index_id, runtime, query, None)
                return city, query, nodes, filtered, None
            except Exception as exc:
                text = str(exc)
                if 'THROTTLING' in text or 'limit' in text:
                    time.sleep(2.0 * attempt)
                    continue
                return city, query, [], False, text
        return city, query, [], False, 'THROTTLING 重试 3 次仍失败'

    rows = []
    for city in cities:
        city, query, nodes, filtered, error = probe(city)
        top = nodes[0] if nodes else None
        hit = bool(top and top['chars'] >= HIT_MIN_CHARS)
        same_city = bool(top and city in top['doc'])
        rows.append({'city': city, 'query': query, 'filter_on': filtered, 'hit': hit,
                     'top_doc': top['doc'] if top else '', 'top_score': top['score'] if top else 0,
                     'top_chars': top['chars'] if top else 0, 'same_city': same_city,
                     'nodes': nodes, 'error': error})
        if args.top:
            print(f'\n[{city}] filter={"on" if filtered else "off"} hit={hit} → {top["doc"] if top else "无"}'
                  + (f'  ⚠ {error}' if error else ''))
            for n in nodes[:args.top]:
                print(f'    {n["doc"]:<12} score={n["score"]:.4f} {n["chars"]:>5}字')
        time.sleep(1.1)

    hits = [r for r in rows if r['hit']]
    filtered = [r for r in rows if r['filter_on']]
    right = [r for r in rows if r['same_city']]
    wrong = [r for r in rows if r['hit'] and not r['same_city']]
    threshold = [r for r in hits if r['top_chars'] < HIT_MIN_CHARS]

    print(f'查询城市数 {len(rows)}')
    errors = [r for r in rows if r['error']]
    if errors:
        print(f'请求失败 {len(errors)} → ' + '; '.join(f'{r["city"]}: {r["error"][:40]}' for r in errors))
    print(f'城市标签过滤生效 {len(filtered)}/{len(rows)}'
          + (f'（未生效：{[r["city"] for r in rows if not r["filter_on"]]}）' if len(filtered) < len(rows) else ''))
    print(f'命中（有 ≥{HIT_MIN_CHARS} 字原文）{len(hits)}/{len(rows)}')
    print(f'首条文档就是请求城市 {len(right)}/{len(rows)}')
    print(f'命中但串到别城 {len(wrong)}' + (f' → {[f"{r["city"]}→{r["top_doc"]}" for r in wrong]}' if wrong else ''))
    if hits:
        scores = sorted(r['top_score'] for r in hits)
        print(f'首条分数 min={scores[0]:.4f} 中位={scores[len(scores)//2]:.4f} max={scores[-1]:.4f}')
    if threshold:
        print(f'命中但首条不足 {HIT_MIN_CHARS} 字 {len(threshold)} → {[r["city"] for r in threshold]}')

    print()
    print('=' * 78)
    print('③ 来源有效性判断')
    print('=' * 78)
    if not rows:
        print('无数据')
    else:
        doc_names = {r['top_doc'] for r in hits}
        print(f'实际被召回过的文档 {len(doc_names)} 个：{sorted(doc_names)[:6]}{" …" if len(doc_names) > 6 else ""}')
        print(f'文档来源字段是否可定位到具体文件：{"能" if right else "不能"}'
              '（百炼只回 doc_name，回不到段落页码；对账靠城市名匹配）')
        print('参考来源在攻略里的标注：查 guide.py 的 SOURCE_NAMES / 文档参考 判定，知识库条目一律标「文档参考」而非「查询匹配」。')
        print('有效性结论：知识库只能支撑"参考"，不能支撑"已核实"——证据层 evidence.py 把文档记录标 verification=reference，')
        print('check_reference() 会拒绝它用作 place/price/opening_hours 的核实依据。所以价格、营业时间必须另有联网来源。')

    payload = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
               'index': {'total': len(docs), 'bad_status': [d['name'] for d in bad_status],
                         'empty_tags': empty_tags, 'missing_local': missing, 'extra_cloud': extra},
               'cities': rows}
    if args.json:
        path = Path(args.json)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\n明细已写 {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
