"""
PartyMate TimelineEngine — 自动时间线生成器

基于《贵州省发展党员工作规程（试行）》和《贵州师范大学组织发展工作专项培训手册》
自动为成员生成各阶段预期时间线事件。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

# 尝试导入 Repository（DB 层可能尚未创建，使用 TYPE_CHECKING 风格引用）
try:
    from partymate.db.repository import Repository
except ImportError:
    Repository = None  # type: ignore

# ──────────────────────────────────────────────
# 阶段映射（与 DEVPLAN.md §2.1 一致）
# ──────────────────────────────────────────────
STAGE_ORDER = [
    "applicant",       # 申请入党
    "activist",        # 入党积极分子
    "candidate",       # 发展对象
    "probationary",    # 预备党员
    "full_member",     # 正式党员
]

# 阶段序号 → 归档文件夹名
STAGE_FOLDER_NAMES = {
    "applicant": "01_入党申请",
    "activist": "02_积极分子",
    "candidate": "03_发展对象",
    "probationary": "04_预备党员",
    "full_member": "05_转正",
}

# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _parse_date(d: Any) -> Optional[date]:
    """将 ISO 日期字符串或 date 对象转为 date"""
    if d is None:
        return None
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return date.fromisoformat(d)
        except (ValueError, TypeError):
            return None
    return None


def _add_months(src: date, months: int) -> date:
    """在日期上增加 N 个月（处理月尾溢出）"""
    total = src.month - 1 + months
    y = src.year + total // 12
    m = total % 12 + 1
    # 取目标月最后一天（防止 1月31日+1月→2月28日这种溢出）
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    d = min(src.day, last_day)
    return date(y, m, d)


def _next_quarter_end(src: date) -> date:
    """返回 src 所处季度末（3月31日/6月30日/9月30日/12月31日）"""
    q_month = math.ceil(src.month / 3) * 3
    import calendar
    last_day = calendar.monthrange(src.year, q_month)[1]
    return date(src.year, q_month, last_day)


def _next_semester_end(src: date) -> date:
    """返回最近的学期末（6月30日或12月31日），从 src 之后算起"""
    if src.month <= 6:
        return date(src.year, 6, 30)
    return date(src.year, 12, 31)


def _next_semester_start(src: date) -> date:
    """返回最近的学期开学周（3月第1周或9月第1周），从 src 之后算起"""
    if src.month <= 2:
        return date(src.year, 3, 1)
    if src.month <= 8:
        return date(src.year, 9, 1)
    return date(src.year + 1, 3, 1)


def _weekday_or_next(d: date) -> date:
    """若日期落在周末（周六/日），顺延到下周一"""
    while d.weekday() >= 5:  # 5=周六, 6=周日
        d += timedelta(days=1)
    return d


def _add_workdays(d: date, n: int) -> date:
    """增加 N 个工作日"""
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


# ──────────────────────────────────────────────
# 主引擎
# ──────────────────────────────────────────────

class TimelineEngine:
    """自动时间线生成器

    根据成员当前阶段和关键日期，自动推断后续所有必须完成的事件及其预期日期。
    完全基于 stdlib，零外部依赖。
    """

    def generate_events(self, member_dict: dict[str, Any]) -> list[dict[str, Any]]:
        """根据成员信息，生成完整的预期时间线事件列表

        Args:
            member_dict: 包含成员阶段、关键日期的字典
                - name, stage, apply_date, activist_date, candidate_date,
                  probationary_date, full_member_date

        Returns:
            list[dict]: 事件字典列表，每个包含:
                - event_type, expected_date, status='pending', notes
        """
        events: list[dict[str, Any]] = []
        stage = member_dict.get("stage", "applicant")
        apply_date = _parse_date(member_dict.get("apply_date"))

        # ── 所有申请人都需要的事件 ──
        if stage in ("applicant", "activist", "candidate", "probationary", "full_member"):
            if apply_date:
                # 1. 递交申请（已完成事件，标记为 completed）
                events.append({
                    "event_type": "递交申请",
                    "expected_date": apply_date.isoformat(),
                    "status": "completed",
                    "notes": f"{member_dict.get('name', '')} 递交入党申请书",
                })

                # 2. 入党谈话（申请书递交后 1 个月内）
                talk_date = _weekday_or_next(apply_date + timedelta(days=30))
                events.append({
                    "event_type": "入党谈话",
                    "expected_date": talk_date.isoformat(),
                    "status": "completed" if stage != "applicant" else "pending",
                    "notes": "收到申请书后1个月内完成入党谈话",
                })

        # ── 申请阶段 → 积极分子阶段 ──
        if stage in ("activist", "candidate", "probationary", "full_member"):
            if apply_date:
                # 3. 确定积极分子（申请书递交至少 3 个月后，大学场景 12 月/6 月集中确定）
                min_activist_date = _add_months(apply_date, 3)
                # 取最近的 6 月或 12 月
                if min_activist_date.month <= 6:
                    activist_est = date(min_activist_date.year, 6, 30)
                else:
                    activist_est = date(min_activist_date.year, 12, 31)
                if activist_est < min_activist_date:
                    # 如果已经过了，推到下一个周期
                    if min_activist_date.month <= 6:
                        activist_est = date(min_activist_date.year + 1, 6, 30)
                    else:
                        activist_est = date(min_activist_date.year + 1, 12, 31)

                events.append({
                    "event_type": "确定积极分子",
                    "expected_date": activist_est.isoformat(),
                    "status": "completed" if stage != "activist" else "pending",
                    "notes": "递交申请书至少3个月后，12月/6月集中确定",
                })

                # 4-5. 积极分子阶段的周期性事件
                activist_date = _parse_date(member_dict.get("activist_date")) or activist_est

                # 思想汇报：每季度至少1篇（3/6/9/12月）
                for q in range(1, 5):
                    q_month = q * 3
                    report_date = date(activist_date.year, q_month, 30 if q_month < 12 else 31)
                    if report_date < activist_date:
                        report_date = date(activist_date.year + 1, q_month, 30 if q_month < 12 else 31)
                    status = "pending"
                    # 如果已到发展对象或之后，已完成
                    if stage in ("candidate", "probationary", "full_member"):
                        status = "completed"
                    events.append({
                        "event_type": "思想汇报（积极分子）",
                        "expected_date": report_date.isoformat(),
                        "status": status,
                        "notes": f"积极分子季度思想汇报（{report_date.year}年Q{q}）",
                    })

                # 半年考察：每学期末（6月/12月）
                for half in [6, 12]:
                    exam_date_1 = date(activist_date.year, half, 30 if half == 6 else 31)
                    if exam_date_1 < activist_date:
                        exam_date_1 = date(activist_date.year + 1, half, 30 if half == 6 else 31)
                    st = "pending"
                    if stage in ("candidate", "probationary", "full_member"):
                        st = "completed"
                    events.append({
                        "event_type": "半年考察（积极分子）",
                        "expected_date": exam_date_1.isoformat(),
                        "status": st,
                        "notes": f"积极分子半年考察（{exam_date_1.year}年{'上' if half == 6 else '下'}学期）",
                    })

                    # 第二学期也可能需要
                    exam_date_2 = date(activist_date.year + 1, 6 if half == 12 else 12, 30 if half == 12 else 31)
                    if exam_date_2 > activist_date and (stage in ("activist", "candidate", "probationary", "full_member")):
                        st2 = "pending"
                        if stage in ("candidate", "probationary", "full_member"):
                            st2 = "completed"
                        events.append({
                            "event_type": "半年考察（积极分子）",
                            "expected_date": exam_date_2.isoformat(),
                            "status": st2,
                            "notes": f"积极分子半年考察（{exam_date_2.year}年{'上' if exam_date_2.month == 6 else '下'}学期）",
                        })

        # ── 积极分子 → 发展对象 ──
        if stage in ("candidate", "probationary", "full_member"):
            activist_date = _parse_date(member_dict.get("activist_date"))
            if activist_date:
                # 6. 确定发展对象（积极分子满1年后，大学场景5月/11月）
                min_candidate_date = _add_months(activist_date, 12)
                # 取最近 5 月或 11 月
                if min_candidate_date.month <= 5:
                    candidate_est = date(min_candidate_date.year, 5, 31)
                elif min_candidate_date.month <= 11:
                    candidate_est = date(min_candidate_date.year, 11, 30)
                else:
                    candidate_est = date(min_candidate_date.year + 1, 5, 31)
                if candidate_est < min_candidate_date:
                    if candidate_est.month == 5:
                        candidate_est = date(min_candidate_date.year, 11, 30)
                        if candidate_est < min_candidate_date:
                            candidate_est = date(min_candidate_date.year + 1, 5, 31)
                    else:
                        candidate_est = date(min_candidate_date.year + 1, 5, 31)

                st = "completed" if stage != "candidate" else "pending"
                events.append({
                    "event_type": "确定发展对象",
                    "expected_date": candidate_est.isoformat(),
                    "status": st,
                    "notes": "积极分子培养满1年后确定发展对象（5月/11月）",
                })

                # 7. 公示（发展对象，5个工作日）
                pub_start = _add_workdays(candidate_est, 1)
                pub_end = _add_workdays(pub_start, 4)
                events.append({
                    "event_type": "公示（发展对象）",
                    "expected_date": pub_end.isoformat(),
                    "status": st if stage == "candidate" else "completed",
                    "notes": "发展对象公示，5个工作日",
                })

                # 8. 短期培训（不少于3天/24学时）
                train_date = _add_months(candidate_est, 1)
                events.append({
                    "event_type": "短期培训",
                    "expected_date": train_date.isoformat(),
                    "status": st if stage == "candidate" else "completed",
                    "notes": "发展对象短期培训（不少于3天/24学时）",
                })

                # 9. 政治审查
                review_date = _add_months(candidate_est, 1)
                events.append({
                    "event_type": "政治审查",
                    "expected_date": review_date.isoformat(),
                    "status": st if stage == "candidate" else "completed",
                    "notes": "对发展对象进行政治审查",
                })

                # 10. 党委预审
                precheck_date = _add_months(candidate_est, 2)
                events.append({
                    "event_type": "党委预审",
                    "expected_date": precheck_date.isoformat(),
                    "status": st if stage == "candidate" else "completed",
                    "notes": "支委会审查→党委预审",
                })

        # ── 发展对象 → 预备党员 ──
        if stage in ("probationary", "full_member"):
            candidate_date = _parse_date(member_dict.get("candidate_date"))
            if not candidate_date:
                # 根据 activist_date 推算
                candidate_date = _parse_date(member_dict.get("activist_date"))
                if candidate_date:
                    candidate_date = _add_months(candidate_date, 12)

            if candidate_date:
                # 11. 填写入党志愿书
                events.append({
                    "event_type": "填写入党志愿书",
                    "expected_date": candidate_date.isoformat(),
                    "status": "completed",
                    "notes": "填写《中国共产党入党志愿书》",
                })

                # 12. 支部大会讨论（预审合格后1个月内）
                meeting_date = _add_months(candidate_date, 1)
                st = "completed" if stage == "full_member" else "pending"
                events.append({
                    "event_type": "支部大会（接收预备党员）",
                    "expected_date": _weekday_or_next(meeting_date).isoformat(),
                    "status": st,
                    "notes": "预审合格后1个月内召开支部大会讨论接收预备党员",
                })

                # 13. 党委谈话
                talk_date_2 = _add_months(meeting_date, 1)
                events.append({
                    "event_type": "党委谈话",
                    "expected_date": talk_date_2.isoformat(),
                    "status": st,
                    "notes": "党委审批前与预备党员谈话",
                })

                # 14. 党委审批（支部大会后3个月内，最长6个月）
                approve_date = _add_months(meeting_date, 3)
                events.append({
                    "event_type": "党委审批",
                    "expected_date": approve_date.isoformat(),
                    "status": "completed",
                    "notes": "支部大会通过后3个月内党委审批（最长6个月）",
                })

                # 15. 入党宣誓
                oath_date = _add_months(approve_date, 1)
                events.append({
                    "event_type": "入党宣誓",
                    "expected_date": _weekday_or_next(oath_date).isoformat(),
                    "status": "completed" if stage == "full_member" else "pending",
                    "notes": "党委批准后及时举行入党宣誓",
                })

        # ── 预备党员 → 转正 ──
        if stage in ("probationary", "full_member"):
            probationary_date = _parse_date(member_dict.get("probationary_date"))
            if not probationary_date:
                # 推算：发展对象日期 + ~6个月
                candidate_date = _parse_date(member_dict.get("candidate_date"))
                if candidate_date:
                    probationary_date = _add_months(candidate_date, 6)

            if probationary_date:
                # 预备期 = 1年
                full_member_date_est = _add_months(probationary_date, 12)

                # 预备期思想汇报（每季度）
                for q in range(1, 5):
                    q_month = q * 3
                    report_date = date(probationary_date.year, q_month, 30 if q_month < 12 else 31)
                    if report_date < probationary_date:
                        report_date = date(probationary_date.year + 1, q_month, 30 if q_month < 12 else 31)
                    if report_date > full_member_date_est:
                        continue
                    st = "completed" if stage == "full_member" else "pending"
                    events.append({
                        "event_type": "思想汇报（预备党员）",
                        "expected_date": report_date.isoformat(),
                        "status": st,
                        "notes": f"预备党员季度思想汇报（{report_date.year}年Q{q}）",
                    })

                # 半年考察（预备期）
                exam_prep = _next_semester_end(probationary_date)
                st = "completed" if stage == "full_member" else "pending"
                events.append({
                    "event_type": "半年考察（预备党员）",
                    "expected_date": exam_prep.isoformat(),
                    "status": st,
                    "notes": f"预备党员半年考察（{exam_prep.year}年{'上' if exam_prep.month == 6 else '下'}学期）",
                })

                # 16. 提交转正申请（预备期满前1周）
                zhuanzheng_deadline = full_member_date_est - timedelta(days=7)
                if stage == "full_member":
                    st_zz = "completed"
                else:
                    st_zz = "pending"
                events.append({
                    "event_type": "提交转正申请",
                    "expected_date": zhuanzheng_deadline.isoformat(),
                    "status": st_zz,
                    "notes": "预备期满前1周提交转正申请书",
                })

                # 17. 支部大会讨论转正（收到申请后1个月内）
                zhuanzheng_meeting = _add_months(zhuanzheng_deadline, 1)
                st_zm = "completed" if stage == "full_member" else "pending"
                events.append({
                    "event_type": "支部大会（转正）",
                    "expected_date": _weekday_or_next(zhuanzheng_meeting).isoformat(),
                    "status": st_zm,
                    "notes": "收到转正申请后1个月内支部大会讨论",
                })

                # 18. 公示（转正，5个工作日）
                pub_zz_start = _add_workdays(zhuanzheng_meeting, 1)
                pub_zz_end = _add_workdays(pub_zz_start, 4)
                events.append({
                    "event_type": "公示（转正）",
                    "expected_date": pub_zz_end.isoformat(),
                    "status": st_zm,
                    "notes": "转正公示，5个工作日",
                })

                # 19. 党委审批转正（3个月内）
                approve_zz = _add_months(zhuanzheng_meeting, 3)
                events.append({
                    "event_type": "党委审批（转正）",
                    "expected_date": approve_zz.isoformat(),
                    "status": st_zm,
                    "notes": "转正决议后3个月内党委审批",
                })

                # 20. 材料归档
                archive_date = _add_months(approve_zz, 1)
                events.append({
                    "event_type": "材料归档",
                    "expected_date": archive_date.isoformat(),
                    "status": "pending" if stage == "full_member" else "pending",
                    "notes": "转正后完整党员档案归档",
                })

        return events

    def get_next_deadline(self, member_dict: dict[str, Any]) -> dict[str, Any]:
        """返回距离当前最近的待处理事件

        Args:
            member_dict: 成员信息字典

        Returns:
            dict: {event_type, expected_date, days_remaining} 或空字典（无待办）
        """
        today = date.today()
        events = self.generate_events(member_dict)
        nearest: Optional[dict[str, Any]] = None

        for ev in events:
            if ev["status"] != "pending":
                continue
            ev_date = _parse_date(ev["expected_date"])
            if ev_date is None:
                continue
            if ev_date < today:
                # 已逾期，但也算最近的
                days = (today - ev_date).days
            else:
                days = (ev_date - today).days

            if nearest is None or ev_date < _parse_date(nearest["expected_date"]):
                nearest = {
                    "event_type": ev["event_type"],
                    "expected_date": ev["expected_date"],
                    "days_remaining": -days if ev_date < today else days,
                    "is_overdue": ev_date < today,
                }

        return nearest or {}

    def check_overdue_events(self, repo: Any) -> list[dict[str, Any]]:
        """扫描所有成员的待办事件，返回已逾期的列表

        Args:
            repo: Repository 实例（含 get_all_members, get_events 等方法）

        Returns:
            list[dict]: 逾期事件列表
        """
        today = date.today()
        overdue: list[dict[str, Any]] = []

        try:
            members = repo.get_all_members()
        except Exception:
            return overdue

        for member in members:
            events = self.generate_events(member)
            for ev in events:
                if ev["status"] != "pending":
                    continue
                ev_date = _parse_date(ev["expected_date"])
                if ev_date and ev_date < today:
                    overdue.append({
                        "member_id": member.get("id"),
                        "member_name": member.get("name", ""),
                        "event_type": ev["event_type"],
                        "expected_date": ev["expected_date"],
                        "overdue_days": (today - ev_date).days,
                        "notes": ev.get("notes", ""),
                    })

        return overdue

    def get_school_calendar_events(self, year: int) -> list[dict[str, str]]:
        """返回固定学校日历提醒事件

        Args:
            year: 年份

        Returns:
            list[dict]: 学校日历事件列表
        """
        return [
            {
                "event_type": "开学",
                "event_date": f"{year}-03-01",
                "description": "春季学期开学第1周，请提醒有意向同学递交入党申请书",
            },
            {
                "event_type": "开学",
                "event_date": f"{year}-09-01",
                "description": "秋季学期开学第1周，请提醒有意向同学递交入党申请书",
            },
            {
                "event_type": "期末考察",
                "event_date": f"{year}-06-30",
                "description": "学期末，请完成本学期积极分子/预备党员半年考察",
            },
            {
                "event_type": "期末考察",
                "event_date": f"{year}-12-31",
                "description": "学期末，请完成本学期积极分子/预备党员半年考察",
            },
            {
                "event_type": "思想汇报收集",
                "event_date": f"{year}-03-31",
                "description": "请收集本季度思想汇报（3月）",
            },
            {
                "event_type": "思想汇报收集",
                "event_date": f"{year}-06-30",
                "description": "请收集本季度思想汇报（6月）",
            },
            {
                "event_type": "思想汇报收集",
                "event_date": f"{year}-09-30",
                "description": "请收集本季度思想汇报（9月）",
            },
            {
                "event_type": "思想汇报收集",
                "event_date": f"{year}-12-31",
                "description": "请收集本季度思想汇报（12月）",
            },
        ]
