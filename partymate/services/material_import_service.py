from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from partymate.db.models import DOC_TYPE_TO_STAGE, MATERIAL_NAME_ALIASES, MATERIALS_PER_STAGE
from partymate.db.repository import Repository
from partymate.tools.doc_check import detect_doc_type
from partymate.tools.file_parser import SUPPORTED_EXTS, parse_file


class MaterialImportService:
    def __init__(self, repo: Repository, data_root: Path) -> None:
        self.repo = repo
        self.data_root = data_root

    def import_archive(
        self,
        member_id: int,
        archive_name: str,
        archive_bytes: bytes,
    ) -> dict[str, Any]:
        batch = self.repo.create_material_import_batch(
            member_id=member_id,
            archive_name=archive_name,
            archive_path="",
            extract_dir="",
            status="processing",
        )

        batch_dir = (
            self.data_root
            / "material_imports"
            / f"member_{member_id}"
            / f"batch_{batch['id']}"
        )
        source_dir = batch_dir / "source"
        extract_dir = batch_dir / "extracted"
        parsed_dir = batch_dir / "parsed"
        source_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        parsed_dir.mkdir(parents=True, exist_ok=True)

        archive_path = source_dir / archive_name
        archive_path.write_bytes(archive_bytes)

        batch = self.repo.update_material_import_batch(
            batch["id"],
            archive_path=str(archive_path),
            extract_dir=str(extract_dir),
        )

        files: list[dict[str, Any]] = []
        skipped_files: list[str] = []
        failed_files: list[str] = []

        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue

                raw_name = info.filename
                target_path = (extract_dir / raw_name).resolve()
                extract_root = extract_dir.resolve()
                if extract_root not in target_path.parents and target_path != extract_root:
                    continue

                ext = Path(raw_name).suffix.lower()
                if ext not in SUPPORTED_EXTS:
                    skipped_files.append(raw_name)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target_path.open("wb") as dst:
                    dst.write(src.read())

                parsed = parse_file(target_path)
                record = self.repo.add_material_file(
                    batch_id=batch["id"],
                    member_id=member_id,
                    original_name=Path(raw_name).name,
                    stored_path=str(target_path),
                    extension=ext,
                    parser_type=parsed.get("type", "unknown"),
                    parse_status="parsed" if not parsed.get("error") else "error",
                )
                if parsed.get("error"):
                    updated = self.repo.update_material_file(
                        record["id"],
                        error_message=parsed["error"],
                        needs_review=1,
                    )
                    files.append(updated)
                    failed_files.append(Path(raw_name).name)
                    continue

                material_type, material_stage, recognition_source, needs_review = self._identify_material(
                    Path(raw_name).name,
                    parsed.get("text", ""),
                )
                needs_review = needs_review or self._requires_ocr_review(parsed)
                full_text_path = self._persist_parsed_text(
                    parsed_dir,
                    record["id"],
                    parsed.get("text", ""),
                )
                updated = self.repo.update_material_file(
                    record["id"],
                    material_type=material_type,
                    material_stage=material_stage,
                    recognition_source=recognition_source,
                    text_excerpt=parsed.get("preview", ""),
                    full_text_path=full_text_path,
                    page_count=parsed.get("pages", 0),
                    needs_review=1 if needs_review else 0,
                )
                if updated["parser_type"] == "image" and updated.get("needs_review"):
                    ocr_task = self.repo.create_ocr_task(
                        member_id=member_id,
                        batch_id=batch["id"],
                        material_file_id=record["id"],
                        status="review_required",
                        raw_segments_json=json.dumps(
                            parsed.get("ocr_segments", []),
                            ensure_ascii=False,
                        ),
                        confidence_summary_json=json.dumps(
                            self._build_confidence_summary(
                                parsed.get("ocr_segments", []),
                            ),
                            ensure_ascii=False,
                        ),
                    )
                    updated = self.repo.update_material_file(
                        record["id"],
                        ocr_task_id=ocr_task["id"],
                        review_status="review_required",
                    )
                files.append(updated)

        recognized_files = sum(
            1 for item in files if item.get("material_type") not in ("", "unknown")
        )
        needs_review_files = sum(1 for item in files if item.get("needs_review"))
        batch = self.repo.update_material_import_batch(
            batch["id"],
            total_files=len(files),
            failed_files=len(failed_files),
            recognized_files=recognized_files,
            needs_review_files=needs_review_files,
            status="completed_with_review" if needs_review_files else "completed",
        )

        return {
            "batch": batch,
            "files": files,
            "skipped_files": skipped_files,
            "failed_files": failed_files,
        }

    def _identify_material(
        self,
        original_name: str,
        parsed_text: str,
    ) -> tuple[str, str, str, bool]:
        normalized_name = original_name.lower()
        stage_map = self._material_stage_map()

        for material_name, stage in stage_map.items():
            if material_name.lower() in normalized_name:
                return material_name, stage, "filename_exact", False

        for material_name, aliases in MATERIAL_NAME_ALIASES.items():
            if any(alias.lower() in normalized_name for alias in aliases):
                return (
                    material_name,
                    DOC_TYPE_TO_STAGE.get(material_name, stage_map.get(material_name, "")),
                    "filename_alias",
                    False,
                )

        doc_type = detect_doc_type(parsed_text or "")
        if doc_type:
            return doc_type, DOC_TYPE_TO_STAGE.get(doc_type, ""), "content_doc_type", False

        needs_review = len("".join((parsed_text or "").split())) < 30
        return "unknown", "", "unknown", needs_review

    def _persist_parsed_text(self, parsed_dir: Path, file_id: int, text: str) -> str:
        full_text_path = parsed_dir / f"file_{file_id}.txt"
        full_text_path.write_text(text, encoding="utf-8")
        return str(full_text_path)

    def _build_confidence_summary(
        self,
        ocr_segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        confidences = [
            float(item.get("confidence", 0.0))
            for item in ocr_segments
            if item.get("confidence") is not None
        ]
        if not confidences:
            return {
                "segment_count": 0,
                "low_confidence_count": 0,
                "average_confidence": 0.0,
                "min_confidence": 0.0,
                "max_confidence": 0.0,
            }
        return {
            "segment_count": len(confidences),
            "low_confidence_count": sum(1 for item in confidences if item < 0.60),
            "average_confidence": round(sum(confidences) / len(confidences), 4),
            "min_confidence": min(confidences),
            "max_confidence": max(confidences),
        }

    def _requires_ocr_review(self, parsed: dict[str, Any]) -> bool:
        if parsed.get("type") != "image":
            return False
        text = "".join((parsed.get("text", "") or "").split())
        if len(text) < 30:
            return True
        for item in parsed.get("ocr_segments", []):
            confidence = item.get("confidence")
            if confidence is not None and float(confidence) < 0.60:
                return True
        return False

    def _material_stage_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for stage, materials in MATERIALS_PER_STAGE.items():
            for material_name in materials:
                mapping.setdefault(material_name, stage)
        return mapping
