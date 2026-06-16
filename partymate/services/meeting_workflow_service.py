"""PartyMate v2 — Meeting Workflow Closure Service

Closes the meeting workflow loop:
1. Parse action items from a structured meeting summary
2. Auto-write action items as reminders
3. Track meeting action status (pending → confirmed → done)
"""

from __future__ import annotations

import json
import re
from typing import Any

from partymate.db.repository import Repository


class MeetingWorkflowService:
    """Closes the meeting workflow: parse → save reminders → track status."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def parse_and_write_actions(
        self,
        meeting_summary_json: str,
        meeting_title: str = "",
        member_id: int | None = None,
    ) -> dict[str, Any]:
        """Parse action items from a meeting summary and write them to reminders.

        Args:
            meeting_summary_json: JSON string from parse_meeting_notes()
            meeting_title: Optional title for the meeting
            member_id: Optional member to associate actions with

        Returns:
            Dict with actions written and any skipped items
        """
        actions = self._extract_actions(meeting_summary_json, meeting_title)
        written: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for action in actions:
            action_text = action.get("action_text", "").strip()
            if not action_text or len(action_text) < 5:
                skipped.append(action)
                continue

            due_date = action.get("due_date", "")
            if not due_date:
                due_date = self._extract_deadline(action_text)

            # Create meeting action record
            meeting_action = self.repo.create_meeting_action(
                action_text=action_text,
                meeting_title=meeting_title,
                responsible_person=action.get("responsible_person", ""),
                due_date=due_date,
                status="pending",
                member_id=member_id,
                source_meeting_id=meeting_title,
            )

            # Also write to reminders if linked to a member
            if member_id and member_id > 0:
                reminder = self.repo.add_reminder(
                    member_id=member_id,
                    title=f"[会议待办] {action_text[:40]}",
                    description=action_text,
                    due_date=due_date or "",
                    remind_before_days=3,
                )
                if reminder.get("id"):
                    self.repo.update_meeting_action(
                        meeting_action["id"],
                        reminder_id=reminder["id"],
                    )
                    meeting_action["reminder_id"] = reminder["id"]

            written.append(meeting_action)

        return {
            "written_count": len(written),
            "skipped_count": len(skipped),
            "actions": written,
            "skipped": skipped,
        }

    def _extract_actions(
        self,
        meeting_summary_json: str,
        meeting_title: str = "",
    ) -> list[dict[str, Any]]:
        """Extract structured action items from a meeting summary JSON."""
        try:
            data = json.loads(meeting_summary_json) if isinstance(meeting_summary_json, str) else meeting_summary_json
        except (json.JSONDecodeError, TypeError):
            return []

        actions: list[dict[str, Any]] = []

        # 1. Extract from structured action_items field
        for item in data.get("action_items", []):
            task_text = item.get("task", "").strip()
            if not task_text or task_text.startswith("（未识别"):
                continue
            actions.append({
                "action_text": task_text,
                "responsible_person": item.get("assignee", ""),
                "due_date": item.get("deadline", ""),
            })

        # 2. Fallback: parse raw text for action patterns
        if not actions:
            raw_text = json.dumps(data, ensure_ascii=False)
            actions = self._regex_extract_actions(raw_text)

        return actions

    def _regex_extract_actions(self, text: str) -> list[dict[str, Any]]:
        """Regex-based fallback to find action items in raw text."""
        actions: list[dict[str, Any]] = []
        patterns = [
            r"(?:请|要求|安排|由)\s*(\S{2,6})\s*(?:负责|牵头|落实|完成)([^，。\\n]{5,60})",
            r"(?:下一步|后续|接下来)\s*(?:工作)?[：:，,]?\s*([^，。\\n]{5,60})",
            r"(\S{2,6})\s*(?:负责|牵头|起草|落实|完成)\s*([^，。\\n]{5,60})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                action_text = match.group(0).strip()[:60]
                person = groups[0] if len(groups) > 0 else ""
                actions.append({
                    "action_text": action_text,
                    "responsible_person": person,
                    "due_date": "",
                })
        return actions

    def _extract_deadline(self, text: str) -> str:
        """Extract a due date from action text."""
        match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日]?", text)
        if match:
            return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
        match = re.search(r"(\d{1,2})月(\d{1,2})[日]?", text)
        if match:
            import datetime
            year = datetime.date.today().year
            return f"{year}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"
        return ""

    def list_pending_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all pending meeting actions."""
        return self.repo.list_meeting_actions(status="pending", limit=limit)

    def confirm_action(self, action_id: int) -> dict[str, Any]:
        """Mark a meeting action as confirmed (in progress)."""
        return self.repo.update_meeting_action(action_id, status="confirmed")

    def complete_action(self, action_id: int) -> dict[str, Any]:
        """Mark a meeting action as done."""
        action = self.repo.get_meeting_action(action_id)
        if action and action.get("reminder_id"):
            self.repo.add_reminder(
                member_id=action.get("member_id") or 0,
                title=f"[已完成] {action.get('action_text', '')[:40]}",
                description=f"会议待办已完成: {action.get('action_text', '')}",
                due_date="",
            )
        return self.repo.update_meeting_action(action_id, status="done")