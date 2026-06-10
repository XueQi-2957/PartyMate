# Member Material Workbench V1 Design

## 1. Purpose

This document defines the first implementation increment on the path to the full PartyMate local agent described in `DEVPLAN.md`.

The end goal is not a collection of disconnected tools. The end goal is a `local-first, single-user, stateful Party affairs agent workbench` that can:

- manage member-specific context and materials,
- ingest document packages,
- run deterministic and AI-assisted checks,
- support OCR plus human review,
- write results back into ledger and reminders,
- and expose all of that through controlled agent tools.

This first increment builds the foundation for that system by delivering a `Member Material Workbench V1`.

## 2. Why This Is The First Increment

The current repository already has:

- single-document compliance checking,
- file parsing and OCR,
- a member repository backed by SQLite,
- a dashboard-like web UI,
- and a lightweight tool-calling agent runtime.

However, the current system still breaks at the exact place where a useful agent needs continuity:

- document handling is still mostly one-file-at-a-time,
- material checks are not member-package-aware,
- dashboard API shapes do not match the frontend's expectations,
- and there is no stable material-ingestion surface for later OCR review, memory, or run tracing.

Because of that, the first increment should not be "add another tool". It should create the first durable `member-centered working surface` that later agent capabilities can build on.

## 3. Product Goal For V1

Deliver a member-centered material workbench that can:

1. bind uploaded material archives to a specific member,
2. unpack and index the files safely,
3. parse supported files using existing parsers,
4. classify files into likely material types,
5. run package-level deterministic checks,
6. show results inside the existing member detail workflow,
7. and expose stable backend data shapes that future OCR-review, member-memory, and agent-task features can reuse.

## 4. Relationship To The Final Full Agent

V1 is not the final agent. It is the first durable substrate for the final agent.

After V1, the next large capabilities can be added on top without replacing the core material flow:

- `OCR review loop`: add low-confidence segment review on imported files,
- `member memory`: persist long-lived conclusions and preferences per member,
- `meeting closed loop`: push parsed actions into reminders and member history,
- `agent run trace`: record tool invocations and outputs for auditability,
- `knowledge management`: attach citations and party-rule basis to remediation advice,
- `stateful agent tools`: let the model call material import, context load, package check, and report export tools.

V1 therefore must prioritize stable storage, stable API contracts, and member-level context boundaries over flashy but isolated UI work.

## 5. Scope

### 5.1 In Scope

- unify the member/dashboard API contract used by the current web UI,
- import zip material packages for a specific member,
- extract supported files into a controlled batch directory,
- parse files with the existing file parser,
- identify likely material types from file name plus extracted text,
- persist imported file metadata and parse status,
- run package-level deterministic material checks for a member,
- store package check results,
- show import batches and latest package-check results in the member detail view,
- add automated tests for repository, service, and API behavior.

### 5.2 Out Of Scope For V1

- manual OCR correction UI,
- vector retrieval or embedding-based material recall,
- member memory storage,
- full agent run audit trail,
- background task queue,
- multi-user support,
- Vue/FastAPI migration,
- model-based fuzzy adjudication in package checks,
- direct archive finalization into long-term member archive folders.

Those are intentionally deferred so V1 can create a reliable base instead of an oversized partial implementation.

## 6. Existing Problems In Current Code

The current codebase already contains a dashboard and member detail workflow, but the backend and frontend are not aligned:

- backend member detail uses `events`, frontend reads `timeline`,
- backend material rows use `material_name` and `is_submitted`, frontend reads `name` and `submitted`,
- backend dashboard returns `total_members` and `by_stage`, frontend expects `total` and `stages`,
- reminders currently expose raw repository rows while the frontend expects typed reminder categories.

V1 must fix this mismatch through explicit response-shaping rather than by letting the frontend keep guessing raw database column names.

## 7. Architecture

V1 keeps the current `Python local monolith` architecture and adds three focused layers:

### 7.1 Repository Layer

Extend SQLite storage for imported material batches, individual imported files, and package-check results.

### 7.2 Service Layer

Add dedicated services for:

- archive import,
- material identification,
- package-level consistency checking,
- and API response shaping.

The service layer is where future OCR review and agent tools will attach.

### 7.3 Web API Layer

