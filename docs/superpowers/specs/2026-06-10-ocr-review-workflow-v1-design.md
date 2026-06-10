# OCR Review Workflow V1 Design

## 1. Purpose

This document defines the next implementation increment after `Member Material Workbench V1`.

The previous increment established a stable member-centered material ingestion flow:

- zip archive import is bound to a specific member,
- supported files are extracted and parsed,
- imported files are classified,
- package-level deterministic checks run against a member,
- and the member detail UI can surface latest import/check results.

That work intentionally stopped at the point where low-confidence OCR output was only marked as `needs_review`.

This increment turns that routing signal into a usable review loop.

## 2. Why This Is The Next Increment

`DEVPLAN.md` explicitly identifies `OCR 人工复核闭环` as the next high-value capability after archive import and member-level package checks.

The current codebase already has the prerequisites needed for an OCR review loop:

- image OCR via `easyocr`,
- persisted imported file rows in `material_files`,
- `needs_review` routing on low-confidence or near-empty parsed text,
- member detail pages that can surface additional task panels,
- and deterministic material checks that can later consume confirmed text.

What is still missing is the actual human-in-the-loop step:

- no OCR review task entity,
- no API to retrieve an OCR draft for review,
- no API to confirm corrected text,
- no way for checks to prefer human-confirmed OCR,
- and no member detail entry point for unresolved OCR review work.

## 3. Product Goal For V1

Deliver the first OCR review loop that allows a user to:

1. see which imported files need OCR review,
2. open one OCR review task from a member detail view,
3. inspect the raw OCR draft plus low-confidence spans,
4. edit the OCR result as a whole document,
5. confirm the corrected text into controlled storage,
6. and have later package checks prefer the confirmed text over the raw OCR output.

## 4. Scope

### 4.1 In Scope

- create OCR review tasks for imported files that require OCR review,
- persist OCR raw span data and confidence information,
- expose OCR review task read/confirm APIs,
- store human-confirmed OCR text,
- let material/package checks consume confirmed OCR text first,
- surface unresolved OCR review tasks in member detail,
- add automated repository, service, API, and static asset tests.

### 4.2 Out Of Scope For V1

- per-span editing in the UI,
- polygon/image-region visualization,
- manual re-running OCR with alternate engines,
- field-level extraction confirmation workflows,
- bulk review queues across all members,
- review analytics dashboards,
- agent-triggered OCR adjudication,
- independent non-member OCR uploads.

This increment is intentionally a `whole-file confirmation` workflow, not a fine-grained annotation tool.

## 5. Review Granularity Decision

V1 uses `整文件确认`, not span-by-span or field-only review.

Reasoning:

- it closes the OCR loop with the least new UI and API surface,
- it fits the current raw-text-first static frontend,
- it integrates directly with the existing `material_files` records,
- and it gives later package checks one stable authoritative text source.

The system still stores OCR spans and confidence, but the user edits one full text field and confirms it once.

## 6. Relationship To The Full Product

This increment is not the final OCR system.

It creates the durable substrate required for later improvements:

- span-level review UI,
- key-field extraction confirmation,
- stronger confidence heuristics,
- audit trails tied to agent runs,
- and member memory writes based on OCR review conclusions.

The core V1 output is a stable distinction between:

- `raw OCR draft`
- `human-confirmed OCR text`

That distinction is what the later agent and material-check features need.

## 7. Existing Problems In Current Code

Current OCR handling stops too early:

- `partymate/tools/file_parser.py` extracts OCR text but drops the span/confidence structure,
- `MaterialImportService` marks some files as `needs_review` but does not create a reviewable task,
- package checks only see the parsed text snapshot and cannot distinguish raw OCR from confirmed OCR,
- and the frontend shows `待复核` counts but gives no workflow for resolving them.

V1 must solve these gaps without replacing the current archive import and member detail architecture.

## 8. Architecture

V1 keeps the current local Python monolith and adds one new focused service plus targeted repository and API extensions.

### 8.1 Parser Layer

