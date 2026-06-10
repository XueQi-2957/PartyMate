from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from partymate.db.repository import Repository

HERE = Path(__file__).resolve().parents[2]


class OCRReviewService:
    def __init__(self, repo: Repository, data_root: Path | None = None) -> None:
        self.repo = repo
        self.data_root = data_root or (HERE / "data")

    def build_task_detail(self, task_id: int) -> dict[str, Any]:
        task = self.repo.get_ocr_task(task_id)
        if not task:
            return {}

        material_file = self.repo.get_material_file(task["material_file_id"])
        segments = self._decode_json(task.get("raw_segments_json", "[]"), [])
        return {
            "task": task,
            "file": material_file,
            "raw_text": self._read_text(material_file.get("full_text_path", "")),
            "confirmed_text": self._read_text(task.get("confirmed_text_path", "")),
            "confidence_summary": self._decode_json(
                task.get("confidence_summary_json", "{}"),
                {},
            ),
            "low_confidence_segments": [
                item
                for item in segments
                if float(item.get("confidence", 0.0)) < 0.60
            ],
        }

    def confirm_task(
        self,
        task_id: int,
        confirmed_text: str,
        review_notes: str = "",
    ) -> dict[str, Any]:
        task = self.repo.get_ocr_task(task_id)
        if not task:
            raise ValueError(f"OCR task {task_id} not found")

        normalized_text = confirmed_text.strip()
        if not normalized_text:
            raise ValueError("confirmed_text is required")

        review_dir = self._review_dir(task)
        review_dir.mkdir(parents=True, exist_ok=True)
        confirmed_path = review_dir / f"task_{task_id}.txt"
        confirmed_path.write_text(normalized_text, encoding="utf-8")

        updated = self.repo.update_ocr_task(
            task_id,
            status="confirmed",
            confirmed_text_path=str(confirmed_path),
            review_notes=review_notes,
        )
        self.repo.update_material_file(
            task["material_file_id"],
            review_status="confirmed",
            needs_review=0,
        )
        return updated

    def resolve_file_text(self, material_file: dict[str, Any]) -> str:
        task = {}
        if material_file.get("ocr_task_id"):
            task = self.repo.get_ocr_task(int(material_file["ocr_task_id"]))
        elif material_file.get("id"):
            task = self.repo.get_ocr_task_by_material_file(int(material_file["id"]))

        if (
            task
            and task.get("status") == "confirmed"
            and task.get("confirmed_text_path")
        ):
            confirmed = self._read_text(task["confirmed_text_path"])
            if confirmed:
                return confirmed

        return self._read_text(material_file.get("full_text_path", ""))

    def _review_dir(self, task: dict[str, Any]) -> Path:
        batch = self.repo.get_material_import_batch(task["batch_id"])
        extract_dir = batch.get("extract_dir", "")
        if extract_dir and Path(extract_dir).is_absolute():
            return Path(extract_dir).parent / "ocr_reviews"
        return (
            self.data_root
            / "material_imports"
            / f"member_{task['member_id']}"
            / f"batch_{task['batch_id']}"
            / "ocr_reviews"
        )

    def _read_text(self, path_str: str) -> str:
        if not path_str:
            return ""
        path = Path(path_str)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _decode_json(self, payload: str, default: Any) -> Any:
        if not payload:
            return default
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return default