Expose stable endpoints for:

- importing an archive,
- checking a member's material package,
- retrieving dashboard/member detail data in frontend-ready form.

The API layer should be thin. It validates inputs, calls services, and returns shaped JSON.

## 8. Storage Design

V1 adds three new tables and keeps existing tables intact.

### 8.1 `material_import_batches`

Purpose: one row per archive import attempt for one member.

Fields:

- `id INTEGER PRIMARY KEY`
- `member_id INTEGER NOT NULL`
- `archive_name TEXT NOT NULL`
- `archive_path TEXT NOT NULL`
- `extract_dir TEXT NOT NULL`
- `status TEXT NOT NULL`
- `total_files INTEGER NOT NULL DEFAULT 0`
- `recognized_files INTEGER NOT NULL DEFAULT 0`
- `needs_review_files INTEGER NOT NULL DEFAULT 0`
- `failed_files INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT NOT NULL`

Status values:

- `processing`
- `completed`
- `completed_with_review`
- `failed`

### 8.2 `material_files`

Purpose: one row per extracted supported file inside an import batch.

Fields:

- `id INTEGER PRIMARY KEY`
- `batch_id INTEGER NOT NULL`
- `member_id INTEGER NOT NULL`
- `original_name TEXT NOT NULL`
- `stored_path TEXT NOT NULL`
- `extension TEXT NOT NULL`
- `parser_type TEXT NOT NULL`
- `parse_status TEXT NOT NULL`
- `material_type TEXT DEFAULT ''`
- `material_stage TEXT DEFAULT ''`
- `recognition_source TEXT DEFAULT ''`
- `text_excerpt TEXT DEFAULT ''`
- `full_text_path TEXT DEFAULT ''`
- `page_count INTEGER NOT NULL DEFAULT 0`
- `needs_review INTEGER NOT NULL DEFAULT 0`
- `error_message TEXT DEFAULT ''`
- `created_at TEXT NOT NULL`

`full_text_path` stores extracted text as a file on disk rather than bloating SQLite rows.

### 8.3 `member_material_checks`

Purpose: one row per package-level check execution.

Fields:

- `id INTEGER PRIMARY KEY`
- `member_id INTEGER NOT NULL`
- `batch_id INTEGER`
- `status TEXT NOT NULL`
- `error_count INTEGER NOT NULL DEFAULT 0`
- `warning_count INTEGER NOT NULL DEFAULT 0`
- `review_count INTEGER NOT NULL DEFAULT 0`
- `summary_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`

`summary_json` stores the structured check result envelope.

## 9. Filesystem Layout

Imported archives and extracted files should live under project data storage, not under temporary upload directories and not under the final archive tree.

Layout:

```text
data/
  material_imports/
    member_{member_id}/
      batch_{batch_id}/
        source/
          original.zip
        extracted/
          ...
        parsed/
          file_{file_id}.txt
```

Rules:

- only supported file types are indexed for downstream parsing,
- unsupported files are skipped but counted in batch summary,
- extracted paths must be normalized and validated to prevent zip-slip path traversal,
- duplicate file names in one archive must be made unique on extraction.

## 10. Supported Inputs

V1 accepts zip archives whose inner files are in the current parser white list:

