"""批量读写百炼知识库文件的标签（城市级）。

    python scripts/tag_kb.py plan                 # 只读：看看现在都是什么标签
    python scripts/tag_kb.py apply --all          # 把文件名映射成城市名，覆盖写入
    python scripts/tag_kb.py apply --file 北京.md  # 只改一个

标签粒度定在城市：厦门.md -> ["厦门"]，香港.md -> ["香港"]。景点级标签（故宫/鼓浪屿）
一律去掉，检索时靠 city 粗筛，再交给语义匹配。
"""
import argparse
import os
import sys
from pathlib import Path

from alibabacloud_bailian20231229 import models as m
from alibabacloud_bailian20231229.client import Client
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from normalize_kb import CITIES  # noqa: E402  只给白名单里的城市打标签

PREFIXES = ('旅游智能体-', '旅游智能体_')
BATCH = 20


def client():
    load_dotenv('.env')
    config = Config(access_key_id=os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'],
                    access_key_secret=os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'])
    config.endpoint = 'bailian.cn-beijing.aliyuncs.com'
    return Client(config), os.environ['ALIYUN_WORKSPACE_ID']


def categories(client, workspace, runtime):
    response = client.list_category_with_options(
        workspace, m.ListCategoryRequest(category_type='UNSTRUCTURED', max_results=50), {}, runtime)
    return [(item.category_id, item.category_name) for item in (response.body.data.category_list or [])]


def files(client, workspace, category_id, runtime):
    collected, token = [], None
    while True:
        response = client.list_file_with_options(
            workspace, m.ListFileRequest(category_id=category_id, max_results=100, next_token=token), {}, runtime)
        data = response.body.data
        collected += data.file_list or []
        token = data.next_token
        if not token:
            return collected


def city_of(file_name):
    """文件名 -> 城市标签；省份文件、认不出来的返回空，交给人工。"""
    stem = Path(file_name).stem
    for prefix in PREFIXES:
        stem = stem.removeprefix(prefix)
    return stem if stem in CITIES else ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'apply'])
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--category', default=os.getenv('ALIYUN_CATEGORY_ID', ''))
    args = parser.parse_args()

    sdk, workspace = client()
    runtime = RuntimeOptions(read_timeout=20000, connect_timeout=5000)
    targets = categories(sdk, workspace, runtime)
    # 索引里挂着的类目才是真正被检索到的，list_category 有时列不全，从 index 文档反查补上。
    index_id = os.getenv('ALIYUN_INDEX_ID', '')
    if index_id:
        documents = sdk.list_index_documents_with_options(
            workspace, m.ListIndexDocumentsRequest(index_id=index_id, page_number=1, page_size=100),
            {}, runtime).body
        for doc in (documents.data.documents if documents.data else []) or []:
            source = getattr(doc, 'source_id', '')
            if source and source not in [item[0] for item in targets]:
                targets.append((source, '索引类目'))
    if args.category:
        targets = [item for item in targets if item[0] == args.category] or [(args.category, '指定类目')]

    pending = []
    for category_id, name in targets:
        for item in files(sdk, workspace, category_id, runtime):
            if args.file and item.file_name not in args.file:
                continue
            city = city_of(item.file_name)
            want = [city] if city else []
            changed = want and want != list(item.tags or [])
            print(f'[{name}] {item.file_name}  {item.tags} -> {want or "（认不出城市，跳过）"}')
            if changed:
                pending.append((item.file_id, want))

    if args.action == 'plan':
        print(f'\n待改 {len(pending)} 个文件；加 apply --all 才会真写。')
        return 0
    if not pending:
        print('没有需要改的。')
        return 0
    if not args.all and not args.file:
        print('批量写入需要 --all 或 --file 明确指定。')
        return 1
    for start in range(0, len(pending), BATCH):
        chunk = pending[start:start + BATCH]
        request = m.BatchUpdateFileTagRequest(
            file_infos=[m.BatchUpdateFileTagRequestFileInfos(file_id=file_id, tags=tags) for file_id, tags in chunk],
            update_mode='replace')
        sdk.batch_update_file_tag_with_options(workspace, request, {}, runtime)
        print(f'已更新 {len(chunk)} 个文件的标签')
    return 0


if __name__ == '__main__':
    sys.exit(main())
