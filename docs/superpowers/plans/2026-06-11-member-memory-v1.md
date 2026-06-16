# Member Memory V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first member-scoped long-term memory workflow by persisting member memories, exposing memory-management APIs, surfacing memories in member detail, and allowing chat requests to load only the selected member's facts and memories.

**Architecture:** Keep the current Python local monolith. Extend the SQLite repository with `member_memories`, add a focused `MemberMemoryService` for validation, merge behavior, and agent-context generation, then wire Starlette endpoints, the lightweight agent runtime, and the static kanban/chat UI to the new member-memory workflow.

**Tech Stack:** Python 3.11, sqlite3, Starlette, unittest, pathlib, existing static HTML/CSS/JS frontend

---

## File Map

### New Files

- `partymate/services/member_memory_service.py`
  - member memory CRUD orchestration, merge behavior, and agent-context building
- `tests/test_repository_member_memory.py`
  - repository schema and CRUD coverage for `member_memories`
- `tests/test_member_memory_service.py`
  - service-level validation, merge, and context-building tests

### Modified Files

- `partymate/db/repository.py`
  - create `member_memories` and add CRUD helpers
- `partymate/services/member_view_service.py`
  - expose active member memories in detail payloads
- `partymate/services/__init__.py`
  - export `MemberMemoryService`
- `partymate/agent.py`
  - accept optional `member_context` and inject it into the prompt
- `partymate/web/server.py`
  - add memory APIs and extend chat with optional `member_id`
- `partymate/web/static/index.html`
  - add chat member-context strip hooks
- `partymate/web/static/app.js`
  - add memory CRUD / merge UI flows and member-bound chat helpers
- `tests/test_member_view_service.py`
  - assert member detail includes active memories
- `tests/test_web_material_workbench_api.py`
  - cover memory APIs and chat context injection
- `tests/test_static_material_workbench_assets.py`
  - assert memory-management and chat-context frontend wiring exists

## Task 1: Add Repository Member Memory Persistence

**Files:**
- Create: `tests/test_repository_member_memory.py`
- Modify: `partymate/db/repository.py`

- [ ] **Step 1: Write the failing tests**

```python
class RepositoryMemberMemoryTests(unittest.TestCase):
    def test_create_tables_adds_member_memories_table(self) -> None:
        ...

    def test_repository_creates_lists_updates_and_deletes_member_memories(self) -> None:
        ...
```

Assert:

- `member_memories` exists,
- create returns the inserted row,
- list orders pinned first,
- update can toggle `pinned`,
- delete removes the row,
- merge helpers can mark `merged_into_id`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_repository_member_memory -v`

Expected: `FAIL` because `member_memories` and repository helpers do not yet exist.

- [ ] **Step 3: Write the minimal implementation**

Add to `Repository.create_tables()`:

```sql
CREATE TABLE IF NOT EXISTS member_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    kind TEXT NOT NULL,
    title TEXT DEFAULT '',
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 2,
    pinned INTEGER NOT NULL DEFAULT 0,
    source TEXT DEFAULT '',
    merged_into_id INTEGER DEFAULT NULL REFERENCES member_memories(id),
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

Add helpers:

- `create_member_memory(...)`
- `get_member_memory(memory_id)`
- `list_member_memories(member_id, include_merged=False, limit=50)`
- `update_member_memory(memory_id, **kwargs)`
- `delete_member_memory(memory_id)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_repository_member_memory -v`

Expected: `OK`

## Task 2: Add Member Memory Service

**Files:**
- Create: `partymate/services/member_memory_service.py`
- Create: `tests/test_member_memory_service.py`
- Modify: `partymate/services/__init__.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:

- create validates `kind` and non-empty `content`,
- merge creates a new active memory and archives source memories via `merged_into_id`,
- context building includes member facts plus active memories.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_member_memory_service -v`

Expected: `FAIL` because `MemberMemoryService` does not yet exist.

- [ ] **Step 3: Write the minimal implementation**

Implement:

```python
class MemberMemoryService:
    def create_memory(...)
    def list_memories(...)
    def update_memory(...)
    def delete_memory(...)
    def merge_memories(...)
    def build_agent_context(...)
```

Rules:

