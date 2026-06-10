from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from partymate.db.models import MATERIALS_PER_STAGE
from partymate.db.repository import Repository


class MaterialCheckService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def run_for_member(
        self,
        member_id: int,
        batch_id: int | None = None,
    ) -> dict[str, Any]:
        member = self.repo.get_member(member_id)
        batch = (
            self.repo.get_material_import_batch(batch_id)
            if batch_id is not None
            else self.repo.get_latest_material_import_batch(member_id)
        )
        files = self.repo.list_material_files(batch["id"])

        result: dict[str, Any] = {
            "summary": {
                "member_id": member_id,
                "batch_id": batch["id"],
                "error_count": 0,
                "warning_count": 0,
                "review_count": 0,
            },
            "errors": [],
            "warnings": [],
            "needs_review": [],
            "recognized_materials": [
                item["material_type"]
                for item in files
                if item.get("material_type") not in ("", "unknown")
            ],
            "missing_materials": [],
        }

        self._check_missing_materials(member, files, result)
        self._check_duplicates(files, result)
        self._check_stage_sequence(member, files, result)
        self._check_identity(member, files, result)
        self._check_review_items(files, result)

        result["summary"]["error_count"] = len(result["errors"])
        result["summary"]["warning_count"] = len(result["warnings"])
        result["summary"]["review_count"] = len(result["needs_review"])

        self.repo.create_member_material_check(
            member_id=member_id,
            batch_id=batch["id"],
            status="completed",
            error_count=result["summary"]["error_count"],
            warning_count=result["summary"]["warning_count"],
            review_count=result["summary"]["review_count"],
            summary_json=json.dumps(result, ensure_ascii=False),
        )
        return result

    def _issue(
        self,
        code: str,
        severity: str,
        title: str,
        detail: str,
        evidence: list[str],
    ) -> dict[str, Any]:
        return {
            "code": code,
            "severity": severity,
            "title": title,
            "detail": detail,
            "evidence": evidence,
            "suggested_action": (
                "核对阶段顺序并补齐前置材料"
                if severity == "warning"
                else "人工复核并补齐材料"
            ),
        }

    def _check_missing_materials(
        self,
        member: dict[str, Any],
        files: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        stage_order = ["applicant", "activist", "candidate", "probationary", "full_member"]
        current_index = stage_order.index(member["stage"])
        expected: list[str] = []
        for stage in stage_order[: current_index + 1]:
            expected.extend(MATERIALS_PER_STAGE.get(stage, []))

        recognized = {
            item["material_type"]
            for item in files
            if item.get("material_type") not in ("", "unknown")
        }
        missing = [
            material_name
            for material_name in expected
            if material_name not in recognized and not material_name.startswith("季度思想汇报")
        ]
        result["missing_materials"].extend(missing)
        if missing:
            result["errors"].append(
                self._issue(
                    "missing_required_material",
                    "error",
                    "缺少必备材料",
                    "存在未导入的必备材料",
                    missing[:5],
                )
            )

    def _check_duplicates(
        self,
        files: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        seen: dict[str, list[str]] = {}
        for item in files:
            material_type = item.get("material_type")
            if not material_type or material_type == "unknown":
                continue
            seen.setdefault(material_type, []).append(item["original_name"])

        for material_type, names in seen.items():
            if material_type == "思想汇报":
                continue
            if len(names) > 1:
                result["errors"].append(
                    self._issue(
                        "duplicate_material",
                        "error",
                        "重复材料",
                        f"{material_type} 被导入了多次",
                        names,
                    )
                )

    def _check_stage_sequence(
        self,
        member: dict[str, Any],
        files: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        stage_order = {
            "applicant": 0,
            "activist": 1,
            "candidate": 2,
            "probationary": 3,
            "full_member": 4,
        }
        current_order = stage_order[member["stage"]]
        for item in files:
            material_stage = item.get("material_stage")
            if not material_stage:
                continue
            if stage_order.get(material_stage, current_order) > current_order:
                result["warnings"].append(
                    self._issue(
                        "stage_sequence_conflict",
                        "warning",
                        "阶段顺序可疑",
                        f"发现超出当前阶段的材料：{item['original_name']}",
                        [item["original_name"]],
                    )
                )

    def _check_identity(
        self,
        member: dict[str, Any],
        files: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        for item in files:
            text_path = item.get("full_text_path")
            if not text_path:
                continue

            text = Path(text_path).read_text(encoding="utf-8")
            if member.get("name") and member["name"] not in text:
                result["needs_review"].append(
                    self._issue(
                        "identity_conflict",
                        "needs_review",
                        "身份字段可能冲突",
                        f"{item['original_name']} 未匹配到成员姓名 {member['name']}",
                        [item["original_name"]],
                    )
                )
                continue

            if (
                member.get("major")
                and member["major"] not in text
                and any(keyword in text for keyword in ("计算机", "软件工程"))
            ):
                result["needs_review"].append(
                    self._issue(
                        "identity_conflict",
                        "needs_review",
                        "身份字段可能冲突",
                        f"{item['original_name']} 的专业信息与成员档案不一致",
                        [item["original_name"]],
                    )
                )

    def _check_review_items(
        self,
        files: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        for item in files:
            if item.get("needs_review"):
                result["needs_review"].append(
                    self._issue(
                        "unresolved_import_file",
                        "needs_review",
                        "待人工确认文件",
                        f"{item['original_name']} 需要人工复核",
                        [item["original_name"]],
                    )
                )