Extend image OCR parsing so the parser can return:

- full OCR text,
- OCR spans,
- and span confidence metadata.

### 8.2 Repository Layer

Persist OCR review tasks and expose task lookup/update helpers.

### 8.3 Service Layer

Add an `OCRReviewService` responsible for:

- creating OCR review tasks from imported files,
- reading review context,
- confirming reviewed text,
- and resolving which text should be used by downstream checks.

### 8.4 API / Frontend Layer

Expose task read/confirm endpoints and extend member detail DTOs plus the existing static frontend so unresolved OCR review work is actionable.

## 9. Storage Design

V1 adds one new table and extends one existing table.

### 9.1 New Table: `ocr_tasks`

Purpose: one row per member-bound OCR review task.

Fields:

- `id INTEGER PRIMARY KEY`
- `member_id INTEGER NOT NULL`
- `batch_id INTEGER NOT NULL`
- `material_file_id INTEGER NOT NULL UNIQUE`
- `status TEXT NOT NULL`
- `raw_segments_json TEXT NOT NULL`
- `confidence_summary_json TEXT NOT NULL`
- `confirmed_text_path TEXT DEFAULT ''`
- `review_notes TEXT DEFAULT ''`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Status values used in V1:

- `review_required`
- `confirmed`

Reserved existing enum values such as `pending` and `dismissed` may stay in the codebase for later increments, but V1 should only produce the two states above.

### 9.2 Existing Table Extension: `material_files`

Add:

- `ocr_task_id INTEGER DEFAULT NULL REFERENCES ocr_tasks(id)`
- `review_status TEXT DEFAULT ''`

Rules:

- `ocr_task_id` is set only when the file has a bound OCR review task,
- `review_status` mirrors the actionable state needed by UI and checks:
  - `review_required`
  - `confirmed`
  - ``

V1 does not replace `full_text_path`; raw parsed text continues to live there.

## 10. Filesystem Layout

Confirmed OCR text should live alongside the import batch under controlled data storage.

Layout:

```text
data/
  material_imports/
    member_{member_id}/
      batch_{batch_id}/
        source/
        extracted/
        parsed/
        ocr_reviews/
          task_{task_id}.txt
```

Rules:

- raw parsed OCR text remains at the existing `parsed/file_{material_file_id}.txt`,
- confirmed OCR text is stored separately,
- confirmation never overwrites the raw OCR draft,
- later checks choose the authoritative source through service logic rather than by mutating the original parsed file.

## 11. Parser Output Changes

V1 extends the parser contract for image OCR.

For image files, parser results should additionally include:

```json
{
  "ocr_segments": [
    {
      "text": "敬爱的党组织",
      "confidence": 0.92,
      "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]]
    }
  ]
}
```

Contract rules:

- non-image files return `ocr_segments: []`,
- image OCR still returns the current flattened `text`,
- the flattened text should be derived from the retained OCR segments,
- confidence values are preserved as returned by the OCR engine,
- `bbox` is stored for future UI evolution even though V1 does not render spatial overlays.

## 12. OCR Review Task Creation Rules

An OCR review task is created automatically during archive import when:

1. the imported file is an image OCR parse, and
2. the imported file is marked `needs_review=1`.

V1 does not create OCR review tasks for normal text-native PDF/Word files.

Task creation behavior:

- store the OCR spans in `raw_segments_json`,
- compute a simple confidence summary in `confidence_summary_json`,
- link the task back to `material_files.ocr_task_id`,
- set `material_files.review_status = 'review_required'`.

## 13. Confidence Summary Rules

V1 does not attempt advanced confidence modeling.

It computes a simple summary from OCR spans:

- `segment_count`
- `low_confidence_count`
- `average_confidence`
- `min_confidence`
- `max_confidence`

Low confidence in V1 means `confidence < 0.60`.

This threshold is not treated as semantic truth. It is a triage aid for the human reviewer.

## 14. Authoritative Text Resolution

The system needs a single rule for which text downstream features should consume.

Resolution order:

