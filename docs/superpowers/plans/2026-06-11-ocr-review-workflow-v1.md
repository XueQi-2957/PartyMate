# OCR Review Workflow V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first OCR human-review loop for imported member materials by persisting OCR review tasks, exposing review/confirm APIs, surfacing pending OCR work in member detail, and letting package checks prefer confirmed OCR text.

**Architecture:** Keep the current Python local monolith. Extend the SQLite repository with OCR task persistence and lightweight column migrations, enrich the parser/import flow with OCR segment metadata, add a focused `OCRReviewService`, then wire the Starlette app and static member-detail UI to the new OCR review workflow.

**Tech Stack:** Python 3.11, sqlite3, Starlette, unittest, pathlib, easyocr, existing static HTML/CSS/JS frontend

---

## File Map

### New Files

- `partymate/services/ocr_review_service.py`
  - OCR task creation, task detail shaping, confirmed-text persistence, authoritative text resolution
- `tests/test_repository_ocr_review.py`
  - repository schema and OCR task CRUD coverage
- `tests/test_ocr_review_service.py`
  - OCR review service behavior and confirmed-text resolution tests

### Modified Files

- `partymate/db/repository.py`
  - OCR task table, `material_files` column migration, OCR task query/update helpers
- `partymate/tools/file_parser.py`
  - preserve OCR segment/confidence output while keeping the current parse contract
- `partymate/services/material_import_service.py`
  - create OCR review tasks during import for unresolved image OCR files
- `partymate/services/material_check_service.py`
  - resolve authoritative text through OCR review service
- `partymate/services/member_view_service.py`
  - include pending OCR task summaries in member detail DTOs
- `partymate/services/__init__.py`
  - export `OCRReviewService`
- `partymate/web/server.py`
  - add OCR task read/confirm APIs and inject the OCR review service
- `partymate/web/static/index.html`
  - add OCR review panel markup hooks
- `partymate/web/static/app.js`
  - add OCR task open/confirm flows in member detail
- `tests/test_material_import_service.py`
  - assert OCR task creation and linked file state
- `tests/test_material_check_service.py`
  - assert confirmed OCR text is preferred during checks
- `tests/test_member_view_service.py`
  - assert member detail exposes pending OCR tasks
- `tests/test_web_material_workbench_api.py`
  - add OCR task API contract coverage
- `tests/test_static_material_workbench_assets.py`
  - assert frontend OCR review wiring exists

## Task 1: Add Repository OCR Review Persistence

**Files:**
- Create: `tests/test_repository_ocr_review.py`
- Modify: `partymate/db/repository.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import unittest

from tests.support import make_temp_repo


class RepositoryOCRReviewTests(unittest.TestCase):
    def test_create_tables_adds_ocr_task_table_and_material_file_columns(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            names = {
                row["name"]
                for row in repo.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("ocr_tasks", names)

            columns = {
                row["name"]
                for row in repo.conn.execute("PRAGMA table_info(material_files)").fetchall()
            }
            self.assertIn("ocr_task_id", columns)
            self.assertIn("review_status", columns)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_repository_persists_and_lists_member_ocr_tasks(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed_with_review",
            )
            material_file = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="申请书扫描件.jpg",
                stored_path="scan.jpg",
                extension=".jpg",
                parser_type="image",
                parse_status="parsed",
            )
            task = repo.create_ocr_task(
                member_id=member["id"],
                batch_id=batch["id"],
                material_file_id=material_file["id"],
                status="review_required",
                raw_segments_json='[{"text":"敬爱的党组织","confidence":0.42}]',
                confidence_summary_json='{"segment_count":1,"low_confidence_count":1}',
            )
            repo.update_material_file(
                material_file["id"],
                ocr_task_id=task["id"],
                review_status="review_required",
            )

            pending = repo.list_member_ocr_tasks(member["id"], status="review_required")

            self.assertEqual(pending[0]["material_file_id"], material_file["id"])
            self.assertEqual(pending[0]["status"], "review_required")
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_repository_ocr_review -v`

