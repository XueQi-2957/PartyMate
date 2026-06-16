"""
PartyMate ReminderEngine — 提醒规则引擎

根据成员当前阶段和关键日期，自动生成 actionable 提醒事项。
参考《贵州省发展党员工作规程（试行）》§4 自动提醒规则。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

try:
    from partymate.db.repository import Repository
except ImportError:
    Repository = None  # type: ignore

from partymate.timeline_engine import TimelineEngine, _parse_date, _add_months


class ReminderEngine:
    """提醒规则引擎

    扫描所有活跃成员，根据其当前阶段和关键日期生成提醒。
    所有提醒使用中文，可直接推送（Hermes Cron 或 Web 端）。
    """

    def __init__(self) -> None:
        self._timeline = TimelineEngine()

    def generate_reminders(
        self, repo: Any, today: Optional[date] = None
    ) -> list[dict[str, Any]]:
        """扫描所有活跃成员，生成待办提醒列表

        Args:
            repo: Repository 实例（含 get_active_members, get_events 等方法）
            today: 参考日期，默认 datetime.date.today()

        Returns:
            list[dict]: 提醒字典列表，每条包含:
                - member_id, member_name, title, description, due_date, is_sent=False
        """
        if today is None:
            today = date.today()

        reminders: list[dict[str, Any]] = []

        try:
            members = repo.get_active_members()
        except Exception:
            # 如果 repo 方法不存在，尝试 get_all_members
            try:
                members = repo.get_all_members()
            except Exception:
                return reminders

        now = datetime.now()

        for member in members:
            member_reminders = self._generate_for_member(member, today)
            reminders.extend(member_reminders)

        return reminders

    def _generate_for_member(
        self, member: dict[str, Any], today: date
    ) -> list[dict[str, Any]]:
        """为单个成员生成提醒"""
        reminders: list[dict[str, Any]] = []
        mid = member.get("id")
        name = member.get("name", "未知")
        stage = member.get("stage", "applicant")

        apply_date = _parse_date(member.get("apply_date"))
        activist_date = _parse_date(member.get("activist_date"))
        candidate_date = _parse_date(member.get("candidate_date"))
        probationary_date = _parse_date(member.get("probationary_date"))

        # ── Rule 1: 申请书递交后第25天 → 入党谈话提醒 ──
        if apply_date and stage in ("applicant",):
            day25 = apply_date + timedelta(days=25)
            if day25 >= today:
                days_left = (apply_date + timedelta(days=30) - today).days
                reminders.append(self._make(
                    mid, name, "入党谈话提醒",
                    f"请安排与{name}的入党谈话（还剩{days_left}天到期）",
                    due_date=(apply_date + timedelta(days=30)).isoformat(),
                ))

        # ── Rule 2: 确定积极分子前2周 ──
        if apply_date and stage in ("applicant", "activist"):
            # 最近的可能积极分子确定日期
            min_date = _add_months(apply_date, 3)
            if min_date.month <= 6:
                activist_est = date(min_date.year, 6, 30)
            else:
                activist_est = date(min_date.year, 12, 31)
            if activist_est < min_date:
                if min_date.month <= 6:
                    activist_est = date(min_date.year + 1, 6, 30)
                else:
                    activist_est = date(min_date.year + 1, 12, 31)

            remind_date = activist_est - timedelta(days=14)
            if today >= remind_date and stage == "applicant":
                months_passed = (today.year - apply_date.year) * 12 + (today.month - apply_date.month)
                reminders.append(self._make(
                    mid, name, "推优准备提醒",
                    f"{name}已递交申请书{months_passed}个月，可准备推优确定积极分子",
                    due_date=activist_est.isoformat(),
                ))

        # ── Rule 3: 每月1日 → 思想汇报收集（由 school calendar 触发，这里做每日检查）─
        # 仅在当月第一天附近（1-3日）生成
        if today.day <= 3 and stage in ("activist", "probationary"):
            reminders.append(self._make(
                mid, name, "思想汇报提醒",
                f"请收集{name}的本月思想汇报（{today.year}年{today.month}月）",
                due_date=date(today.year, today.month, 31).isoformat(),
            ))

        # ── Rule 4: 积极分子满11个月 → 可准备列为发展对象 ──
        if activist_date and stage in ("activist",):
            expire_date = _add_months(activist_date, 12)
            remind_date = expire_date - timedelta(days=30)  # 提前30天提醒
            if today >= remind_date:
                days_to_go = (expire_date - today).days
                reminders.append(self._make(
                    mid, name, "发展对象准备提醒",
                    f"{name}即将满1年培养期（还剩{days_to_go}天），可准备列为发展对象",
                    due_date=expire_date.isoformat(),
                ))

        # ── Rule 5: 预审合格后20天 → 支部大会提醒 ──
        if candidate_date and stage in ("candidate",):
            # 推定预审在确定发展对象后2个月
            precheck_date_est = _add_months(candidate_date, 2)
            remind_date = precheck_date_est + timedelta(days=20)
            meeting_deadline = precheck_date_est + timedelta(days=30)
            if today >= remind_date and today <= meeting_deadline:
                days_left = (meeting_deadline - today).days
                reminders.append(self._make(
                    mid, name, "支部大会提醒",
                    f"{name}预审已合格，请尽快召开支部大会（还剩{days_left}天）",
                    due_date=meeting_deadline.isoformat(),
                ))

        # ── Rule 6: 预备期满前14天 → 转正申请提醒 ──
        if probationary_date and stage in ("probationary",):
            full_member_date_est = _add_months(probationary_date, 12)
            remind_date = full_member_date_est - timedelta(days=14)
            zhuanzheng_deadline = full_member_date_est - timedelta(days=7)
            if today >= remind_date:
                days_left = (zhuanzheng_deadline - today).days
                reminders.append(self._make(
                    mid, name, "转正申请提醒",
                    f"{name}预备期即将满1年，请提醒其写转正申请（还剩{days_left}天）",
                    due_date=zhuanzheng_deadline.isoformat(),
                ))

        # ── Rule 7: 每天扫描逾期事件 ──
        overdue_events = self._timeline.check_overdue_events(
            type("Repo", (), {"get_all_members": lambda: [member]})()
        )
        for oe in overdue_events:
            reminders.append(self._make(
                mid, name, "⚠️ 逾期事件",
                f"{name} - {oe['event_type']} 已逾期{oe['overdue_days']}天（原定{oe['expected_date']}）",
                due_date=oe["expected_date"],
                is_overdue=True,
            ))

        return reminders

    def _make(
        self,
        member_id: Any,
        member_name: str,
        title: str,
        description: str,
        due_date: str,
        is_overdue: bool = False,
    ) -> dict[str, Any]:
        """构造一条提醒字典"""
        prefix = "🔴 " if is_overdue else ""
        return {
            "member_id": member_id,
            "member_name": member_name,
            "title": f"{prefix}{title}",
            "description": description,
            "due_date": due_date,
            "is_sent": False,
            "is_overdue": is_overdue,
        }

    def get_daily_brief(
        self, repo: Any, today: Optional[date] = None
    ) -> str:
        """生成每日简报字符串（用于 Hermes Cron 推送）

        Args:
            repo: Repository 实例
            today: 参考日期

        Returns:
            str: 格式化的每日简报文本
        """
        if today is None:
            today = date.today()

        all_reminders = self.generate_reminders(repo, today)

        # 分组
        overdue = [r for r in all_reminders if r.get("is_overdue")]
        upcoming = [r for r in all_reminders if not r.get("is_overdue")]

        # 获取缺失材料信息
        missing_materials: list[str] = []
        try:
            from partymate.tools.material_checklist import get_missing_materials
            members = repo.get_all_members()
            for m in members:
                missing = get_missing_materials(m, repo)
                for mat in missing:
                    missing_materials.append(f"{m.get('name', '')} - {mat}")
        except Exception:
            pass

        lines: list[str] = []
        lines.append("📋 PartyMate 每日简报")
        lines.append(f"📅 {today.isoformat()}")
        lines.append("")

        if upcoming:
            lines.append(f"📌 待办事项（{len(upcoming)}项）：")
            for i, r in enumerate(upcoming[:10], 1):
                lines.append(f"  {i}. {r['member_name']} - {r['description']}")
            if len(upcoming) > 10:
                lines.append(f"  ...及其他{len(upcoming) - 10}项")
        else:
            lines.append("✅ 无待办事项")

        lines.append("")

        if overdue:
            lines.append(f"🔴 已逾期（{len(overdue)}项）：")
            for i, r in enumerate(overdue[:5], 1):
                lines.append(f"  {i}. {r['member_name']} - {r['description']}")
            if len(overdue) > 5:
                lines.append(f"  ...及其他{len(overdue) - 5}项")
        else:
            lines.append("✅ 无逾期事项")

        lines.append("")

        if missing_materials:
            lines.append(f"📂 材料缺失（{len(missing_materials)}项）：")
            for i, m in enumerate(missing_materials[:5], 1):
                lines.append(f"  {i}. {m}")
            if len(missing_materials) > 5:
                lines.append(f"  ...及其他{len(missing_materials) - 5}项")
        else:
            lines.append("✅ 材料齐全")

        return "\n".join(lines)
