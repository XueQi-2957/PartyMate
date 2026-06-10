# Member Material Workbench V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first member-centered material workbench increment for PartyMate by adding zip archive import, member-level package checks, frontend-ready dashboard/member DTOs, and member-detail UI integration.

**Architecture:** Keep the current Python local monolith. Extend the SQLite repository with import/check tables, add focused services for archive import, package checking, and DTO shaping, then refactor the Starlette app into a testable app factory and wire the existing static frontend to the new member-material workflow.

**Tech Stack:** Python 3.11, sqlite3, Starlette, Starlette TestClient, unittest, zipfile, pathlib, existing `partymate.tools.file_parser`

---

## File Map

### New Files

- `partymate/services/__init__.py`
  - service package export surface
- `partymate/services/material_import_service.py`
  - zip persistence, safe extraction, parser invocation, deterministic classification, batch summaries
- `partymate/services/material_check_service.py`
  - deterministic member-package checks and result persistence
- `partymate/services/member_view_service.py`
  - frontend-ready DTO shaping for dashboard, member detail, and reminders
- `tests/__init__.py`
  - unittest package marker
- `tests/support.py`
  - shared test helpers for temporary repos and zip creation
- `tests/test_repository_material_workbench.py`
  - repository schema and persistence tests
- `tests/test_material_import_service.py`
  - archive import, extraction safety, classification, text persistence tests
- `tests/test_material_check_service.py`
  - deterministic package-check tests
- `tests/test_member_view_service.py`
  - DTO shaping tests
- `tests/test_web_material_workbench_api.py`
  - API contract tests
- `tests/test_static_material_workbench_assets.py`
  - static asset wiring smoke tests

### Modified Files

- `partymate/db/repository.py`
  - new tables plus batch/file/check CRUD and query helpers
- `partymate/web/server.py`
  - app factory, dependency injection, new endpoints, DTO-backed existing endpoints
- `partymate/web/static/index.html`
  - hidden zip input plus member detail panels
- `partymate/web/static/app.js`
  - member archive upload flow, package-check flow, DTO-compatible renderers
- `partymate/db/setup.py`
  - sample-data output alignment for the new dashboard shape

## Task 1: Create Test Scaffolding And Repository Persistence

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/support.py`
- Create: `tests/test_repository_material_workbench.py`
- Modify: `partymate/db/repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/__init__.py

# tests/support.py
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from partymate.db.repository import Repository


def make_temp_repo():
    temp_dir = tempfile.TemporaryDirectory()
    repo = Repository(db_path=str(Path(temp_dir.name) / "partymate-test.db"))
    return temp_dir, repo


def make_zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            archive.writestr(name, data)
    return buffer.getvalue()

# tests/test_repository_material_workbench.py
from __future__ import annotations

import unittest

from tests.support import make_temp_repo