- validate `MemoryKind`,
- clamp importance to `1..3`,
- reject merge requests with fewer than `2` source memories,
- build deterministic plain-text context with max `8` memories.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_member_memory_service -v`

Expected: `OK`

## Task 3: Surface Memories In Member Detail

**Files:**
- Modify: `partymate/services/member_view_service.py`
- Modify: `tests/test_member_view_service.py`

- [ ] **Step 1: Write the failing test**

Extend member detail coverage to assert:

- `memories` exists,
- `memory_count` exists,
- `pinned_memory_count` exists,
- returned memories are frontend-ready.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_member_view_service -v`

Expected: `FAIL` because member detail does not yet expose memory data.

- [ ] **Step 3: Write the minimal implementation**

Load active memories through `MemberMemoryService` and append:

```python
"memories": memories,
"memory_count": len(memories),
"pinned_memory_count": sum(1 for item in memories if item.get("pinned")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_member_view_service -v`

Expected: `OK`

## Task 4: Add Memory APIs And Member-Bound Chat

**Files:**
- Modify: `partymate/web/server.py`
- Modify: `partymate/agent.py`
- Modify: `tests/test_web_material_workbench_api.py`

- [ ] **Step 1: Write the failing tests**

Add API tests for:

- `GET /api/members/{id}/memories`
- `POST /api/members/{id}/memories`
- `PATCH /api/members/{id}/memories/{memory_id}`
- `DELETE /api/members/{id}/memories/{memory_id}`
- `POST /api/members/{id}/memories/merge`
- `POST /api/chat` passing `member_id` through to `run_agent(..., member_context=...)`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_web_material_workbench_api -v`

Expected: `FAIL` because the routes and chat context integration do not yet exist.

- [ ] **Step 3: Write the minimal implementation**

In `create_app()`:

- instantiate `MemberMemoryService`,
- add the new memory routes,
- validate member existence,
- return `400/404` on invalid inputs.

In `partymate/agent.py`:

```python
async def run_agent(user_input: str, member_context: str = "") -> str:
    ...
```

If `member_context` is non-empty, inject it as an additional system message before the user message.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.test_web_material_workbench_api -v`

Expected: `OK`

## Task 5: Add Frontend Memory Management And Chat Context Controls

**Files:**
- Modify: `partymate/web/static/index.html`
- Modify: `partymate/web/static/app.js`
- Modify: `tests/test_static_material_workbench_assets.py`

- [ ] **Step 1: Write the failing test**

Assert the static assets contain hooks for:

- chat member-context strip,
- memory creation,
- memory pin/delete actions,
- memory merge actions.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `FAIL` because the HTML and JS hooks do not yet exist.

- [ ] **Step 3: Write the minimal implementation**

Add:

- a chat context indicator row,
- member detail memory section rendering,
- `bindMemberChatContext(...)`
- `clearChatMemberContext()`
- `saveMemberMemory(...)`
- `toggleMemberMemoryPinned(...)`
- `deleteMemberMemory(...)`
- `mergeSelectedMemories(...)`

Update `sendChat()` to include:

```javascript
await callAPI('chat', { message: fullMsg, member_id: window._chatMemberId || null })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_static_material_workbench_assets -v`

Expected: `OK`

## Task 6: Run Full Verification

**Files:**
- No code changes required unless failures appear

- [ ] **Step 1: Run targeted tests**

Run:

```bash
uv run python -m unittest \
  tests.test_repository_member_memory \
  tests.test_member_memory_service \
  tests.test_member_view_service \
  tests.test_web_material_workbench_api \
  tests.test_static_material_workbench_assets -v
```

Expected: all pass.

- [ ] **Step 2: Run the full suite**

Run: `uv run python -m unittest discover -s tests -v`

Expected: all tests pass with the new memory workflow included.

- [ ] **Step 3: Perform a runtime smoke check**

Exercise:

- create a member memory,
- pin one memory,
- merge two memories,
- call `/api/chat` with `member_id`,
- confirm the request path still works without a live model by inspecting the server response path or patched test coverage.

- [ ] **Step 4: Record outcomes**

Document the final implemented surface:

- repository table and helpers,
- service behavior,
- API endpoints,
- member detail memory UI,
- member-bound chat context behavior.
