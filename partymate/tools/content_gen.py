"""
三会一课内容生成工具

输入：会议/党课主题
输出：学习资料摘要、PPT大纲、讨论题目
"""

from __future__ import annotations

import json


def generate_meeting_content(topic: str) -> str:
    """
    根据主题生成三会一课内容

    Args:
        topic: 会议/党课主题（如 "学习党的二十大精神"）

    Returns:
        结构化的内容方案（JSON格式）
    """
    result = {
        "topic": topic,
        "meeting_type": _detect_meeting_type(topic),
        "learning_materials": _suggest_materials(topic),
        "ppt_outline": _generate_outline(topic),
        "discussion_questions": _generate_questions(topic),
        "reference_sources": [],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def _detect_meeting_type(topic: str) -> str:
    """根据主题判断适合的会议类型（关键词优先级：党课 > 党员大会 > 支委会 > 党小组会）"""
    # 先匹配最具体的类型
    party_class_keywords = ["党课", "党纪", "党史", "条例", "准则", "纪律", "作风", "思想建设"]
    party_meeting_keywords = ["发展党员", "预备", "转正", "换届", "选举", "表彰", "处分", "民主评议"]
    committee_keywords = ["支委", "工作安排", "计划", "分工", "汇报工作"]
    party_group_keywords = ["学习", "讨论", "交流", "分享", "谈心"]

    if any(kw in topic for kw in party_class_keywords):
        return "党课"
    elif any(kw in topic for kw in party_meeting_keywords):
        return "支部党员大会"
    elif any(kw in topic for kw in committee_keywords):
        return "支委会"
    elif any(kw in topic for kw in party_group_keywords):
        return "党小组会"
    else:
        return "党课（建议类型）"


def _suggest_materials(topic: str) -> list[dict]:
    """建议学习材料"""
    materials = [
        {
            "type": "原文学习",
            "title": f"关于「{topic}」的原文/文件",
            "source": "请查阅学校党委下发文件或人民网/新华网相关报道",
            "focus": "核心要义、精神实质",
        },
        {
            "type": "解读资料",
            "title": f"「{topic}」权威解读",
            "source": "求是网/人民日报评论/学习强国",
            "focus": "重点内容梳理、实践要求",
        },
        {
            "type": "案例参考",
            "title": f"相关典型案例或先进事迹",
            "source": "共产党员网/各地实践案例",
            "focus": "理论联系实际",
        },
    ]
    return materials


def _generate_outline(topic: str) -> list[dict]:
    """生成绩PPT大纲"""

    slides = [
        {"title": f"学习「{topic}」", "content": f"封面页\n主讲人：\n日期：\n主题：{topic}", "type": "cover"},
        {"title": "学习背景", "content": f"为什么学习「{topic}」\n• 当前形势与任务\n• 上级党组织要求\n• 支部学习计划安排", "type": "content"},
        {"title": "核心内容", "content": f"「{topic}」的主要内容\n• 重点条目一\n• 重点条目二\n• 重点条目三", "type": "content"},
        {"title": "关键词解读", "content": f"「{topic}」的关键概念\n• 概念一：解释\n• 概念二：解释\n• 概念三：解释", "type": "content"},
        {"title": "实践要求", "content": "如何结合实际贯彻落实\n• 对学生党员的要求\n• 对支部工作的指导\n• 具体行动方向", "type": "content"},
        {"title": "讨论环节", "content": f"请围绕以下问题展开讨论：\n1. 你对{topic}的理解？\n2. 如何在日常学习生活中践行？\n3. 对支部工作的建议？", "type": "discussion"},
        {"title": "总结", "content": f"本次学习要点回顾\n• {topic}的核心要义\n• 下一阶段学习安排\n• 落实要求", "type": "summary"},
    ]

    return slides


def _generate_questions(topic: str) -> list[str]:
    """生成讨论题目"""
    questions = [
        f"结合自身实际，谈谈你对「{topic}」的理解和认识？",
        f"作为学生党员/积极分子，如何在日常学习生活中贯彻「{topic}」的要求？",
        f"「{topic}」对你所在的专业/研究方向有什么启示？",
        f"对照「{topic}」的要求，你觉得支部工作还有哪些可以改进的地方？",
    ]
    return questions


def format_content_plan(result_json: str) -> str:
    """将JSON格式的内容方案格式化为可读文本"""
    try:
        data = json.loads(result_json)
    except json.JSONDecodeError:
        return result_json

    lines = []
    lines.append("=" * 40)
    lines.append(f" 内容方案: {data['topic']}")
    lines.append(f" 建议形式: {data['meeting_type']}")
    lines.append("=" * 40)
    lines.append("")

    lines.append("📚 学习材料")
    lines.append("-" * 40)
    for mat in data.get("learning_materials", []):
        lines.append(f"  [{mat['type']}] {mat['title']}")
        lines.append(f"     来源: {mat['source']}")
        lines.append(f"     重点: {mat['focus']}")
    lines.append("")

    lines.append("📊 PPT大纲")
    lines.append("-" * 40)
    for i, slide in enumerate(data.get("ppt_outline", []), 1):
        lines.append(f"  {i}. {slide['title']} [{slide['type']}]")
        for line in slide['content'].split("\n"):
            if line.strip():
                lines.append(f"     {line.strip()}")
    lines.append("")

    lines.append("💬 讨论题目")
    lines.append("-" * 40)
    for i, q in enumerate(data.get("discussion_questions", []), 1):
        lines.append(f"  {i}. {q}")

    return "\n".join(lines)