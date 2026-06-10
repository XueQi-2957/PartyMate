from __future__ import annotations

import json
from typing import Any

from partymate.db.repository import Repository


class MemberViewService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def build_member_detail(self, member_id: int) -> dict[str, Any]:
        member = self.repo.get_member(member_id)
        if not member:
            return {}
        pending_ocr_tasks = self._build_pending_ocr_tasks(member_id)

        return {
            **member,
            "timeline": [
                {
                    "date": item.get("event_date") or item.get("expected_date") or "",
                    "title": item.get("event_type", ""),
                    "description": item.get("notes", ""),
                    "type": "stage_event",
                }
                for item in member.get("events", [])
            ],
            "materials": [
                {
                    **item,
                    "name": item.get("material_name", ""),
                    "submitted": bool(item.get("is_submitted")),
                }
                for item in member.get("materials", [])
            ],
            "latest_import_batch": self.repo.get_latest_material_import_batch(member_id),
            "recent_import_batches": self.repo.list_material_import_batches(member_id),
            "latest_material_check": self._decode_check(
                self.repo.get_latest_material_check(member_id)
            ),
            "pending_ocr_tasks": pending_ocr_tasks,
            "pending_ocr_task_count": len(pending_ocr_tasks),
        }

    def build_dashboard(self) -> dict[str, Any]:
        members = self.repo.get_members(status="active")
        stage_keys = [
            "applicant",
            "activist",
            "candidate",
            "probationary",
            "full_member",
        ]
        stages = {key: {"count": 0, "members": []} for key in stage_keys}
        for member in members:
            detail = self.build_member_detail(member["id"])
            stages[detail["stage"]]["count"] += 1
            stages[detail["stage"]]["members"].append(detail)
        return {"total": len(members), "stages": stages}

    def build_reminders(self) -> list[dict[str, Any]]:
        reminders = self.repo.get_reminders()
        members = {
            member["id"]: member["name"]
            for member in self.repo.get_members(status="active")
        }
        return [
            {
                "id": item["id"],
                "member_id": item.get("member_id"),
                "member_name": members.get(item.get("member_id"), ""),
                "type": (
                    "material_pending"
                    if "材料" in item.get("title", "")
                    else "stage_delayed"
                ),
                "title": item.get("title", ""),
                "detail": item.get("description", ""),
                "due_date": item.get("due_date", ""),
            }
            for item in reminders
        ]

    def _decode_check(self, row: dict[str, Any]) -> dict[str, Any]:
        if not row:
            return {}
        decoded = json.loads(row["summary_json"])
        decoded["id"] = row["id"]
        decoded["created_at"] = row["created_at"]
        return decoded

    def _build_pending_ocr_tasks(self, member_id: int) -> list[dict[str, Any]]:
        tasks = self.repo.list_member_ocr_tasks(member_id, status="review_required")
        result: list[dict[str, Any]] = []
        for task in tasks:
            material_file = self.repo.get_material_file(task["material_file_id"])
            confidence_summary = self._decode_json(
                task.get("confidence_summary_json", "{}"),
                {},
            )
            result.append(
                {
                    "task_id": task["id"],
                    "material_file_id": task["material_file_id"],
                    "original_name": material_file.get("original_name", ""),
                    "review_status": material_file.get("review_status", ""),
                    "created_at": task.get("created_at", ""),
                    "confidence_summary": confidence_summary,
                }
            )
        return result

    def _decode_json(self, payload: str, default: Any) -> Any:
        if not payload:
            return default
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return default