Expected: `FAIL` because the repository does not yet create `ocr_tasks`, does not add `material_files.ocr_task_id/review_status`, and does not expose OCR task helpers.

- [ ] **Step 3: Write the minimal implementation**

Add to `Repository.create_tables()`:

- `CREATE TABLE IF NOT EXISTS ocr_tasks (...)`
- lightweight `ALTER TABLE` checks so existing `material_files` tables gain:
  - `ocr_task_id INTEGER DEFAULT NULL`
  - `review_status TEXT DEFAULT ''`

Add helpers:

- `create_ocr_task(...)`
- `get_ocr_task(task_id)`
- `update_ocr_task(task_id, **kwargs)`
- `list_member_ocr_tasks(member_id, status=None)`
- `get_ocr_task_by_material_file(material_file_id)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_repository_ocr_review -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add tests/test_repository_ocr_review.py partymate/db/repository.py
git commit -m "test: add repository coverage for ocr review workflow"
```

## Task 2: Preserve OCR Segment Metadata And Create Tasks During Import

**Files:**
- Modify: `partymate/tools/file_parser.py`
- Modify: `partymate/services/material_import_service.py`
- Modify: `tests/test_material_import_service.py`

- [ ] **Step 1: Write the failing test**

Extend `tests/test_material_import_service.py` with a new case that patches `parse_file()` to return:

```python
{
    "filename": "申请书扫描件.jpg",
    "type": "image",
    "text": "敬爱的党组只",
    "pages": 1,
    "preview": "敬爱的党组只",
    "ocr_segments": [
        {"text": "敬爱的党组只", "confidence": 0.42, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}
    ],
    "error": None,
}
```

Then assert:

- import result file has `review_status == "review_required"`
- imported file has non-empty `ocr_task_id`
- linked OCR task exists and stores the raw segment/confidence payload

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_material_import_service -v`

Expected: `FAIL` because parser output does not preserve OCR segments and import flow does not create OCR review tasks.

- [ ] **Step 3: Write the minimal implementation**

In `partymate/tools/file_parser.py`:

- return `ocr_segments: []` for non-image parsing
- for image OCR, capture retained `(bbox, text, confidence)` into `ocr_segments`
- keep the current flattened `text`, `preview`, and `pages`

In `partymate/services/material_import_service.py`:

- after updating an imported file, if `parser_type == "image"` and `needs_review` is true:
  - create an OCR task
  - attach `ocr_task_id`
  - set `review_status = "review_required"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_material_import_service -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/tools/file_parser.py partymate/services/material_import_service.py tests/test_material_import_service.py
git commit -m "feat: create ocr review tasks during material import"
```

## Task 3: Add OCR Review Service And Confirmed Text Resolution

**Files:**
- Create: `tests/test_ocr_review_service.py`
- Create: `partymate/services/ocr_review_service.py`
- Modify: `partymate/services/__init__.py`
- Modify: `partymate/services/material_check_service.py`
- Modify: `tests/test_material_check_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ocr_review_service.py` with coverage for:

- building a task detail DTO that loads raw text and low-confidence segments
- confirming a task, writing `ocr_reviews/task_{id}.txt`, and updating task/file state
- resolving authoritative text to the confirmed text when present

Extend `tests/test_material_check_service.py` with a case where:

- raw OCR text omits the member name
- confirmed OCR text includes the member name
- `MaterialCheckService` no longer raises `identity_conflict`

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_ocr_review_service -v
uv run python -m unittest tests.test_material_check_service -v
```

Expected: `ERROR` / `FAIL` because `OCRReviewService` does not exist and package checks still read only `full_text_path`.

- [ ] **Step 3: Write the minimal implementation**

Implement `OCRReviewService` with:

- `build_task_detail(task_id)`
- `confirm_task(task_id, confirmed_text, review_notes="")`
- `resolve_file_text(material_file)`
- helper methods for confidence summary parsing and low-confidence segment filtering

Update `MaterialCheckService`:

- initialize and use `OCRReviewService`
- replace direct `Path(full_text_path).read_text(...)` calls with authoritative text resolution
- treat `review_status == "review_required"` as unresolved review input

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run python -m unittest tests.test_ocr_review_service -v
uv run python -m unittest tests.test_material_check_service -v
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/ocr_review_service.py partymate/services/__init__.py partymate/services/material_check_service.py tests/test_ocr_review_service.py tests/test_material_check_service.py
git commit -m "feat: add ocr review service and confirmed text resolution"
```

## Task 4: Expose OCR Review APIs And Member DTOs

**Files:**
- Modify: `partymate/services/member_view_service.py`
- Modify: `partymate/web/server.py`
- Modify: `tests/test_member_view_service.py`
- Modify: `tests/test_web_material_workbench_api.py`

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_member_view_service.py` to assert:

- `pending_ocr_tasks`
- `pending_ocr_task_count`

Extend `tests/test_web_material_workbench_api.py` to assert:

- `GET /api/ocr/tasks/{id}` returns task/file/raw_text/confidence summary
- `POST /api/ocr/confirm` confirms the task and returns status `confirmed`
- `GET /api/members/{id}` includes pending OCR task summaries

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_member_view_service -v
uv run python -m unittest tests.test_web_material_workbench_api -v
```

Expected: `FAIL` because member DTOs and web routes do not yet include OCR review data.

- [ ] **Step 3: Write the minimal implementation**

In `MemberViewService`:

- add pending OCR task summaries to `build_member_detail()`

In `partymate/web/server.py`:

- instantiate `OCRReviewService`
- add:
  - `GET /api/ocr/tasks/{task_id}`
  - `POST /api/ocr/confirm`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run python -m unittest tests.test_member_view_service -v
uv run python -m unittest tests.test_web_material_workbench_api -v
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/services/member_view_service.py partymate/web/server.py tests/test_member_view_service.py tests/test_web_material_workbench_api.py
git commit -m "feat: expose ocr review workflow api"
```

## Task 5: Wire The Static Frontend To OCR Review

**Files:**
- Modify: `partymate/web/static/index.html`
- Modify: `partymate/web/static/app.js`
- Modify: `tests/test_static_material_workbench_assets.py`

- [ ] **Step 1: Write the failing smoke test**

Extend `tests/test_static_material_workbench_assets.py` to assert the frontend includes:

- OCR review section markup marker
- `openOCRReviewTask(`
- `confirmOCRReviewTask(`
- `/api/ocr/tasks/`
- `/api/ocr/confirm`

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `FAIL` because the current frontend does not include OCR review handlers or API wiring.

- [ ] **Step 3: Write the minimal implementation**

In `index.html`:

- add OCR review detail hooks inside the member detail area if needed

In `app.js`:

- render pending OCR review tasks in member detail
- load OCR task detail on `开始复核`
- render raw OCR text + editable confirmed text + review notes
- submit `POST /api/ocr/confirm`
- refresh member detail after confirmation

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add partymate/web/static/index.html partymate/web/static/app.js tests/test_static_material_workbench_assets.py
git commit -m "feat: add ocr review workflow ui"
```

## Task 6: Full Verification

**Files:**
- Modify: `tests/test_web_material_workbench_api.py`

- [ ] **Step 1: Add end-to-end OCR review flow coverage**

Add one API-level test that:

1. imports a member archive with a low-confidence OCR image
2. fetches the created OCR task
3. confirms corrected text
4. runs package check
5. verifies the structured result no longer treats the OCR file as unresolved review input

- [ ] **Step 2: Run the full automated suite**

Run: `uv run python -m unittest discover -s tests -v`

Expected: `OK`

- [ ] **Step 3: Run a runtime smoke check**

Run:

```bash
uv run python -m partymate.db.setup
uv run python -m partymate.web.server
```

Checklist:

- open `http://localhost:8567`
- enter `发展看板`
- import a zip package with an OCR image
- confirm an OCR task appears
- open the task, edit/confirm text
- rerun package check
- verify the task leaves the pending OCR queue

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_material_workbench_api.py
git commit -m "test: verify ocr review workflow end to end"
```