class RepositoryMaterialWorkbenchTests(unittest.TestCase):
    def test_create_tables_adds_material_workbench_tables(self):
        temp_dir, repo = make_temp_repo()
        try:
            names = {
                row["name"]
                for row in repo.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertTrue(
                {
                    "material_import_batches",
                    "material_files",
                    "member_material_checks",
                }.issubset(names)
            )
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_repository_persists_batch_file_and_check_rows(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="data/material_imports/member_1/batch_1/source/materials.zip",
                extract_dir="data/material_imports/member_1/batch_1/extracted",
                status="processing",
            )
            material_file = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书.docx",
                stored_path="data/material_imports/member_1/batch_1/extracted/入党申请书.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            repo.update_material_file(
                material_file["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                text_excerpt="敬爱的党组织",
                full_text_path="data/material_imports/member_1/batch_1/parsed/file_1.txt",
                page_count=1,
            )
            repo.create_member_material_check(
                member_id=member["id"],
                batch_id=batch["id"],
                status="completed",
                error_count=1,
                warning_count=0,
                review_count=0,
                summary_json='{"errors":[{"code":"missing_required_material"}]}',
            )

            latest_batch = repo.get_latest_material_import_batch(member["id"])
            latest_check = repo.get_latest_material_check(member["id"])
            files = repo.list_material_files(batch["id"])

            self.assertEqual(latest_batch["archive_name"], "materials.zip")
            self.assertEqual(files[0]["material_type"], "入党申请书")
            self.assertEqual(latest_check["error_count"], 1)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_repository_material_workbench -v`

Expected: `FAIL` because `Repository` does not yet create the new tables or expose methods like `create_material_import_batch`.

- [ ] **Step 3: Write the minimal implementation**

```python
# partymate/db/repository.py
class Repository:
    def create_tables(self) -> None:
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS members (...);
                CREATE TABLE IF NOT EXISTS timeline_events (...);
                CREATE TABLE IF NOT EXISTS materials (...);
                CREATE TABLE IF NOT EXISTS reminders (...);

                CREATE TABLE IF NOT EXISTS material_import_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    archive_name TEXT NOT NULL,
                    archive_path TEXT NOT NULL,
                    extract_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    recognized_files INTEGER NOT NULL DEFAULT 0,
                    needs_review_files INTEGER NOT NULL DEFAULT 0,
                    failed_files INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS material_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL REFERENCES material_import_batches(id),
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    parser_type TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    material_type TEXT DEFAULT '',
                    material_stage TEXT DEFAULT '',
                    recognition_source TEXT DEFAULT '',
                    text_excerpt TEXT DEFAULT '',
                    full_text_path TEXT DEFAULT '',
                    page_count INTEGER NOT NULL DEFAULT 0,
                    needs_review INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS member_material_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    batch_id INTEGER REFERENCES material_import_batches(id),
                    status TEXT NOT NULL,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );
            """)

    def create_material_import_batch(
        self,
        member_id: int,
        archive_name: str,
        archive_path: str,
        extract_dir: str,
        status: str,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO material_import_batches
               (member_id, archive_name, archive_path, extract_dir, status)
               VALUES (?, ?, ?, ?, ?)""",
            (member_id, archive_name, archive_path, extract_dir, status),
        )
        self.conn.commit()
        return self.get_material_import_batch(int(cursor.lastrowid))

    def get_material_import_batch(self, batch_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM material_import_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        return _row_to_dict(row)

    def update_material_import_batch(self, batch_id: int, **kwargs: Any) -> dict[str, Any]:
        sets = []
        params: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(batch_id)
        self.conn.execute(
            f"UPDATE material_import_batches SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_material_import_batch(batch_id)

    def get_latest_material_import_batch(self, member_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM material_import_batches WHERE member_id = ? ORDER BY id DESC LIMIT 1",
            (member_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_material_import_batches(self, member_id: int, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM material_import_batches WHERE member_id = ? ORDER BY id DESC LIMIT ?",
            (member_id, limit),
        ).fetchall()
        return _rows_to_dicts(rows)

    def add_material_file(self, batch_id: int, member_id: int, original_name: str, stored_path: str,
                          extension: str, parser_type: str, parse_status: str) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO material_files
               (batch_id, member_id, original_name, stored_path, extension, parser_type, parse_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (batch_id, member_id, original_name, stored_path, extension, parser_type, parse_status),
        )
        self.conn.commit()
        return self.get_material_file(int(cursor.lastrowid))

    def get_material_file(self, file_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM material_files WHERE id = ?",
            (file_id,),
        ).fetchone()
        return _row_to_dict(row)

    def update_material_file(self, file_id: int, **kwargs: Any) -> dict[str, Any]:
        sets = []
        params: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(file_id)
        self.conn.execute(
            f"UPDATE material_files SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_material_file(file_id)

    def list_material_files(self, batch_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM material_files WHERE batch_id = ? ORDER BY id ASC",
            (batch_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    def create_member_material_check(
        self,
        member_id: int,
        batch_id: int | None,
        status: str,
        error_count: int,
        warning_count: int,
        review_count: int,
        summary_json: str,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO member_material_checks
               (member_id, batch_id, status, error_count, warning_count, review_count, summary_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (member_id, batch_id, status, error_count, warning_count, review_count, summary_json),
        )
        self.conn.commit()
        return self.get_member_material_check(int(cursor.lastrowid))

    def get_member_material_check(self, check_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM member_material_checks WHERE id = ?",
            (check_id,),
        ).fetchone()
        return _row_to_dict(row)

    def get_latest_material_check(self, member_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM member_material_checks WHERE member_id = ? ORDER BY id DESC LIMIT 1",
            (member_id,),
        ).fetchone()
        return _row_to_dict(row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_repository_material_workbench -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/support.py tests/test_repository_material_workbench.py partymate/db/repository.py
git commit -m "test: add repository coverage for material workbench"
```

## Task 2: Implement Safe Archive Import And Extraction

**Files:**
- Create: `partymate/services/__init__.py`
- Create: `partymate/services/material_import_service.py`
- Create: `tests/test_material_import_service.py`
- Modify: `partymate/db/repository.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_material_import_service.py
from __future__ import annotations

import unittest
from pathlib import Path

from partymate.services.material_import_service import MaterialImportService
from tests.support import make_temp_repo, make_zip_bytes


class MaterialImportServiceExtractionTests(unittest.TestCase):
    def test_import_archive_blocks_zip_slip_and_skips_unsupported_files(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            zip_bytes = make_zip_bytes(
                {
                    "../evil.txt": "blocked",
                    "notes/readme.txt": "skip me",
                    "docs/入党申请书.docx": b"fake-docx",
                }
            )
            service = MaterialImportService(repo=repo, data_root=Path(temp_dir.name))

            result = service.import_archive(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_bytes=zip_bytes,
            )

            stored_names = [item["original_name"] for item in result["files"]]
            self.assertEqual(stored_names, ["入党申请书.docx"])
            self.assertEqual(result["skipped_files"], ["notes/readme.txt"])
            self.assertEqual(result["batch"]["status"], "completed")
            self.assertFalse((Path(temp_dir.name) / "evil.txt").exists())
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_material_import_service.MaterialImportServiceExtractionTests.test_import_archive_blocks_zip_slip_and_skips_unsupported_files -v`

Expected: `ERROR` because `partymate.services.material_import_service` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# partymate/services/__init__.py
from .material_import_service import MaterialImportService

__all__ = ["MaterialImportService"]

# partymate/services/material_import_service.py
from __future__ import annotations

import zipfile
from pathlib import Path

from partymate.db.repository import Repository
from partymate.tools.file_parser import SUPPORTED_EXTS, parse_file


class MaterialImportService:
    def __init__(self, repo: Repository, data_root: Path) -> None:
        self.repo = repo
        self.data_root = data_root

    def import_archive(self, member_id: int, archive_name: str, archive_bytes: bytes) -> dict:
        batch = self.repo.create_material_import_batch(
            member_id=member_id,
            archive_name=archive_name,
            archive_path="",
            extract_dir="",
            status="processing",
        )
        batch_dir = self.data_root / "material_imports" / f"member_{member_id}" / f"batch_{batch['id']}"
        source_dir = batch_dir / "source"
        extract_dir = batch_dir / "extracted"
        parsed_dir = batch_dir / "parsed"
        source_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        parsed_dir.mkdir(parents=True, exist_ok=True)

        archive_path = source_dir / archive_name
        archive_path.write_bytes(archive_bytes)
        self.repo.update_material_import_batch(
            batch["id"],
            archive_path=str(archive_path),
            extract_dir=str(extract_dir),
        )

        files = []
        skipped_files: list[str] = []
        failed_files: list[str] = []

        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                raw_name = info.filename
                target = (extract_dir / raw_name).resolve()
                if extract_dir.resolve() not in target.parents and target != extract_dir.resolve():
                    continue
                ext = Path(raw_name).suffix.lower()
                if ext not in SUPPORTED_EXTS:
                    skipped_files.append(raw_name)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("wb") as dst:
                    dst.write(src.read())
                parsed = parse_file(target)
                record = self.repo.add_material_file(
                    batch_id=batch["id"],
                    member_id=member_id,
                    original_name=Path(raw_name).name,
                    stored_path=str(target),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_material_import_service.MaterialImportServiceExtractionTests.test_import_archive_blocks_zip_slip_and_skips_unsupported_files -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/__init__.py partymate/services/material_import_service.py tests/test_material_import_service.py partymate/db/repository.py
git commit -m "feat: add safe archive extraction service"
```

## Task 3: Add Deterministic Classification And Parsed Text Persistence

**Files:**
- Modify: `partymate/services/material_import_service.py`
- Modify: `partymate/db/repository.py`
- Modify: `tests/test_material_import_service.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from partymate.services.material_import_service import MaterialImportService
from tests.support import make_temp_repo, make_zip_bytes


class MaterialImportServiceClassificationTests(unittest.TestCase):
    @patch("partymate.services.material_import_service.parse_file")
    def test_import_archive_classifies_files_and_persists_text_outputs(self, mock_parse):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            zip_bytes = make_zip_bytes(
                {
                    "入党申请书.docx": b"fake-docx-a",
                    "思想汇报Q1.docx": b"fake-docx-b",
                }
            )
            mock_parse.side_effect = [
                {
                    "filename": "入党申请书.docx",
                    "type": "docx",
                    "text": "敬爱的党组织，我志愿加入中国共产党。",
                    "pages": 1,
                    "preview": "敬爱的党组织",
                    "error": None,
                },
                {
                    "filename": "思想汇报Q1.docx",
                    "type": "docx",
                    "text": "思想汇报：我在本季度认真学习。",
                    "pages": 1,
                    "preview": "思想汇报",
                    "error": None,
                },
            ]

            service = MaterialImportService(repo=repo, data_root=Path(temp_dir.name))
            result = service.import_archive(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_bytes=zip_bytes,
            )

            files = repo.list_material_files(result["batch"]["id"])
            self.assertEqual(result["batch"]["recognized_files"], 2)
            self.assertEqual(files[0]["material_type"], "入党申请书")
            self.assertEqual(files[1]["material_type"], "思想汇报")
            self.assertTrue(Path(files[0]["full_text_path"]).exists())
            self.assertEqual(files[0]["recognition_source"], "filename_exact")
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_material_import_service.MaterialImportServiceClassificationTests.test_import_archive_classifies_files_and_persists_text_outputs -v`

Expected: `FAIL` because the current import service does not classify files or persist parsed text files.

- [ ] **Step 3: Write minimal implementation**

```python
# partymate/services/material_import_service.py
from partymate.db.models import DOC_TYPE_TO_STAGE, MATERIAL_NAME_ALIASES
from partymate.tools.doc_check import detect_doc_type


class MaterialImportService:
    def _identify_material(self, original_name: str, parsed_text: str) -> tuple[str, str, str, bool]:
        normalized_name = original_name.lower()
        for material_name, aliases in MATERIAL_NAME_ALIASES.items():
            if material_name.lower() in normalized_name:
                return material_name, "", "filename_exact", False
            if any(alias.lower() in normalized_name for alias in aliases):
                return material_name, "", "filename_alias", False

        doc_type = detect_doc_type(parsed_text or "")
        if doc_type:
            return doc_type, DOC_TYPE_TO_STAGE.get(doc_type, ""), "content_doc_type", False

        needs_review = len("".join((parsed_text or "").split())) < 30
        return "unknown", "", "unknown", True

    def _persist_parsed_text(self, parsed_dir: Path, file_id: int, text: str) -> str:
        full_text_path = parsed_dir / f"file_{file_id}.txt"
        full_text_path.write_text(text, encoding="utf-8")
        return str(full_text_path)

    def import_archive(self, member_id: int, archive_name: str, archive_bytes: bytes) -> dict:
        ...
                parsed = parse_file(target)
                record = self.repo.add_material_file(...)
                if parsed.get("error"):
                    failed_files.append(Path(raw_name).name)
                    self.repo.update_material_file(
                        record["id"],
                        error_message=parsed["error"],
                        needs_review=1,
                    )
                    files.append(self.repo.get_material_file(record["id"]))
                    continue

                material_type, material_stage, recognition_source, needs_review = self._identify_material(
                    Path(raw_name).name,
                    parsed.get("text", ""),
                )
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
                files.append(updated)

        recognized_files = sum(1 for item in files if item.get("material_type") not in ("", "unknown"))
        needs_review_files = sum(1 for item in files if item.get("needs_review"))
        batch_status = "completed_with_review" if needs_review_files else "completed"
        batch = self.repo.update_material_import_batch(
            batch["id"],
            total_files=len(files),
            recognized_files=recognized_files,
            needs_review_files=needs_review_files,
            failed_files=len(failed_files),
            status=batch_status,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_material_import_service.MaterialImportServiceClassificationTests.test_import_archive_classifies_files_and_persists_text_outputs -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/material_import_service.py partymate/db/repository.py tests/test_material_import_service.py
git commit -m "feat: classify imported member materials"
```

## Task 4: Implement Deterministic Member Package Checks

**Files:**
- Create: `partymate/services/material_check_service.py`
- Create: `tests/test_material_check_service.py`
- Modify: `partymate/services/__init__.py`
- Modify: `partymate/db/repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_material_check_service.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from partymate.services.material_check_service import MaterialCheckService
from tests.support import make_temp_repo


class MaterialCheckServiceTests(unittest.TestCase):
    def test_run_for_member_reports_missing_duplicate_and_stage_conflicts(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                grade="2023级",
                major="计算机科学与技术",
                student_id="2023010001",
                apply_date="2026-03-01",
            )
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed",
            )
            text_dir = Path(temp_dir.name) / "texts"
            text_dir.mkdir()

            first = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书-1.docx",
                stored_path="a.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            second = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书-2.docx",
                stored_path="b.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            late_stage = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="转正申请书.docx",
                stored_path="c.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )

            (text_dir / "file_1.txt").write_text("张三 2023010001 敬爱的党组织 2026年3月1日", encoding="utf-8")
            (text_dir / "file_2.txt").write_text("张三 2023010001 敬爱的党组织 2026年3月1日", encoding="utf-8")
            (text_dir / "file_3.txt").write_text("张三 于2025年1月1日提出转正申请", encoding="utf-8")

            repo.update_material_file(
                first["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_1.txt"),
            )
            repo.update_material_file(
                second["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_2.txt"),
            )
            repo.update_material_file(
                late_stage["id"],
                material_type="转正申请书",
                material_stage="full_member",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_3.txt"),
            )

            result = MaterialCheckService(repo).run_for_member(member["id"], batch["id"])
            error_codes = {item["code"] for item in result["errors"]}
            warning_codes = {item["code"] for item in result["warnings"]}

            self.assertIn("duplicate_material", error_codes)
            self.assertIn("missing_required_material", error_codes)
            self.assertIn("stage_sequence_conflict", warning_codes)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_run_for_member_reports_identity_conflicts_and_review_items(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", major="计算机科学与技术", student_id="2023010001")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed_with_review",
            )
            text_dir = Path(temp_dir.name) / "texts"
            text_dir.mkdir()
            record = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="思想汇报Q1.docx",
                stored_path="a.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            (text_dir / "file_1.txt").write_text("李四 软件工程 2023010001 思想汇报", encoding="utf-8")
            repo.update_material_file(
                record["id"],
                material_type="思想汇报",
                material_stage="activist",
                recognition_source="filename_alias",
                full_text_path=str(text_dir / "file_1.txt"),
                needs_review=1,
            )

            result = MaterialCheckService(repo).run_for_member(member["id"], batch["id"])
            review_codes = {item["code"] for item in result["needs_review"]}

            self.assertIn("identity_conflict", review_codes)
            self.assertIn("unresolved_import_file", review_codes)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_material_check_service -v`

Expected: `ERROR` because `MaterialCheckService` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# partymate/services/material_check_service.py
from __future__ import annotations

import json
import re
from pathlib import Path

from partymate.db.models import MATERIALS_PER_STAGE
from partymate.db.repository import Repository


class MaterialCheckService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def run_for_member(self, member_id: int, batch_id: int | None = None) -> dict:
        member = self.repo.get_member(member_id)
        batch = (
            self.repo.get_material_import_batch(batch_id)
            if batch_id is not None
            else self.repo.get_latest_material_import_batch(member_id)
        )
        files = self.repo.list_material_files(batch["id"])

        result = {
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
            "recognized_materials": [item["material_type"] for item in files if item.get("material_type")],
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

    def _issue(self, code: str, severity: str, title: str, detail: str, evidence: list[str]) -> dict:
        return {
            "code": code,
            "severity": severity,
            "title": title,
            "detail": detail,
            "evidence": evidence,
            "suggested_action": "人工复核并补齐材料" if severity != "warning" else "核对阶段顺序",
        }

    def _check_missing_materials(self, member: dict, files: list[dict], result: dict) -> None:
        stage_order = ["applicant", "activist", "candidate", "probationary", "full_member"]
        current_index = stage_order.index(member["stage"])
        expected = []
        for stage in stage_order[: current_index + 1]:
            expected.extend(MATERIALS_PER_STAGE.get(stage, []))
        recognized = {item["material_type"] for item in files if item.get("material_type") not in ("", "unknown")}
        for material_name in expected:
            if material_name not in recognized and not material_name.startswith("季度思想汇报"):
                result["missing_materials"].append(material_name)
        if result["missing_materials"]:
            result["errors"].append(
                self._issue(
                    "missing_required_material",
                    "error",
                    "缺少必备材料",
                    "存在未导入的必备材料",
                    result["missing_materials"][:5],
                )
            )

    def _check_duplicates(self, files: list[dict], result: dict) -> None:
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

    def _check_stage_sequence(self, member: dict, files: list[dict], result: dict) -> None:
        stage_order = {"applicant": 0, "activist": 1, "candidate": 2, "probationary": 3, "full_member": 4}
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

    def _check_identity(self, member: dict, files: list[dict], result: dict) -> None:
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
            if member.get("major") and member["major"] not in text and re.search(r"(计算机|软件工程)", text):
                result["needs_review"].append(
                    self._issue(
                        "identity_conflict",
                        "needs_review",
                        "身份字段可能冲突",
                        f"{item['original_name']} 的专业信息与成员档案不一致",
                        [item["original_name"]],
                    )
                )

    def _check_review_items(self, files: list[dict], result: dict) -> None:
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

# partymate/services/__init__.py
from .material_check_service import MaterialCheckService
from .material_import_service import MaterialImportService

__all__ = ["MaterialImportService", "MaterialCheckService"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_material_check_service -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/material_check_service.py partymate/services/__init__.py tests/test_material_check_service.py partymate/db/repository.py
git commit -m "feat: add deterministic member material checks"
```

## Task 5: Build Frontend-Ready DTO Services

**Files:**
- Create: `partymate/services/member_view_service.py`
- Create: `tests/test_member_view_service.py`
- Modify: `partymate/services/__init__.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_member_view_service.py
from __future__ import annotations

import unittest

from partymate.services.member_view_service import MemberViewService
from tests.support import make_temp_repo


class MemberViewServiceTests(unittest.TestCase):
    def test_build_member_detail_returns_frontend_ready_fields(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", apply_date="2026-03-01", notes="重点培养")
            material = repo.get_materials(member["id"])[0]
            repo.submit_material(material["id"], file_path="archives/入党申请书.docx")
            service = MemberViewService(repo)

            detail = service.build_member_detail(member["id"])

            self.assertIn("timeline", detail)
            self.assertIn("latest_import_batch", detail)
            self.assertIn("latest_material_check", detail)
            self.assertEqual(detail["materials"][0]["name"], "入党申请书")
            self.assertIn("submitted", detail["materials"][0])
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_build_dashboard_returns_total_and_stage_groups(self):
        temp_dir, repo = make_temp_repo()
        try:
            repo.add_member(name="张三")
            repo.add_member(name="李四")
            service = MemberViewService(repo)

            dashboard = service.build_dashboard()

            self.assertIn("total", dashboard)
            self.assertIn("stages", dashboard)
            self.assertIn("applicant", dashboard["stages"])
            self.assertIn("members", dashboard["stages"]["applicant"])
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_member_view_service -v`

Expected: `ERROR` because `MemberViewService` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# partymate/services/member_view_service.py
from __future__ import annotations

import json

from partymate.db.repository import Repository


class MemberViewService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def build_member_detail(self, member_id: int) -> dict:
        member = self.repo.get_member(member_id)
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
            "latest_material_check": self._decode_check(self.repo.get_latest_material_check(member_id)),
        }

    def build_dashboard(self) -> dict:
        members = self.repo.get_members(status="active")
        stage_keys = ["applicant", "activist", "candidate", "probationary", "full_member"]
        stages = {
            key: {"count": 0, "members": []}
            for key in stage_keys
        }
        for member in members:
            detail = self.build_member_detail(member["id"])
            stages[detail["stage"]]["count"] += 1
            stages[detail["stage"]]["members"].append(detail)
        return {"total": len(members), "stages": stages}

    def build_reminders(self) -> list[dict]:
        return [
            {
                "id": item["id"],
                "member_id": item.get("member_id"),
                "member_name": "",
                "type": "material_pending" if "材料" in item.get("title", "") else "stage_delayed",
                "title": item.get("title", ""),
                "detail": item.get("description", ""),
                "due_date": item.get("due_date", ""),
            }
            for item in self.repo.get_reminders()
        ]

    def _decode_check(self, row: dict) -> dict:
        if not row:
            return {}
        decoded = json.loads(row["summary_json"])
        decoded["id"] = row["id"]
        decoded["created_at"] = row["created_at"]
        return decoded

# partymate/services/__init__.py
from .material_check_service import MaterialCheckService
from .material_import_service import MaterialImportService
from .member_view_service import MemberViewService

__all__ = ["MaterialImportService", "MaterialCheckService", "MemberViewService"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_member_view_service -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/member_view_service.py partymate/services/__init__.py tests/test_member_view_service.py
git commit -m "feat: add frontend-ready member view service"
```

## Task 6: Refactor The Starlette App And Add Material Workbench APIs

**Files:**
- Create: `tests/test_web_material_workbench_api.py`
- Modify: `partymate/web/server.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_material_workbench_api.py
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from partymate.web.server import create_app
from tests.support import make_temp_repo, make_zip_bytes


class MaterialWorkbenchApiTests(unittest.TestCase):
    @patch("partymate.services.material_import_service.parse_file")
    def test_import_endpoint_saves_member_archive_batch(self, mock_parse):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            mock_parse.return_value = {
                "filename": "入党申请书.docx",
                "type": "docx",
                "text": "敬爱的党组织",
                "pages": 1,
                "preview": "敬爱的党组织",
                "error": None,
            }
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            client = TestClient(app)
            zip_bytes = make_zip_bytes({"入党申请书.docx": b"fake-docx"})

            response = client.post(
                "/api/materials/archive/import",
                files={"file": ("materials.zip", zip_bytes, "application/zip")},
                data={"member_id": str(member["id"])},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["batch"]["recognized_files"], 1)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_material_check_endpoint_uses_latest_batch_when_batch_id_missing(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed",
            )
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            client = TestClient(app)

            response = client.post(f"/api/members/{member['id']}/materials/check", json={})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["batch_id"], batch["id"])
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_dashboard_and_member_endpoints_return_frontend_ready_shapes(self):
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            client = TestClient(app)

            dashboard = client.get("/api/dashboard")
            detail = client.get(f"/api/members/{member['id']}")

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("total", dashboard.json())
            self.assertIn("stages", dashboard.json())
            self.assertIn("timeline", detail.json()["member"])
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_web_material_workbench_api -v`

Expected: `ERROR` because `create_app()` and the new routes do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# partymate/web/server.py
from partymate.services import MaterialCheckService, MaterialImportService, MemberViewService


def create_app(repository: Repository | None = None, data_root: Path | None = None) -> Starlette:
    repo = repository or Repository()
    base_data_root = data_root or (HERE / "data")
    member_views = MemberViewService(repo)
    import_service = MaterialImportService(repo=repo, data_root=base_data_root)
    check_service = MaterialCheckService(repo)

    async def api_get_member(request):
        member = member_views.build_member_detail(int(request.path_params["member_id"]))
        if not member:
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        return JSONResponse({"member": member})

    async def api_dashboard(request):
        return JSONResponse(member_views.build_dashboard())

    async def api_reminders(request):
        return JSONResponse({"reminders": member_views.build_reminders()})

    async def api_material_archive_import(request):
        form = await request.form()
        file: UploadFile | None = form.get("file")
        member_id = int(form.get("member_id", "0"))
        if not file or not file.filename:
            return JSONResponse({"error": "未上传文件"}, status_code=400)
        if Path(file.filename).suffix.lower() != ".zip":
            return JSONResponse({"error": "仅支持 zip 材料包"}, status_code=400)
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        result = import_service.import_archive(
            member_id=member_id,
            archive_name=file.filename,
            archive_bytes=await file.read(),
        )
        return JSONResponse(result)

    async def api_member_material_check(request):
        member_id = int(request.path_params["member_id"])
        if not repo.get_member(member_id):
            return JSONResponse({"error": "成员未找到"}, status_code=404)
        body = await request.json() if request.method == "POST" else {}
        result = check_service.run_for_member(member_id, body.get("batch_id"))
        return JSONResponse(result)

    routes = [
        Route("/api/check-doc", api_check_doc, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/meeting", api_meeting, methods=["POST"]),
        Route("/api/content", api_content, methods=["POST"]),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/status", api_status),
        Route("/api/download", api_download),
        Route("/api/members", api_members),
        Route("/api/members", api_add_member, methods=["POST"]),
        Route("/api/members/{member_id}", api_get_member),
        Route("/api/members/{member_id}", api_update_member, methods=["PATCH"]),
        Route("/api/members/{member_id}", api_delete_member, methods=["DELETE"]),
        Route("/api/members/{member_id}/advance", api_advance, methods=["POST"]),
        Route("/api/members/{member_id}/materials", api_submit_material, methods=["POST"]),
        Route("/api/members/{member_id}/materials/check", api_member_material_check, methods=["POST"]),
        Route("/api/members/{member_id}/events", api_add_event, methods=["POST"]),
        Route("/api/materials/archive/import", api_material_archive_import, methods=["POST"]),
        Route("/api/dashboard", api_dashboard),
        Route("/api/reminders", api_reminders),
        Route("/api/members/import", api_import_members, methods=["POST"]),
        Mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"),
    ]
    return Starlette(debug=False, routes=routes)


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_web_material_workbench_api -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/web/server.py tests/test_web_material_workbench_api.py
git commit -m "feat: expose member material workbench api"
```

## Task 7: Wire The Static Frontend To The Member Material Workflow

**Files:**
- Create: `tests/test_static_material_workbench_assets.py`
- Modify: `partymate/web/static/index.html`
- Modify: `partymate/web/static/app.js`

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/test_static_material_workbench_assets.py
from __future__ import annotations

import unittest
from pathlib import Path


class StaticMaterialWorkbenchAssetTests(unittest.TestCase):
    def test_member_material_workbench_markup_and_scripts_exist(self):
        html = Path("partymate/web/static/index.html").read_text(encoding="utf-8")
        js = Path("partymate/web/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="memberArchiveInput"', html)
        self.assertIn("openMemberArchivePicker(", js)
        self.assertIn("handleMemberArchiveSelected(", js)
        self.assertIn("runMemberMaterialCheck(", js)
        self.assertIn("/api/materials/archive/import", js)
        self.assertIn("/materials/check", js)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `FAIL` because the current HTML and JS do not include the new archive import wiring.

- [ ] **Step 3: Write minimal implementation**

```html
<!-- partymate/web/static/index.html -->
<input type="file" id="memberArchiveInput" accept=".zip" style="display:none" onchange="handleMemberArchiveSelected(event)">
```

```javascript
// partymate/web/static/app.js
function openMemberArchivePicker(memberId) {
  _selectedMemberId = memberId;
  document.getElementById('memberArchiveInput').click();
}

async function handleMemberArchiveSelected(event) {
  const file = event.target.files[0];
  if (!file || !_selectedMemberId) return;
  const formData = new FormData();
  formData.append('member_id', String(_selectedMemberId));
  formData.append('file', file);

  const detailEl = document.getElementById('kanbanMemberDetail');
  detailEl.insertAdjacentHTML('afterbegin', '<div class="loading" id="memberImportLoading">导入材料包中...</div>');

  try {
    const resp = await fetch('/api/materials/archive/import', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    await renderMemberDetail(_selectedMemberId);
  } catch (e) {
    showKanbanError('材料包导入失败: ' + e.message);
  } finally {
    document.getElementById('memberImportLoading')?.remove();
    event.target.value = '';
  }
}

async function runMemberMaterialCheck(memberId, batchId) {
  try {
    const resp = await fetch('/api/members/' + memberId + '/materials/check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(batchId ? {batch_id: batchId} : {}),
    });
    const data = await resp.json();
    if (data.error) {
      showKanbanError(data.error);
      return;
    }
    await renderMemberDetail(memberId);
  } catch (e) {
    showKanbanError('整套核查失败: ' + e.message);
  }
}

// inside renderMemberDetail(memberId)
const latestBatch = m.latest_import_batch || {};
const latestCheck = m.latest_material_check || {};
html += `<div class="detail-actions">
  <button class="btn btn-secondary" onclick="openMemberArchivePicker(${m.id})">📦 导入材料包</button>
  <button class="btn btn-primary" onclick="runMemberMaterialCheck(${m.id}, ${latestBatch.id || 'null'})">🔍 整套核查</button>
</div>`;

html += `<div class="detail-section">
  <div class="detail-section-title">📦 最近导入</div>
  <div>${latestBatch.archive_name || '暂无导入记录'}</div>
  <div>${latestBatch.total_files || 0} 文件 · ${latestBatch.recognized_files || 0} 已识别 · ${latestBatch.needs_review_files || 0} 待复核</div>
</div>`;

html += `<div class="detail-section">
  <div class="detail-section-title">🧾 最近整套核查</div>
  <div>错误 ${latestCheck.summary?.error_count || 0} · 警告 ${latestCheck.summary?.warning_count || 0} · 待确认 ${latestCheck.summary?.review_count || 0}</div>
</div>`;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/web/static/index.html partymate/web/static/app.js tests/test_static_material_workbench_assets.py
git commit -m "feat: add member material workbench ui"
```

## Task 8: Run End-To-End Verification And Final Cleanup

**Files:**
- Modify: `partymate/db/setup.py`
- Modify: `tests/test_web_material_workbench_api.py`
- Modify: `tests/test_material_import_service.py`
- Modify: `tests/test_material_check_service.py`

- [ ] **Step 1: Add final regression coverage for the complete flow**

```python
# tests/test_web_material_workbench_api.py
@patch("partymate.services.material_import_service.parse_file")
def test_import_then_check_flow_returns_structured_summary(self, mock_parse):
    temp_dir, repo = make_temp_repo()
    try:
        member = repo.add_member(name="张三", apply_date="2026-03-01")
        mock_parse.return_value = {
            "filename": "入党申请书.docx",
            "type": "docx",
            "text": "敬爱的党组织 张三 2026年3月1日",
            "pages": 1,
            "preview": "敬爱的党组织",
            "error": None,
        }
        app = create_app(repository=repo, data_root=Path(temp_dir.name))
        client = TestClient(app)
        zip_bytes = make_zip_bytes({"入党申请书.docx": b"fake-docx"})

        import_resp = client.post(
            "/api/materials/archive/import",
            files={"file": ("materials.zip", zip_bytes, "application/zip")},
            data={"member_id": str(member["id"])},
        )
        check_resp = client.post(f"/api/members/{member['id']}/materials/check", json={})

        self.assertEqual(import_resp.status_code, 200)
        self.assertEqual(check_resp.status_code, 200)
        self.assertIn("summary", check_resp.json())
        self.assertIn("errors", check_resp.json())
        self.assertIn("warnings", check_resp.json())
        self.assertIn("needs_review", check_resp.json())
    finally:
        repo.close()
        temp_dir.cleanup()
```

- [ ] **Step 2: Run the full automated suite**

Run: `uv run python -m unittest discover -s tests -v`

Expected: `OK` for repository, service, API, and static-asset smoke tests.

- [ ] **Step 3: Align sample-data output with the new dashboard contract**

```python
# partymate/db/setup.py
dash = MemberViewService(repo).build_dashboard()
print(f"\nDashboard summary:")
print(f"  Total members:  {dash['total']}")
print(f"  Stage counts:   {{k: v['count'] for k, v in dash['stages'].items()}}")
```

- [ ] **Step 4: Perform manual browser verification**

Run:

```bash
uv run python -m partymate.db.setup
uv run python -m partymate.web.server
```

Manual checklist:

- open `http://localhost:8567`
- switch to `发展看板`
- create or select a member
- upload a `.zip` material package from the member detail area
- confirm latest import panel updates
- click `整套核查`
- confirm latest check panel shows counts
- confirm no existing `材料检查 / 会议整理 / 内容生成 / AI 对话` tab is broken

- [ ] **Step 5: Commit**

```bash
git add partymate/db/setup.py tests/test_web_material_workbench_api.py tests/test_material_import_service.py tests/test_material_check_service.py
git commit -m "test: verify member material workbench end to end"
```