- `.pdf`
- `.docx`
- `.doc`
- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.tiff`

Other file types are ignored for parsing and reported as skipped.

## 11. Material Identification Strategy

V1 uses deterministic identification, not LLM classification.

Identification order:

1. exact or alias match against known material names using the filename,
2. document-type detection using extracted text,
3. stage inference using existing material mappings,
4. fallback to `unknown` plus `needs_review`.

Recognition sources:

- `filename_exact`
- `filename_alias`
- `content_doc_type`
- `content_keyword`
- `unknown`

This keeps V1 explainable and testable.

## 12. Package-Level Check Rules

V1 package checks are deterministic and member-centered.

### 12.1 Required Material Missing Check

For the member's current stage and earlier stages, compare recognized imported material types against required material lists.

Output:

- `error` when a clearly required item is missing,
- `warning` when the current stage context is incomplete and the requirement is stage-sensitive.

### 12.2 Duplicate Material Check

Detect multiple files mapped to the same material type unless that type explicitly allows multiple instances, such as periodic reports.

### 12.3 Identity Consistency Check

Extract candidate fields from parsed text and compare with member record:

- name
- grade
- major
- student_id

If multiple files disagree with the member profile or with each other, emit:

- `error` for conflicting strong matches,
- `needs_review` for weak or partial evidence.

### 12.4 Date Conflict Check

Extract key dates from recognized documents and compare for impossible combinations, including:

- activist date earlier than apply date,
- candidate date earlier than activist date,
- probationary date earlier than candidate date,
- full-member date earlier than probationary date,
- transfer or correction dates appearing before prerequisite stage dates.

### 12.5 Stage Sequence Reasonableness Check

If imported materials indicate a later stage without prerequisite earlier-stage materials or dates:

- emit `warning` when a later-stage material exists but prerequisite stage evidence is simply missing,
- emit `error` when extracted dates explicitly contradict required stage order.

### 12.6 Ideological Report Count Check

Count recognized ideological report materials for:

- activist phase
- probationary phase

Flag insufficient count based on the stage already reached.

### 12.7 Semiannual Inspection Check

Check whether semiannual cultivation or inspection materials exist where expected for the member's stage progression.

### 12.8 Unknown Or Low-Confidence File Review Check

Any file that cannot be classified or that parses into near-empty text is added to `needs_review`.

For V1, `near-empty text` means either:

- parser succeeded but extracted text is shorter than 30 non-whitespace characters, or
- an image file produced OCR output with no usable retained lines.

This is not yet the OCR correction loop. It is a routing signal for the next increment.

## 13. Result Model

Package check results will be stored and returned in a stable structured envelope:

```json
{
  "summary": {
    "member_id": 12,
    "batch_id": 5,
    "error_count": 2,
    "warning_count": 3,
    "review_count": 4
  },
  "errors": [],
  "warnings": [],
  "needs_review": [],
  "recognized_materials": [],
  "missing_materials": []
}
```

Each issue entry should include:

- `code`
- `severity`
- `title`
- `detail`
- `evidence`
- `suggested_action`

## 14. API Design

### 14.1 `POST /api/materials/archive/import`

Request:

- `multipart/form-data`
- fields:
  - `member_id`
  - `file`

Behavior:

- verify member exists,
- verify uploaded file is `.zip`,
- create batch row,
- save archive,
- extract safely,
- parse supported files,
- classify files,
- store batch summary and file rows,
- return completed batch result.

Response:

```json
{
  "batch": {},
  "files": [],
  "skipped_files": [],
  "failed_files": []
}
```

### 14.2 `POST /api/members/{id}/materials/check`

Request body:

- optional `batch_id`

Behavior:

- select latest batch when `batch_id` absent,
- run deterministic package checks using imported files plus member profile,
- persist result into `member_material_checks`,
- return the structured envelope.

### 14.3 `GET /api/members/{id}`

This endpoint remains but changes shape to a frontend-ready member DTO:

- `timeline`
- `materials`
- `latest_import_batch`
- `recent_import_batches`
- `latest_material_check`

The repository may still use raw column names internally. The API must not expose those raw names directly.

### 14.4 `GET /api/dashboard`

This endpoint returns the shape the current UI actually needs:

```json
{
  "total": 10,
  "stages": {
    "applicant": {"count": 2, "members": []},
    "activist": {"count": 3, "members": []}
  }
}
```

### 14.5 `GET /api/reminders`

Return reminder DTOs with explicit frontend fields rather than raw reminder table rows.

## 15. Web UI Design

V1 keeps the current static frontend and enhances the member detail area.

### 15.1 Member Detail Additions

Add:

- `导入材料包` button
- `整套核查` button
- latest import summary panel
- latest package-check panel

### 15.2 Import Flow

1. user selects a member,
2. user clicks `导入材料包`,
3. user uploads one zip file,
4. UI shows import progress placeholder,
5. UI renders import summary:
   - total files
   - recognized files
   - needs-review files
   - failed files
6. UI enables `整套核查`.

### 15.3 Check Flow

1. user clicks `整套核查`,
2. backend runs package checks for latest batch,
3. UI renders:
   - severe errors
   - warnings
   - items needing manual review
   - missing material list

### 15.4 Dashboard Contract Fix

V1 will use `backend DTO shaping plus minimal frontend cleanup`.

That means:

- backend APIs return stable frontend-ready DTOs,
- frontend renderers are updated to consume those DTOs directly,
- and frontend adapter glue for raw repository rows is not introduced.

## 16. Service Boundaries

V1 should add focused modules instead of expanding `server.py` or `repository.py` into a grab bag.

Recommended modules:

- `partymate/services/material_import_service.py`
- `partymate/services/material_check_service.py`
- `partymate/services/member_view_service.py`

Responsibilities:

- import service: archive persistence, extraction, parsing, classification
- check service: deterministic package-level rules
- member view service: dashboard/member DTO shaping

## 17. Security And Safety Rules

V1 must enforce:

- zip path traversal prevention,
- upload extension validation,
- extraction only under controlled data directories,
- no arbitrary file reads outside stored batch paths,
- no model access during import/check execution,
- no shell execution for archive handling.

## 18. Testing Strategy

V1 must add automated tests. The repository currently has no test suite, so this increment creates one.

### 18.1 Repository Tests

Test:

- new table creation,
- batch insertion and retrieval,
- imported file persistence,
- material check persistence,
- dashboard/member DTO source queries.

### 18.2 Service Tests

Test:

- safe zip extraction,
- duplicate name handling,
- supported/unsupported file filtering,
- deterministic classification,
- missing-material detection,
- duplicate-material detection,
- identity conflict detection,
- date conflict detection.

### 18.3 API Tests

Test:

- archive import success,
- invalid member rejection,
- invalid file type rejection,
- package-check success,
- latest-batch fallback,
- dashboard shape matches frontend expectations,
- member detail shape matches frontend expectations.

### 18.4 UI Verification

At minimum:

- load the workbench in browser,
- import a sample archive for a sample member,
- run package check,
- verify result sections render.

This can be manual for V1 if browser automation is not yet introduced.

## 19. Migration Strategy

The repository currently creates tables in-place on startup. V1 should continue with the same lightweight migration style:

- extend `create_tables()` with the new tables,
- keep existing data intact,
- avoid introducing a full migration framework in this increment.

This is acceptable because the project is still a local monolith and the schema surface is small.

## 20. Rollout Sequence

The implementation sequence for V1 should be:

1. create tests and repository support for new tables,
2. add import service and safe extraction,
3. add material classification and batch summaries,
4. add package-check service,
5. add frontend-ready member/dashboard DTO shaping,
6. expose new API endpoints,
7. wire the member detail UI to import and check flows,
8. run manual end-to-end verification.

## 21. Risks And Mitigations

### 21.1 OCR Noise

Risk:

- scanned documents may parse poorly and produce false mismatches.

Mitigation:

- V1 routes low-confidence or near-empty files into `needs_review` instead of claiming certainty.

### 21.2 Material Name Ambiguity

Risk:

- different institutions may use slightly different names.

Mitigation:

- add alias-based matching and keep unknown files visible instead of silently discarding them.

### 21.3 Frontend Contract Drift

Risk:

- future code may again couple the UI to raw repository rows.

Mitigation:

- keep DTO shaping explicit in service/API layer.

### 21.4 Scope Expansion

Risk:

- OCR review, memory, and agent tracing could be pulled into this increment.

Mitigation:

- keep V1 limited to material import, package check, and API/UI contract stabilization.

## 22. Success Criteria

V1 is successful when all of the following are true:

- a user can select a member and upload one zip material package,
- supported files are safely extracted and indexed,
- parsed files are classified or flagged for review,
- a package-level check can be run for that member,
- missing/duplicate/conflicting issues are returned in structured form,
- member detail shows latest import batch and latest package-check results,
- dashboard and member detail APIs return stable frontend-ready shapes,
- automated tests cover repository, service, and API behavior.

## 23. Next Increment After V1

If V1 is completed and stable, the next increment should be `OCR Review Workflow V1`:

- add OCR task table,
- store raw OCR spans and confidence,
- expose preview and confirm endpoints,
- let package checks consume confirmed text preferentially,
- and let the member detail surface unresolved OCR review tasks.

That is the correct next step because V1 will already provide:

- member-bound file batches,
- parsed-file records,
- and a deterministic route for unresolved files.
