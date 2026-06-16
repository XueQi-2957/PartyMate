# Member Memory V1 Design

## 1. Purpose

This document defines the next implementation increment after `OCR Review Workflow V1`.

The current codebase can already:

- manage members and stage progression,
- import member-bound material archives,
- run package-level deterministic checks,
- persist OCR review tasks,
- and expose a basic AI chat entry point.

What is still missing is member-scoped long-term memory.

Without that layer:

- the agent has no durable member-specific preferences or conclusions,
- the chat entry point cannot reliably stay inside one member's context,
- and users have no place to preserve review conclusions that should survive beyond one task.

## 2. Why This Is The Next Increment

`DEVPLAN.md` identifies `成员级独立记忆` as a core differentiator for the final local agent:

- each member must have an isolated memory namespace,
- only high-value long-term information should be retained,
- and the agent should load only the selected member's facts and memories.

The current repository already hints at this direction:

- `partymate/db/models.py` already defines `MemoryKind`,
- member detail pages already aggregate member-centered workflow state,
- and `POST /api/chat` already provides the integration seam for member context loading.

This increment converts that latent design into a usable first version.

## 3. Product Goal For V1

Deliver the first member-memory loop that allows a user to:

1. create and manage high-value memories for a specific member,
2. pin and merge important memories instead of letting them fragment,
3. view recent memories inside the member workflow,
4. bind AI chat to one selected member,
5. and ensure the agent receives only that member's facts and memories as explicit context.

## 4. Scope

### 4.1 In Scope

- add persistent `member_memories` storage,
- support memory kinds aligned with the existing enum:
  - `summary`
  - `risk`
  - `instruction`
  - `correction`
  - `note`
- support manual memory creation,
- support manual delete,
- support pin / unpin,
- support merge of multiple memories into one consolidated memory,
- expose member memory APIs,
- surface active memories in member detail,
- allow chat requests to carry `member_id`,
- build member-specific agent context from member facts plus active memories,
- add repository, service, API, and static-asset tests.

### 4.2 Out Of Scope For V1

- automatic post-run memory extraction by the model,
- global cross-member memory search,
- standalone memory vector retrieval,
- agent-run trace persistence,
- memory deduplication suggestions from the model,
- multi-user permission controls,
- a separate top-level memory management page.

V1 uses the existing member detail surface as the memory management entry point.

## 5. Key Product Decisions

### 5.1 Memory Namespace

Each memory belongs to exactly one member via `member_id`.

There is no shared memory pool in V1.

### 5.2 Human-Managed Memory First

V1 is intentionally manual:

- users create memories,
- users pin or delete memories,
- users explicitly merge overlapping memories,
- and the agent only consumes what has been curated.

This avoids weak automatic summarization logic being stored as durable truth.

### 5.3 Active Memory Model

Merged memories remain historically stored but are removed from the active list.

The active list is therefore:

- all memories for a member where `merged_into_id IS NULL`,
- ordered with pinned items first,
- then by latest update time.

### 5.4 Chat Context Boundary

`POST /api/chat` may optionally include `member_id`.

When `member_id` is present:

- the backend validates that the member exists,
- loads that member's facts and active memories,
- builds one bounded context string,
- and passes it to the agent runtime.

When `member_id` is absent, chat keeps the current generic behavior.

## 6. Architecture

V1 keeps the current local Python monolith and adds one focused service plus repository and API extensions.

### 6.1 Repository Layer

Persist member memories and expose CRUD plus merge-support helpers.

### 6.2 Service Layer

Add a `MemberMemoryService` responsible for:

- input normalization,
- kind validation,
- importance normalization,
- memory list shaping,
- merge behavior,
- and member-context string generation for the agent.

### 6.3 Member View Layer

Extend `MemberViewService` so member detail pages include:

- active memories,
- pinned memory count,
- and total active memory count.

### 6.4 Agent / API Layer

Extend the chat API and runtime so member-scoped context can be injected without changing the overall tool-calling architecture.

### 6.5 Frontend Layer

Reuse the existing kanban member detail area for:

- memory list rendering,
- quick memory creation,
- pin / unpin,
- delete,
- merge,
- and one-click binding of the current member to AI chat.

## 7. Storage Design

V1 adds one new table.

### 7.1 New Table: `member_memories`

Purpose: store durable member-bound memory entries.

Fields:

- `id INTEGER PRIMARY KEY`
- `member_id INTEGER NOT NULL REFERENCES members(id)`
- `kind TEXT NOT NULL`
- `title TEXT DEFAULT ''`
- `content TEXT NOT NULL`
- `importance INTEGER NOT NULL DEFAULT 2`
- `pinned INTEGER NOT NULL DEFAULT 0`
- `source TEXT DEFAULT ''`
- `merged_into_id INTEGER DEFAULT NULL REFERENCES member_memories(id)`
- `created_at TEXT DEFAULT (datetime('now','localtime'))`
- `updated_at TEXT DEFAULT (datetime('now','localtime'))`

Rules:

- `kind` must be one of the existing `MemoryKind` values,
- `content` is the durable memory body,
- `title` is a short operator-facing label,
- `pinned` controls top-of-list ordering and context priority,
- `merged_into_id` is null for active memories and set when a memory has been merged into another active memory.

## 8. Service Behavior

### 8.1 Create Memory

Input:

- `member_id`
- `kind`
- `content`
- optional `title`
- optional `importance`
- optional `pinned`
- optional `source`

Behavior:

- trim text fields,
- reject empty content,
- validate `kind`,
- normalize `importance` into `1..3`,
- persist the row,
- return the created memory.

### 8.2 Update Memory

V1 supports partial update for:

- `title`
- `content`
- `importance`
- `pinned`

This is primarily needed for pinning and correcting operator-entered text.

### 8.3 Delete Memory

Delete is physical delete in V1.

Reasoning:

- the app is still local and single-user,
- current repository patterns already use direct delete behavior,
- and there is no audit subsystem yet.

### 8.4 Merge Memories

Input:

- `member_id`
- `memory_ids`
- `kind`
- `content`
- optional `title`
- optional `importance`
- optional `pinned`

Behavior:

1. validate that all source memories exist and belong to the same member,
2. create a new consolidated memory,
3. mark source memories with `merged_into_id = new_memory_id`,
4. unpin the source memories,
5. return the new active memory.

### 8.5 Build Agent Context

The service builds one plain-text context block containing:

- member facts:
  - name
  - stage
  - status
  - grade
  - major
  - student_id
  - notes
- and active memories, pinned first.

The context is bounded and deterministic.

V1 should load at most the first `8` active memories for chat context.

## 9. API Design

### 9.1 Member Memory APIs

- `GET /api/members/{id}/memories`
- `POST /api/members/{id}/memories`
- `PATCH /api/members/{id}/memories/{memory_id}`
- `DELETE /api/members/{id}/memories/{memory_id}`
- `POST /api/members/{id}/memories/merge`

Response shape should be simple JSON objects with `memory` or `memories`.

### 9.2 Chat API Extension

Extend `POST /api/chat` request body with optional:

- `member_id`

If present, the response shape stays the same, but the runtime receives member context.

## 10. Frontend Behavior

## 10.1 Member Detail Memory Panel

Add a member-memory section containing:

- a quick-add form,
- active memory count,
- pinned-memory count,
- a list of active memories,
- per-item actions:
  - pin / unpin
  - delete
- merge checkboxes and a `merge selected` action.

## 10.2 Chat Context Indicator

Add a compact chat context strip showing:

- current bound member name,
- a clear action,
- and a way to bind the currently selected member from kanban into chat.

This keeps the member context visible and reduces accidental cross-member use.

## 11. Error Handling

- invalid `member_id` returns `404`,
- invalid `kind` returns `400`,
- empty `content` returns `400`,
- merge with fewer than two source memories returns `400`,
- merge across different members returns `400`,
- patch/delete against a missing memory returns `404`,
- chat with missing member returns `404`.

## 12. Testing Strategy

V1 must add automated coverage for:

- repository schema and CRUD behavior,
- merge behavior,
- agent-context construction,
- member detail memory aggregation,
- API CRUD and merge endpoints,
- chat member-context injection,
- static asset wiring for memory management and member-bound chat.

## 13. Relationship To Later Increments

This increment creates the durable substrate needed for later agent evolution:

- model-suggested memory extraction after OCR review or package checks,
- run-trace-backed memory provenance,
- member-specific task resumability,
- and stronger long-context agent workflows.

The important V1 distinction is:

- generic chat remains generic,
- member-bound chat becomes explicitly context-scoped,
- and durable memory becomes a managed product surface instead of an implicit idea.
