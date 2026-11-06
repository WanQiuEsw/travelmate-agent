"""Remove retrieval infrastructure identifiers from user-facing output."""
import os
import re


def internal_title(value):
    value = re.split(r'[:：]', value, maxsplit=1)[0]
    title = re.sub(r'^[\s#>*\-\d.、（）()一二三四五六七八九十]+', '', value)
    title = re.sub(r'[\s*：:]+$', '', title)
    return bool(re.fullmatch(r'(?:内部)?(?:检查项|检查清单|检查结果|检查与仍待确认事项|待确定事项|待确认事项|仍待确认事项|内部检查|内部审查|审核记录|审查记录)(?:[及与和、/]*(?:仍)?待(?:确认|确定)事项)?(?:[（(]内部[）)])?', title))


def travel_content(text):
    """Remove editorial sections while retaining practical travel and safety advice."""
    lines = text.splitlines()
    output, hidden_level, current_level = [], None, 0
    for index, line in enumerate(lines):
        heading = re.match(r'^\s*(#{1,6})\s+(.+?)\s*#*\s*$', line)
        bold = re.fullmatch(r'\s*\*\*(.+?)\*\*\s*[:：]?\s*', line)
        setext = index + 1 < len(lines) and re.fullmatch(r'\s*(?:=+|-{3,})\s*', lines[index + 1])
        label = line.strip().rstrip(':：')
        level = len(heading[1]) if heading else (1 if lines[index + 1].strip().startswith('=') else 2) if setext else current_level + 1
        title = heading[2] if heading else bold[1] if bold else label
        if internal_title(title):
            hidden_level = level
            continue
        if hidden_level is not None:
            if (heading or bold or setext) and level <= hidden_level:
                hidden_level = None
            else:
                continue
        if heading or setext:
            current_level = level
        output.append(line)
    return '\n'.join(output).strip()


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


def public_answer(text, messages=()):
    """Keep reference labels short without changing the travel advice."""
    text = travel_content(public_data(text, messages))
    # Evidence IDs must survive machine-readable state and model input.
    text = re.sub(r"(?<![\w-])[a-f0-9]{32}:\d+(?!\w)", "查询依据", text)
    # Map coordinates belong in navigation links, not in travel prose.
    text = re.sub(r"[（(]\s*-?\d{1,3}\.\d+\s*[,，]\s*-?\d{1,2}\.\d+\s*[)）]", "", text)
    labels = {"travel_minutes": "交通预留时间", "transport_mode": "交通方式",
              "transit": "公交/地铁", "walking": "步行", "driving": "驾车", "flight": "飞机", "ferry": "轮渡"}
    for field, label in labels.items():
        text = re.sub(r"(?<![A-Za-z0-9_/=:])`?" + field + r"`?(?![A-Za-z0-9_])", label, text)
    lines = text.splitlines()
    in_sources = False
    seen = set()
    output = []
    for line in lines:
        if re.match(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:参考来源|引用来源|参考资料|资料来源|来源说明|来源)(?:\*\*)?\s*[:：]?\s*$", line):
            in_sources = True
        elif in_sources and (re.match(r"^#{1,6}\s", line) or re.match(r"^\s*(?:[-*]\s*)?(?:如需|如果|欢迎|你可以|告诉我|需要我)", line)):
            in_sources = False
        elif in_sources:
            label = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
            if label.startswith("高德") and not any(word in label for word in ("查询匹配", "查询失败", "无结果", "超查询范围")):
                line = "- 通过高德地图查询"
            elif ("知识库" in label and " · " not in label and "，" not in label
                  and len(label) <= 40 and not re.search(r"https?://", label)):
                # 只压掉「XX知识库（城市、景点）」这类裸文档名，带说明的整句保留。
                line = "- 使用了" + re.split(r"[（(:：]", label)[0].removeprefix("使用了").strip()
            if line.strip():
                if line in seen:
                    continue
                seen.add(line)
        output.append(line)
    return "\n".join(output)