1. if an OCR task exists and is `confirmed`, use `confirmed_text_path`,
2. otherwise use the raw parsed text from `material_files.full_text_path`,
3. if neither exists, treat the file as unresolved review input.

This rule must be implemented in one reusable service helper rather than duplicated in package-check logic.

## 15. API Design

V1 adds the OCR endpoints already proposed in `DEVPLAN.md`.

### 15.1 `GET /api/ocr/tasks/{task_id}`

Purpose: retrieve the review context for one OCR task.

Response shape:

```json
{
  "task": {
    "id": 7,
    "status": "review_required",
    "member_id": 1,
    "batch_id": 3,
    "material_file_id": 21,
    "review_notes": "",
    "created_at": "",
    "updated_at": ""
  },
  "file": {
    "id": 21,
    "original_name": "申请书扫描件.jpg",
    "stored_path": "..."
  },
  "raw_text": "...",
  "confirmed_text": "",
  "confidence_summary": {
    "segment_count": 14,
    "low_confidence_count": 3,
    "average_confidence": 0.77
  },
  "low_confidence_segments": []
}
```

Rules:

- `raw_text` is loaded from the raw parsed text file,
- `confirmed_text` is loaded from the confirmed text file when present,
- `low_confidence_segments` is derived from stored raw OCR spans.

### 15.2 `POST /api/ocr/confirm`

Purpose: confirm one OCR review task with edited whole-file text.

Request body:

```json
{
  "task_id": 7,
  "confirmed_text": "人工修订后的全文",
  "review_notes": "修正了姓名和日期"
}
```

Behavior:

- validate task exists,
- validate `confirmed_text` is non-empty,
- persist the confirmed text to controlled storage,
- set task status to `confirmed`,
- update `material_files.review_status` to `confirmed`,
- return the updated task summary.

### 15.3 `GET /api/members/{id}`

Extend the member DTO with:

- `pending_ocr_tasks`
- `pending_ocr_task_count`

Each pending OCR task entry should include:

- `task_id`
- `material_file_id`
- `original_name`
- `review_status`
- `created_at`
- `confidence_summary`

### 15.4 Existing Check Endpoint Integration

`POST /api/members/{id}/materials/check` keeps the same route but changes internal source selection so confirmed OCR text is preferred automatically.

No new client contract is required for this part.

## 16. Frontend Design

V1 stays inside the existing static member detail UI.

### 16.1 Member Detail Additions

Add a new OCR review section showing:

- pending OCR review count,
- a list of review-required files,
- an `开始复核` button per task.

### 16.2 Review Panel

When a task is opened:

- show file name and confidence summary,
- show the raw OCR draft in a read-only panel,
- show an editable textarea seeded with the raw OCR draft,
- allow optional review notes,
- and provide a `确认入库` button.

### 16.3 V1 UX Boundaries

V1 does not need:

- image thumbnails,
- bbox overlays,
- keyboard shortcuts,
- bulk navigation,
- or diff visualization.

The user experience goal is not elegance yet. The goal is a reliable human-confirmation path.

## 17. Service Boundaries

Add:

- `partymate/services/ocr_review_service.py`

Responsibilities:

- create OCR review tasks from imported image files,
- build review-task DTOs,
- persist confirmed OCR text,
- expose authoritative text lookup for downstream checks.

Current services should interact with it as follows:

- `MaterialImportService`: may create OCR tasks after imported file persistence,
- `MaterialCheckService`: uses OCRReviewService to resolve authoritative text before checking file content,
- `MemberViewService`: includes pending OCR task summaries in member detail DTOs.

## 18. Integration With Current Import Flow

Material import changes should be minimal and additive.

During import:

1. parse file,
2. persist `material_files` row,
3. write raw parsed text file,
4. decide `needs_review`,
5. if image OCR and `needs_review`, create OCR task,
6. link the task to the imported file.

The existing batch summary counts remain valid.

`needs_review_files` should still count unresolved OCR items until they are confirmed.

## 19. Integration With Current Package Checks

