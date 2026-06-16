from __future__ import annotations

from typing import Any

from partymate.db.models import Importance, MemoryKind
from partymate.db.repository import Repository


class MemberMemoryService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def create_memory(
        self,
        member_id: int,
        kind: str,
        content: str,
        title: str = "",
        importance: int = 2,
        pinned: bool = False,
        source: str = "",
    ) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        normalized_content = (content or "").strip()
        if not normalized_content:
            raise ValueError("content is required")

        return self.repo.create_member_memory(
            member_id=member_id,
            kind=normalized_kind,
            title=(title or "").strip(),
            content=normalized_content,
            importance=self._normalize_importance(importance),
            pinned=1 if pinned else 0,
            source=(source or "").strip(),
        )

    def list_memories(
        self,
        member_id: int,
        include_merged: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self.repo.list_member_memories(
            member_id,
            include_merged=include_merged,
            limit=limit,
        )

    def update_memory(
        self,
        memory_id: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        current = self.repo.get_member_memory(memory_id)
        if not current:
            raise ValueError(f"memory {memory_id} not found")

        payload: dict[str, Any] = {}
        if "title" in kwargs:
            payload["title"] = (kwargs.get("title") or "").strip()
        if "content" in kwargs:
            content = (kwargs.get("content") or "").strip()
            if not content:
                raise ValueError("content is required")
            payload["content"] = content
        if "importance" in kwargs:
            payload["importance"] = self._normalize_importance(kwargs["importance"])
        if "pinned" in kwargs:
            payload["pinned"] = 1 if kwargs["pinned"] else 0

        return self.repo.update_member_memory(memory_id, **payload)

    def delete_memory(self, memory_id: int) -> bool:
        return self.repo.delete_member_memory(memory_id)

    def merge_memories(
        self,
        member_id: int,
        memory_ids: list[int],
        kind: str,
        content: str,
        title: str = "",
        importance: int = 2,
        pinned: bool = False,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(memory_ids))
        if len(unique_ids) < 2:
            raise ValueError("at least two memories are required for merge")

        source_rows = [self.repo.get_member_memory(memory_id) for memory_id in unique_ids]
        if any(not row for row in source_rows):
            raise ValueError("source memory not found")
        if any(int(row["member_id"]) != member_id for row in source_rows):
            raise ValueError("cannot merge memories across members")

        merged = self.create_memory(
            member_id=member_id,
            kind=kind,
            content=content,
            title=title,
            importance=importance,
            pinned=pinned,
            source="merge",
        )

        for row in source_rows:
            self.repo.update_member_memory(
                int(row["id"]),
                merged_into_id=merged["id"],
                pinned=0,
            )
        return merged

    def build_agent_context(self, member_id: int, limit: int = 8) -> str:
        member = self.repo.get_member(member_id)
        if not member:
            raise ValueError(f"member {member_id} not found")

        memories = self.list_memories(member_id, include_merged=False, limit=limit)
        lines = [
            "以下是当前对话绑定的成员上下文，只能围绕该成员提供建议。",
            f"成员姓名: {member.get('name', '')}",
            f"当前阶段: {member.get('stage', '')}",
            f"成员状态: {member.get('status', '')}",
            f"年级: {member.get('grade', '')}",
            f"专业: {member.get('major', '')}",
            f"学号: {member.get('student_id', '')}",
            f"备注: {member.get('notes', '')}",
            "成员记忆:",
        ]
        if not memories:
            lines.append("- 无")
        else:
            for item in memories:
                pin_tag = "置顶" if item.get("pinned") else "普通"
                title = item.get("title") or item.get("kind") or "记忆"
                lines.append(
                    f"- [{pin_tag}|{item.get('kind', '')}|重要度{item.get('importance', 2)}] "
                    f"{title}: {item.get('content', '')}"
                )
        return "\n".join(lines)

    def _normalize_kind(self, kind: str) -> str:
        try:
            return MemoryKind((kind or "").strip()).value
        except ValueError as exc:
            raise ValueError(f"invalid memory kind: {kind}") from exc

    def _normalize_importance(self, importance: Any) -> int:
        try:
            value = int(importance)
        except (TypeError, ValueError):
            value = int(Importance.MEDIUM)
        return max(int(Importance.LOW), min(int(Importance.HIGH), value))
