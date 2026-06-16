"""PartyMate v2 — database models and enums."""

from enum import IntEnum, StrEnum


class Stage(StrEnum):
    """发展党员五个阶段"""
    APPLICANT = "applicant"          # 申请入党
    ACTIVIST = "activist"            # 入党积极分子
    CANDIDATE = "candidate"          # 发展对象
    PROBATIONARY = "probationary"    # 预备党员
    FULL_MEMBER = "full_member"      # 正式党员

    @property
    def order(self) -> int:
        """stage progression order (0-indexed)"""
        return _STAGE_ORDER[self]

    def next_stage(self) -> "Stage | None":
        """Return the next stage, or None if already at full_member."""
        stages = list(type(self))
        try:
            idx = stages.index(self)
        except ValueError:
            return None
        if idx + 1 >= len(stages):
            return None
        return stages[idx + 1]

    def previous_stage(self) -> "Stage | None":
        """Return the previous stage, or None if already at applicant."""
        stages = list(type(self))
        try:
            idx = stages.index(self)
        except ValueError:
            return None
        if idx - 1 < 0:
            return None
        return stages[idx - 1]


_STAGE_ORDER = {
    Stage.APPLICANT: 0,
    Stage.ACTIVIST: 1,
    Stage.CANDIDATE: 2,
    Stage.PROBATIONARY: 3,
    Stage.FULL_MEMBER: 4,
}


class EventStatus(StrEnum):
    """时间线事件状态"""
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class MemberStatus(StrEnum):
    """成员状态"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DROPPED = "dropped"


class MemoryKind(StrEnum):
    """成员记忆类型"""

    SUMMARY = "summary"
    RISK = "risk"
    INSTRUCTION = "instruction"
    CORRECTION = "correction"
    NOTE = "note"


class OCRTaskStatus(StrEnum):
    """OCR 任务状态"""

    PENDING = "pending"
    REVIEW_REQUIRED = "review_required"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class AgentRunStatus(StrEnum):
    """Agent 运行状态"""

    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class MeetingActionStatus(StrEnum):
    """会议待办状态"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DONE = "done"


class Importance(IntEnum):
    """通用重要度"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


# ── 各阶段所需材料清单 ──────────────────────────────────────────
MATERIALS_PER_STAGE = {
    "applicant": [
        "入党申请书",
        "入党谈话记录",
        "身份证复印件",
        "学历证书复印件",
    ],
    "activist": [
        "党员推荐入党积极分子登记表",
        "群团组织推优表",
        "确定为积极分子的支委会会议记录",
        "入党积极分子培养教育考察登记表",
        "季度思想汇报Q1",
        "季度思想汇报Q2",
        "季度思想汇报Q3",
        "季度思想汇报Q4",
        "半年考察记录上",
        "半年考察记录下",
        "列为积极分子通知书",
    ],
    "candidate": [
        "听取意见记录",
        "确定为发展对象的支委会会议记录",
        "发展对象公示材料",
        "备案报告及批复",
        "综合性政审报告",
        "函调材料",
        "短期培训结业证书",
        "入党介绍人信息",
    ],
    "probationary": [
        "预审请示",
        "预审批复",
        "中国共产党入党志愿书",
        "接收预备党员支部大会会议记录",
        "票决结果",
        "预备党员教育考察登记表",
        "审批批复",
    ],
    "full_member": [
        "转正申请书",
        "预备期思想汇报Q1",
        "预备期思想汇报Q2",
        "预备期思想汇报Q3",
        "预备期思想汇报Q4",
        "转正支部大会会议记录",
        "转正公示材料",
        "转正审批批复",
    ],
}


MATERIAL_NAME_ALIASES = {
    "入党申请书": ["入党申请", "申请书"],
    "入党谈话记录": ["谈话记录", "谈话"],
    "思想汇报": ["思想汇报"],
    "半年考察记录": ["考察记录", "考察意见", "培养考察"],
    "转正申请书": ["转正申请", "转正申请书"],
    "中国共产党入党志愿书": ["入党志愿书", "入党志愿"],
    "政治审查": ["政审", "政治审查", "综合性政审报告"],
    "短期培训结业证书": ["培训结业", "结业证", "党校培训"],
    "公示材料": ["公示", "公示材料"],
    "支部大会会议记录": ["支部大会", "会议记录", "票决"],
}


DOC_TYPE_TO_STAGE = {
    "入党申请书": "applicant",
    "思想汇报": "activist",
    "转正申请": "full_member",
    "入党志愿书": "probationary",
    "考察意见": "activist",
}