Package checks should not parse OCR files again.

Instead, they should:

1. ask OCRReviewService for authoritative file text,
2. use confirmed OCR text when present,
3. otherwise use raw parsed text,
4. continue reporting unresolved OCR review items as review issues.

This keeps OCR review and package checks loosely coupled.

## 20. Error Handling Rules

V1 must handle:

- task not found,
- confirmed text missing,
- confirmed text file write failure,
- raw parsed text missing unexpectedly,
- task/file/member mismatch,
- and duplicate confirmation attempts.

Expected behavior:

- return structured API errors,
- do not silently overwrite unrelated files,
- keep task status unchanged on failed confirmation writes,
- and allow re-confirming a task by replacing the prior confirmed text only for the same task.

## 21. Security And Safety Rules

V1 must enforce:

- OCR review tasks are only created from already-imported controlled files,
- confirmed text is written only under controlled batch storage,
- no arbitrary filesystem paths from the client,
- no user-specified file references in OCR confirm requests,
- and no shell invocation or external model dependency during review confirmation.

## 22. Testing Strategy

### 22.1 Repository Tests

Test:

- `ocr_tasks` table creation,
- OCR task creation/retrieval/update,
- `material_files` OCR link fields,
- member-level OCR task listing.

### 22.2 Service Tests

Test:

- OCR task creation from image files needing review,
- confidence summary generation,
- confirmed text persistence,
- authoritative text resolution preferring confirmed text.

### 22.3 API Tests

Test:

- get OCR task success,
- get OCR task 404,
- confirm OCR task success,
- confirm OCR task validation failure on empty text,
- member detail DTO includes pending OCR tasks,
- package check uses confirmed OCR text when available.

### 22.4 Static Asset Smoke Tests

Test that the static frontend includes:

- OCR review section markers,
- review open handler,
- confirm submission handler,
- OCR API endpoint wiring.

## 23. Migration Strategy

Continue using the current lightweight schema evolution approach:

- extend `Repository.create_tables()` in place,
- avoid a migration framework,
- and keep existing data usable.

This is acceptable for the current local-single-user monolith stage.

## 24. Rollout Sequence

The implementation order should be:

1. add repository tests and OCR task schema support,
2. extend file parser OCR output to preserve spans and confidence,
3. add OCR review service and import integration,
4. add OCR task APIs,
5. extend member detail DTOs and static frontend review UI,
6. update package checks to prefer confirmed OCR text,
7. run automated tests and one real end-to-end runtime smoke check.

## 25. Risks And Mitigations

### 25.1 OCR Draft Quality Is Very Poor

Risk:

- some scanned materials may produce unusable drafts.

Mitigation:

- V1 still lets the reviewer replace the whole text manually instead of depending on small edits only.

### 25.2 Review Tasks Drift From Material Files

Risk:

- OCR task state and material file state may become inconsistent.

Mitigation:

- keep one task per material file,
- mirror actionable status on the `material_files` row,
- and centralize authoritative text resolution in one service.

### 25.3 Scope Expansion Into Annotation Tooling

Risk:

- adding overlays, per-span editing, or advanced image previews will slow the increment down.

Mitigation:

- keep V1 strictly whole-file confirmation.

## 26. Success Criteria

V1 is successful when all of the following are true:

- imported image OCR files that require review create OCR review tasks,
- OCR tasks persist raw OCR span/confidence data,
- a user can retrieve one OCR task through API,
- a user can confirm corrected whole-file OCR text,
- confirmed text is stored separately from raw OCR text,
- member detail surfaces unresolved OCR review tasks,
- package checks prefer confirmed OCR text automatically,
- and automated tests cover repository, service, API, and static asset behavior.

## 27. Next Increment After V1

If this increment is stable, the next natural OCR step is `Segmented OCR Review V2` or `Key Field Confirmation V2`.

That later increment can build on the V1 substrate because V1 will already provide:

- persisted OCR task records,
- raw OCR segments with confidence,
- human-confirmed canonical text,
- and member-bound unresolved review queues.
