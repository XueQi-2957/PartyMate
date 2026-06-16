"""
会议记录整理工具

输入：会议原始文本（语音转文字/手写识别文本/笔记等）
输出：结构化会议纪要
"""

from __future__ import annotations

import json
import re


def parse_meeting_notes(raw_text: str) -> str:
    """
    将原始会议记录整理为结构化纪要

    Args:
        raw_text: 会议原始文本

    Returns:
        结构化会议纪要（JSON格式）
    """
    # 提取基本信息
    meeting_info = _extract_meeting_info(raw_text)

    # 识别议题
    topics = _identify_topics(raw_text)

    # 识别待办事项
    action_items = _identify_action_items(raw_text)

    result = {
        "meeting_info": meeting_info,
        "topics": topics,
        "action_items": action_items,
        "summary": {
            "type": meeting_info.get("type", "未知"),
            "key_decisions": _extract_decisions(topics),
            "status": "待整理",
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def _extract_meeting_info(text: str) -> dict:
    """提取会议基本信息"""
    info = {
        "date": "",
        "time": "",
        "location": "",
        "chair": "",
        "recorder": "",
        "attendees": [],
        "absentees": [],
        "type": "",
    }

    # 日期提取
    date_patterns = [
        r"(\d{4})[年\.\-](\d{1,2})[月\.\-](\d{1,2})[日]?",
        r"(\d{4})[年\.\-](\d{1,2})[月\.\-](\d{1,2})[日]?\s*(?:星期[一二三四五六日])?",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            info["date"] = match.group(0)
            break

    # 会议类型
    type_patterns = {
        "支部党员大会": ["支部党员大会", "党员大会"],
        "支委会": ["支委会", "支部委员会"],
        "党小组会": ["党小组会"],
        "党课": ["党课", "主题教育课"],
    }
    for meeting_type, keywords in type_patterns.items():
        if any(kw in text for kw in keywords):
            info["type"] = meeting_type
            break

    # 主持人/记录人
    chair_match = re.search(r"主持(?:人)?[：:]\s*(\S+)", text)
    if chair_match:
        info["chair"] = chair_match.group(1)

    recorder_match = re.search(r"记录(?:人)?[：:]\s*(\S+)", text)
    if recorder_match:
        info["recorder"] = recorder_match.group(1)

    # 出席人数
    attend_patterns = [
        r"(?:出席|参会|参加)(?:人数)?[：:]\s*(\d+)\s*人",
        r"(?:应到|实到)[：:]\s*(\d+)\s*人",
    ]
    for pattern in attend_patterns:
        match = re.search(pattern, text)
        if match:
            info["attendees"] = [f"共{match.group(1)}人"]
            break

    return info


def _identify_topics(text: str) -> list[dict]:
    """识别会议议题"""
    topics = []

    topic_markers = [
        r"(?:一|二|三|四|五|六|七|八|九|十)[、\.]\s*([^\n]{2,50})",
        r"(?:议题|议程)[：:]\s*([^\n]{2,50})",
        r"(?:讨论|研究|学习)\s*(?:了)?\s*[「『【《]([^」』】》]{2,50})[」』】》]",
        r"关于\s*([^\n]{2,40})[的]*\s*(?:通知|报告|讲话|文件|精神)",
    ]

    # 尝试使用正则查找议题
    for pattern in topic_markers:
        for match in re.finditer(pattern, text):
            topic_text = match.group(1).strip()
            if len(topic_text) >= 4 and topic_text not in [t.get("title", "") for t in topics]:
                topics.append({
                    "title": topic_text,
                    "discussion_points": [],
                    "conclusion": "",
                })

    # 如果没有识别到议题，用中文序号拆分单行文本
    if not topics:
        # 尝试匹配 "议题一：xxx 议题二：xxx" 模式（单行）
        # 用 议题[一二三四五六] 作为分隔符拆分
        parts = re.split(r"(议题[一二三四五六][：:])", text)
        if len(parts) > 1:
            for i in range(1, len(parts), 2):
                idx = parts[i]  # e.g. "议题一："
                content = parts[i + 1] if i + 1 < len(parts) else ""
                # 截取到下一个 "议题" 或行尾
                content = re.split(r"议题[一二三四五六]", content)[0]
                # 去掉尾部附带的待办事项或后续说明
                content = re.split(r"(?:下一步|后续|接下来)\s*(?:工作)?[：，,]", content)[0]
                content = content.strip().rstrip("，。；,")
                if content and len(content) >= 2:
                    topics.append({"title": content, "discussion_points": [], "conclusion": ""})
        if not topics:
            sections = re.split(r"\n(?:一|二|三|四|五|六)[、\.]", text)
            if len(sections) > 1:
                for i, section in enumerate(sections[1:], 1):
                    first_line = section.strip().split("\n")[0][:40]
                    topics.append({
                        "title": f"第{i}项议程: {first_line}",
                        "discussion_points": [],
                        "conclusion": "",
                    })

    if not topics:
        topics.append({
            "title": "未识别到明确议题",
            "discussion_points": ["请人工补充议题信息"],
            "conclusion": "",
        })

    return topics


def _identify_action_items(text: str) -> list[dict]:
    """识别待办事项"""
    items = []

    action_patterns = [
        r"(?:请|要求|安排|由)\s*(\S+)\s*(?:负责|牵头|落实|完成)([^，。\n]{5,50})",
        r"(?:下一步|后续|接下来)\s*(?:工作)?[：，,]\s*([^，。\n]{5,50})",
        r"(\S{2,6})\s*(?:负责|牵头|起草|落实)([^，。\n]{5,50})",
        r"([^，。\n]{5,50})\s*(?:需|需要|务必|必须)\s*在\s*(\d{1,2})[月](?:\d{1,2})?[日]?\s*(?:前|之前|完成)",
    ]

    for pattern in action_patterns:
        for match in re.finditer(pattern, text):
            items.append({
                "task": match.group(0).strip()[:60],
                "assignee": match.group(1) if len(match.groups()) > 0 else "待确认",
                "deadline": match.group(2) if len(match.groups()) > 1 else "待确认",
            })

    if not items:
        items.append({
            "task": "（未识别到待办事项，请人工检查）",
            "assignee": "",
            "deadline": "",
        })

    return items


def _extract_decisions(topics: list[dict]) -> list[str]:
    """提取决策事项"""
    decisions = []
    for topic in topics:
        if topic.get("conclusion"):
            decisions.append(f"{topic['title']}: {topic['conclusion']}")
    if not decisions:
        decisions.append("（请AI补充决议事项总结）")
    return decisions


def format_meeting_summary(result_json: str) -> str:
    """将JSON格式的会议纪要格式化为可读文本"""
    try:
        data = json.loads(result_json)
    except json.JSONDecodeError:
        return result_json

    info = data["meeting_info"]
    lines = []
    lines.append("=" * 40)
    lines.append(" 会 议 纪 要")
    lines.append("=" * 40)
    lines.append("")
    lines.append(f"📅 日期: {info.get('date', '未识别')}")
    lines.append(f"📍 地点: {info.get('location', '未识别')}")
    lines.append(f"👤 主持人: {info.get('chair', '未识别')}")
    lines.append(f"📝 记录人: {info.get('recorder', '未识别')}")
    lines.append(f"👥 出席: {', '.join(info.get('attendees', [])) if info.get('attendees') else '未识别'}")
    lines.append(f"📋 类型: {info.get('type', '未识别')}")
    lines.append("")

    lines.append("-" * 40)
    lines.append("📌 议题")
    lines.append("-" * 40)
    for i, topic in enumerate(data.get("topics", []), 1):
        lines.append(f"  {i}. {topic['title']}")
        for point in topic.get("discussion_points", []):
            lines.append(f"     • {point}")

    lines.append("")
    lines.append("-" * 40)
    lines.append("✅ 待办事项")
    lines.append("-" * 40)
    for item in data.get("action_items", []):
        assignee = f"[{item.get('assignee', '')}]" if item.get('assignee') else ""
        deadline = f" 截止: {item.get('deadline', '')}" if item.get('deadline') else ""
        lines.append(f"  □ {item['task']} {assignee}{deadline}")

    lines.append("")
    lines.append("-" * 40)
    lines.append("💡 决议事项")
    lines.append("-" * 40)
    for decision in data.get("summary", {}).get("key_decisions", []):
        lines.append(f"  • {decision}")

    return "\n".join(lines)
