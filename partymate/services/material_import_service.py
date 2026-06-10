from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from partymate.db.repository import Repository
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
                files.append(record)
                if parsed.get("error"):
                    failed_files.append(Path(raw_name).name)

        batch = self.repo.update_material_import_batch(
            batch["id"],
            total_files=len(files),
            failed_files=len(failed_files),
            recognized_files=0,
            needs_review_files=0,
            status="completed",
        )

        return {
            "batch": batch,
            "files": files,
            "skipped_files": skipped_files,
            "failed_files": failed_files,
        }
