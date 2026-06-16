"""
发展党员材料合规检查工具

输入：一份发展党员相关材料的文本内容
输出：结构化的问题清单（格式/内容/时间线/交叉一致性）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge" / "party_rules.md"

DOC_TYPES = {
    "入党申请书": {"keywords": ["入党申请", "申请加入", "志愿加入"], "min_words": 1500},
    "思想汇报": {"keywords": ["思想汇报", "近期思想"], "min_words": 1000},
    "转正申请": {"keywords": ["转正申请", "按期转正", "预备期"], "min_words": 1200},
    "入党志愿书": {"keywords": ["入党志愿", "本人经历"], "min_words": 800},
    "考察意见": {"keywords": ["考察意见", "培养考察", "考察情况"], "min_words": 300},
}


def detect_doc_type(text: str) -> str | None:
    text_lower = text.lower()
    best_match = None
    best_score = 0
    for doc_type, info in DOC_TYPES.items():
        score = sum(1 for kw in info["keywords"] if kw.lower() in text_lower)
        if score > best_score:
            best_score = score
            best_match = doc_type
    return best_match if best_score > 0 else None


def _estimate_word_count(text: str) -> int:
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    return len(chinese_chars)


def _check_date_format(text: str) -> list[dict]:
    issues = []
    standard_date = re.findall(r'\d{4}\u5e74\d{1,2}\u6708\d{1,2}\u65e5', text)
    dot_date = re.findall(r'\d{4}\.\d{1,2}\.\d{1,2}', text)
    slash_date = re.findall(r'\d{4}/\d{1,2}/\d{1,2}', text)

    for d in standard_date:
        issues.append({'type': '\u2705', 'detail': '\u65e5\u671f\u683c\u5f0f\u6b63\u786e\u300c' + d + '\u300d', 'fix': ''})
    for d in dot_date:
        fix_val = d.replace('.', '\u5e74', 1).replace('.', '\u6708') + '\u65e5'
        issues.append({'type': '\u274c', 'detail': '\u65e5\u671f\u683c\u5f0f\u4e0d\u89c4\u8303\u300c' + d + '\u300d', 'fix': fix_val})
    for d in slash_date:
        issues.append({'type': '\u274c', 'detail': '\u65e5\u671f\u683c\u5f0f\u4e0d\u89c4\u8303\u300c' + d + '\u300d', 'fix': ''})

    return issues


def _check_required_fields(text: str, doc_type: str) -> list[dict]:
    issues = []
    greeting_found = False
    for expected in ["\u656c\u7231\u7684\u515a\u7ec4\u7ec7", "\u656c\u7231\u7684\u515a\u652f\u90e8"]:
        if expected in text:
            greeting_found = True
            issues.append({'type': '\u2705', 'detail': '\u79f0\u547c\u683c\u5f0f\u6b63\u786e', 'fix': ''})
            break
    if not greeting_found:
        issues.append({'type': '\u274c', 'detail': '\u672a\u627e\u5230\u6807\u51c6\u79f0\u547c', 'fix': '\u5efa\u8bae\u4f7f\u7528\u201c\u656c\u7231\u7684\u515a\u7ec4\u7ec7\u201d'})

    ending_patterns = [
        r'\u6b64\u81f4\s*\n\s*\u656c\u793c',
        r'\u8bf7\u515a\u7ec4\u7ec7[\u8003\u5bdf|\u8003\u9a8c|\u6279\u8bc4|\u6307\u6b63]',
        r'\u6073\u8bf7\u515a\u7ec4\u7ec7',
    ]
    has_sig = False
    for pat in ending_patterns:
        if re.search(pat, text):
            has_sig = True
            issues.append({'type': '\u2705', 'detail': '\u6709\u89c4\u8303\u7ed3\u5c3e\u7528\u8bed', 'fix': ''})
            break
    if not has_sig:
        issues.append({'type': '\u26a0\ufe0f', 'detail': '\u672a\u627e\u5230\u89c4\u8303\u7ed3\u5c3e', 'fix': '\u5efa\u8bae\u52a0\u4e0a\u201c\u6b64\u81f4\u656c\u793c\u201d\u6216\u201c\u8bf7\u515a\u7ec4\u7ec7\u6279\u8bc4\u6307\u6b63\u201d'})

    return issues


def _check_content_quality(text: str, doc_type: str) -> list[dict]:
    issues = []
    word_count = _estimate_word_count(text)
    min_words = DOC_TYPES.get(doc_type, {}).get("min_words", 1000)

    if word_count < min_words * 0.7:
        issues.append({'type': '\u274c', 'detail': f'\u5185\u5bb9\u4e25\u91cd\u4e0d\u8db3\uff1a\u7ea6{word_count}\u5b57\uff0c\u8981\u6c42\u6700\u5c11{min_words}\u5b57', 'fix': '\u9700\u8981\u5927\u5e45\u6269\u5145\u5185\u5bb9'})
    elif word_count < min_words:
        issues.append({'type': '\u26a0\ufe0f', 'detail': f'\u5185\u5bb9\u504f\u5c11\uff1a\u7ea6{word_count}\u5b57\uff0c\u5efa\u8bae\u8fbe\u5230{min_words}\u5b57\u4ee5\u4e0a', 'fix': '\u5efa\u8bae\u9002\u5f53\u6269\u5145'})
    else:
        issues.append({'type': '\u2705', 'detail': f'\u5b57\u6570\u8fbe\u6807\uff1a\u7ea6{word_count}\u5b57', 'fix': ''})

    hot_topics = ["\u4e8c\u5341\u5927", "\u4e3b\u9898\u6559\u80b2", "\u65b0\u8d28\u751f\u4ea7\u529b", "\u4e2d\u56fd\u5f0f\u73b0\u4ee3\u5316", "\u9ad8\u8d28\u91cf\u53d1\u5c55", "\u4ece\u4e25\u6cbb\u515a", "\u515a\u7eaa"]
    found_topics = [t for t in hot_topics if t in text]
    if found_topics:
        issues.append({'type': '\u2705', 'detail': '\u7ed3\u5408\u4e86\u65f6\u653f\u70ed\u70b9', 'fix': ''})
    else:
        issues.append({'type': '\u26a0\ufe0f', 'detail': '\u672a\u8bc6\u522b\u5230\u65f6\u653f\u70ed\u70b9\u8bcd\u6c47', 'fix': '\u5efa\u8bae\u7ed3\u5408\u8fd1\u671f\u91cd\u8981\u4f1a\u8bae\u7cbe\u795e'})

    self_criticism_keywords = ["\u4e0d\u8db3", "\u7f3a\u70b9", "\u5dee\u8ddd", "\u6539\u8fdb", "\u52aa\u529b\u65b9\u5411", "\u53cd\u601d"]
    found_criticism = [k for k in self_criticism_keywords if k in text]
    if found_criticism:
        issues.append({'type': '\u2705', 'detail': '\u6709\u81ea\u6211\u6279\u8bc4\u5185\u5bb9', 'fix': ''})
    else:
        issues.append({'type': '\u26a0\ufe0f', 'detail': '\u7f3a\u5c11\u81ea\u6211\u6279\u8bc4\u6216\u6539\u8fdb\u65b9\u5411', 'fix': '\u5efa\u8bae\u8865\u5145\u4e2a\u4eba\u4e0d\u8db3\u548c\u6539\u8fdb\u65b9\u5411'})

    return issues


def check_document(text: str) -> str:
    doc_type = detect_doc_type(text) or "未知"
    word_count = _estimate_word_count(text)

    lines = []
    lines.append(f"材料类型: {doc_type}")
    lines.append(f"中文字数: ~{word_count}")
    lines.append("")

    date_issues = _check_date_format(text)
    req_issues = _check_required_fields(text, doc_type)
    quality_issues = _check_content_quality(text, doc_type)

    for section_name, section_issues in [
        ("日期格式", date_issues),
        ("必备要素", req_issues),
        ("内容质量", quality_issues),
    ]:
        if section_issues:
            lines.append("---")
            lines.append(section_name)
            for item in section_issues:
                icon = item["type"]
                detail = item["detail"]
                fix = item.get("fix", "")
                line = f"  {icon} {detail}"
                if fix:
                    line += f"\n     \u2192 {fix}"
                lines.append(line)
        lines.append("")

    error_count = sum(1 for l in lines if "\u274c" in l)
    warning_count = sum(1 for l in lines if "\u26a0" in l)
    pass_count = sum(1 for l in lines if "\u2705" in l)

    lines.append("---")
    lines.append(f"摘要: ❌ {error_count}个错误  ⚠️ {warning_count}个警告  ✅ {pass_count}项通过")

    return "\n".join(lines)


def format_check_result(result: str) -> str:
    return result