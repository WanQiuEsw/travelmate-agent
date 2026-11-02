"""Remove retrieval infrastructure identifiers from user-facing output."""
import os
import re


def public_data(value, messages=()):
    hidden = {os.getenv(key, "") for key in ("ALIYUN_INDEX_ID", "ALIYUN_WORKSPACE_ID")}
    for message in messages:
        if getattr(message, "type", "") == "tool":
            hidden.update(re.findall(r'"(?:document_id|doc_id)"\s*:\s*"([^"\n]+)"', str(message.content)))

    def clean(item):
        if isinstance(item, str):
            for identifier in sorted(hidden - {""}, key=len, reverse=True):
                item = re.sub(r'(?<![\w-])' + re.escape(identifier) + r'(?![\w-])', '内部资料', item)
            return re.sub(r'(?:知识库|文档|索引|工作空间|document|doc|index|workspace)[_\s]*(?:ID|编号)\s*[:：=]\s*[`\"\']?[\w-]+[`\"\']?', '内部资料', item, flags=re.I)
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()
                    if key not in ("document_id", "doc_id", "index_id", "workspace_id")}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item

    return clean(value)
