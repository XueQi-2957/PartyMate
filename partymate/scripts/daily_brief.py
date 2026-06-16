"""PartyMate 每日简报 — 用于 Hermes Cron 定时任务。

在每个工作日早上运行，扫描所有活跃成员的状态，
生成待办事项和提醒摘要，通过 Hermes Cron 推送。"""

import os
import sys
from datetime import date, datetime, timedelta

# ── 确保能导入 partymate ────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, "..", ".."))
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from partymate.db.repository import Repository
from partymate.reminder_engine import ReminderEngine
from partymate.timeline_engine import TimelineEngine


def generate_brief() -> str:
    """生成今日简报文本，直接返回适合推送的字符串。"""
    repo = Repository()
    reminder_engine = ReminderEngine()
    timeline_engine = TimelineEngine()

    today = date.today()
    today_str = today.isoformat()
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

    lines = []
    lines.append("📋 PartyMate 每日党务简报")
    lines.append(f"📅 {today.year}年{today.month}月{today.day}日 星期{weekday_names[today.weekday()]}")
    lines.append("")

    # ── 总体概览 ──
    dashboard = repo.get_dashboard()
    lines.append(f"👥 成员总数: {dashboard['total_members']} 人")
    by_stage = dashboard.get("by_stage", {})
    stage_labels = {
        "applicant": "申请入党",
        "activist": "积极分子",
        "candidate": "发展对象",
        "probationary": "预备党员",
        "full_member": "正式党员",
    }
    stage_parts = []
    for s, label in stage_labels.items():
        cnt = by_stage.get(s, 0)
        if cnt > 0:
            stage_parts.append(f"{label} {cnt}人")
    if stage_parts:
        lines.append("  分布: " + " | ".join(stage_parts))
    lines.append("")

    # ── 已逾期事件 ──
    overdue = dashboard.get("overdue_events", 0)
    pending_mats = dashboard.get("pending_materials", 0)
    if overdue > 0:
        lines.append(f"⛔ 已逾期事件: {overdue} 项")
    if pending_mats > 0:
        lines.append(f"📄 待交材料: {pending_mats} 项")
    if overdue > 0 or pending_mats > 0:
        lines.append("")

    # ── 各成员待办 ──
    members = repo.get_members()
    has_pending = False
    for m in members:
        mid = m["id"]
        name = m["name"]
        stage = m["stage"]
        events = repo.get_events(mid)

        pending_events = [e for e in events if e.get("status") == "pending"]
        overdue_events = [e for e in events if e.get("status") == "overdue"]
        materials = repo.get_materials(mid)
        missing_mats = [mat for mat in materials if mat.get("is_required") and not mat.get("is_submitted")]

        if not pending_events and not overdue_events and not missing_mats:
            continue

        has_pending = True
        stage_label = stage_labels.get(stage, stage)
        lines.append(f"🔹 {name} ({stage_label})")

        for ev in overdue_events:
            lines.append(f"  ⛔ 逾期: {ev['event_type']}")
        for ev in pending_events:
            lines.append(f"  📌 {ev['event_type']}")
        if missing_mats:
            lines.append(f"  📄 缺 {len(missing_mats)} 项材料")

        # 下一关键节点倒计时
        next_dl = timeline_engine.get_next_deadline(m)
        if next_dl:
            days = next_dl.get("days_remaining")
            et = next_dl.get("event_type", "")
            if days is not None:
                if days <= 0:
                    lines.append(f"  ⛔ {et} 已到期!")
                elif days <= 7:
                    lines.append(f"  ⚠️ {et} 还剩 {days} 天")
        lines.append("")

    if not has_pending:
        lines.append("✅ 当前无待办事项，一切正常！")
        lines.append("")

    # ── 学校日历提醒 ──
    school_events = timeline_engine.get_school_calendar_events(today.year)
    nearby_events = [e for e in school_events if e.get("date") and abs((date.fromisoformat(e["date"]) - today).days) <= 14]
    if nearby_events:
        lines.append("📆 近期学校节点:")
        for ev in nearby_events:
            ev_date = date.fromisoformat(ev["date"])
            days = (ev_date - today).days
            prefix = "今天" if days == 0 else f"还剩 {days} 天"
            lines.append(f"  {prefix}: {ev['title']}")
        lines.append("")

    # ── 自动生成提醒 ──
    lines.append("💡 系统自动提醒:")
    new_reminders = reminder_engine.generate_reminders(repo, today)
    if new_reminders:
        for r in new_reminders[:10]:  # 最多显示10条
            lines.append(f"  • {r['title']}: {r.get('description', '')[:60]}")
    else:
        lines.append("  （暂无新提醒）")

    lines.append("")
    lines.append("---")
    lines.append("💻 访问 Web 界面查看更多: http://localhost:8567")

    repo.close()
    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_brief())