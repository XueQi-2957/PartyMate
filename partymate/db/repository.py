"""PartyMate v2 — SQLite repository layer.

Single Repository class wrapping sqlite3 with auto-commit.
All public methods accept / return plain dicts.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from typing import Any

from .models import MATERIALS_PER_STAGE, Stage


def _get_db_path() -> str:
    """Determine database file path.

    Priority:
    1. HERMES_AGENT_STATE env var (Hermes Agent mode)
    2. {project_root}/data/partymate.db
    """
    env = os.environ.get("HERMES_AGENT_STATE")
    if env:
        db_dir = env
    else:
        db_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data")
        )
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "partymate.db")


# ── Helper ──────────────────────────────────────────────────────


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in rows]


def _today_str() -> str:
    return date.today().isoformat()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Stage transition helpers ────────────────────────────────────

_STAGE_DATE_FIELD = {
    "applicant": "apply_date",
    "activist": "activist_date",
    "candidate": "candidate_date",
    "probationary": "probationary_date",
    "full_member": "full_member_date",
}

_STAGE_LABEL_CN = {
    "applicant": "申请入党",
    "activist": "入党积极分子",
    "candidate": "发展对象",
    "probationary": "预备党员",
    "full_member": "正式党员",
}

_STAGE_TRANSITION_EVENTS = {
    "applicant": [
        {"event_type": "递交申请", "note": "递交入党申请书"},
        {"event_type": "入党谈话", "note": "党支部派人谈话"},
    ],
    "activist": [
        {"event_type": "确定积极分子", "note": "确定为入党积极分子"},
        {"event_type": "党委备案(积极分子)", "note": "报上级党委备案"},
    ],
    "candidate": [
        {"event_type": "确定发展对象", "note": "确定为发展对象"},
        {"event_type": "公示(发展对象)", "note": "发展对象公示"},
        {"event_type": "党委备案(发展对象)", "note": "报上级党委备案"},
        {"event_type": "政治审查", "note": "政治审查"},
        {"event_type": "短期培训", "note": "短期集中培训"},
    ],
    "probationary": [
        {"event_type": "党委预审", "note": "党委预审"},
        {"event_type": "填写志愿书", "note": "填写入党志愿书"},
        {"event_type": "支部大会(接收)", "note": "支部大会讨论接收预备党员"},
        {"event_type": "党委谈话", "note": "党委派人谈话"},
        {"event_type": "党委审批", "note": "党委审批"},
        {"event_type": "入党宣誓", "note": "入党宣誓"},
    ],
    "full_member": [
        {"event_type": "提出转正申请", "note": "预备党员提出转正申请"},
        {"event_type": "支部大会(转正)", "note": "支部大会讨论转正"},
        {"event_type": "公示(转正)", "note": "转正公示"},
        {"event_type": "党委审批(转正)", "note": "党委审批转正"},
        {"event_type": "归档", "note": "材料归档"},
    ],
}


# ── Repository ──────────────────────────────────────────────────


class Repository:
    """SQLite repository for PartyMate v2."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _get_db_path()
        # Starlette TestClient may handle requests on a different thread from
        # the one that created the injected repository.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    # ── Schema ──────────────────────────────────────────────

    def create_tables(self) -> None:
        """Create all tables if they do not exist."""
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    gender TEXT DEFAULT '',
                    grade TEXT DEFAULT '',
                    major TEXT DEFAULT '',
                    student_id TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    stage TEXT NOT NULL DEFAULT 'applicant',
                    status TEXT NOT NULL DEFAULT 'active',
                    apply_date TEXT DEFAULT '',
                    activist_date TEXT DEFAULT '',
                    candidate_date TEXT DEFAULT '',
                    probationary_date TEXT DEFAULT '',
                    full_member_date TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS timeline_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    event_type TEXT NOT NULL,
                    event_date TEXT DEFAULT '',
                    expected_date TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    material_name TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    is_required INTEGER NOT NULL DEFAULT 1,
                    is_submitted INTEGER NOT NULL DEFAULT 0,
                    submitted_date TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER REFERENCES members(id),
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    due_date TEXT DEFAULT '',
                    remind_before_days INTEGER DEFAULT 7,
                    is_sent INTEGER NOT NULL DEFAULT 0,
                    sent_at TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

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
                    ocr_task_id INTEGER DEFAULT NULL,
                    review_status TEXT DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS ocr_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id INTEGER NOT NULL REFERENCES members(id),
                    batch_id INTEGER NOT NULL REFERENCES material_import_batches(id),
                    material_file_id INTEGER NOT NULL UNIQUE REFERENCES material_files(id),
                    status TEXT NOT NULL,
                    raw_segments_json TEXT NOT NULL,
                    confidence_summary_json TEXT NOT NULL,
                    confirmed_text_path TEXT DEFAULT '',
                    review_notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

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

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    member_id INTEGER DEFAULT NULL REFERENCES members(id),
                    user_input TEXT NOT NULL,
                    tool_calls_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'completed',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    model_used TEXT DEFAULT '',
                    result_summary TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS agent_run_tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL DEFAULT '{}',
                    result_summary TEXT DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    call_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS meeting_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_title TEXT DEFAULT '',
                    action_text TEXT NOT NULL,
                    responsible_person TEXT DEFAULT '',
                    due_date TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    member_id INTEGER DEFAULT NULL REFERENCES members(id),
                    reminder_id INTEGER DEFAULT NULL REFERENCES reminders(id),
                    source_meeting_id TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    member_id INTEGER DEFAULT NULL REFERENCES members(id),
                    message_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    tool_calls_json TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );
            """)
            self._ensure_column(
                "material_files",
                "ocr_task_id",
                "INTEGER DEFAULT NULL",
            )
            self._ensure_column(
                "material_files",
                "review_status",
                "TEXT DEFAULT ''",
            )

    # ── Members ─────────────────────────────────────────────

    def add_member(
        self,
        name: str,
        gender: str = "",
        grade: str = "",
        major: str = "",
        student_id: str = "",
        phone: str = "",
        apply_date: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Insert a new member and return its dict.

        If apply_date is set, auto-generate applicant-stage timeline events
        and materials.
        """
        cursor = self.conn.execute(
            """INSERT INTO members (name, gender, grade, major, student_id,
                                    phone, stage, status, apply_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, 'applicant', 'active', ?, ?)""",
            (name, gender, grade, major, student_id, phone, apply_date, notes),
        )
        member_id = cursor.lastrowid

        # auto-generate timeline events for applicant stage
        if apply_date:
            self._auto_generate_events(member_id, "applicant", apply_date)
            self._auto_generate_materials(member_id, "applicant")

        return self.get_member(member_id)

    def get_members(
        self, stage: str | None = None, status: str = "active"
    ) -> list[dict[str, Any]]:
        """List members, optionally filtered by stage and status."""
        parts = ["SELECT * FROM members WHERE 1=1"]
        params: list[Any] = []
        if stage:
            parts.append("AND stage = ?")
            params.append(stage)
        if status:
            parts.append("AND status = ?")
            params.append(status)
        parts.append("ORDER BY created_at DESC")
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    def get_member(self, member_id: int) -> dict[str, Any]:
        """Return a single member with nested events, materials, reminders."""
        row = self.conn.execute(
            "SELECT * FROM members WHERE id = ?", (member_id,)
        ).fetchone()
        if row is None:
            return {}
        member = _row_to_dict(row)
        member["events"] = self.get_events(member_id)
        member["materials"] = self.get_materials(member_id)
        member["reminders"] = self.get_reminders(member_id=member_id, limit=50)
        return member

    def update_member(self, member_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update member fields. Sets updated_at automatically."""
        if not kwargs:
            return self.get_member(member_id)
        sets = []
        params: list[Any] = []
        for key, val in kwargs.items():
            if key in ("id", "created_at", "updated_at"):
                continue
            sets.append(f"{key} = ?")
            params.append(val)
        sets.append("updated_at = ?")
        params.append(_now_str())
        params.append(member_id)
        sql = f"UPDATE members SET {', '.join(sets)} WHERE id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()
        return self.get_member(member_id)

    def advance_stage(
        self, member_id: int, event_date: str = ""
    ) -> dict[str, Any]:
        """Move a member to the next stage.

        1. Determine current stage → next stage
        2. Set the stage-date field on members
        3. Generate timeline events for the new stage
        4. Generate materials for the new stage
        5. Update member stage + status
        """
        member = self.get_member(member_id)
        if not member:
            raise ValueError(f"Member {member_id} not found")

        current_stage_str = member.get("stage", "applicant")
        try:
            current = Stage(current_stage_str)
        except ValueError:
            raise ValueError(f"Unknown stage: {current_stage_str}")

        next_stage = current.next_stage()
        if next_stage is None:
            raise ValueError(f"Member {member_id} is already at final stage")

        next_str = str(next_stage)
        use_date = event_date or _today_str()

        # Mark all previous-stage events as completed
        for prev_stage_key in list(_STAGE_TRANSITION_EVENTS.keys()):
            if prev_stage_key == next_str:
                break  # stop before events of the new stage
            for ev in _STAGE_TRANSITION_EVENTS[prev_stage_key]:
                self.conn.execute(
                    "UPDATE timeline_events SET status = 'completed', event_date = ? "
                    "WHERE member_id = ? AND event_type = ? AND status = 'pending'",
                    (use_date, member_id, ev["event_type"]),
                )
            # Mark materials from this previous stage as submitted
            if prev_stage_key in MATERIALS_PER_STAGE:
                self.conn.execute(
                    "UPDATE materials SET is_submitted = 1, submitted_date = ? "
                    "WHERE member_id = ? AND stage = ? AND is_submitted = 0",
                    (use_date, member_id, prev_stage_key),
                )

        # Set the stage-date field
        date_field = _STAGE_DATE_FIELD[next_str]
        self.conn.execute(
            f"UPDATE members SET stage = ?, status = 'active', "
            f"{date_field} = ?, updated_at = ? WHERE id = ?",
            (next_str, use_date, _now_str(), member_id),
        )
        self.conn.commit()

        # Auto-generate events + materials for the new stage
        self._auto_generate_events(member_id, next_str, use_date)
        self._auto_generate_materials(member_id, next_str)

        return self.get_member(member_id)

    def delete_member(self, member_id: int) -> bool:
        """Delete a member and all related records (cascade manually)."""
        with self.conn:
            self.conn.execute("DELETE FROM reminders WHERE member_id = ?", (member_id,))
            self.conn.execute("DELETE FROM materials WHERE member_id = ?", (member_id,))
            self.conn.execute(
                "DELETE FROM timeline_events WHERE member_id = ?", (member_id,)
            )
            self.conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        return True

    # ── Timeline Events ─────────────────────────────────────

    def add_event(
        self,
        member_id: int,
        event_type: str,
        event_date: str = "",
        expected_date: str = "",
        status: str = "pending",
        notes: str = "",
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO timeline_events
               (member_id, event_type, event_date, expected_date, status, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (member_id, event_type, event_date, expected_date, status, notes),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM timeline_events WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)

    def get_events(self, member_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM timeline_events WHERE member_id = ? "
            "ORDER BY event_date ASC, id ASC",
            (member_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    # ── Materials ───────────────────────────────────────────

    def add_material(
        self,
        member_id: int,
        material_name: str,
        stage: str,
        is_required: bool = True,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO materials
               (member_id, material_name, stage, is_required)
               VALUES (?, ?, ?, ?)""",
            (member_id, material_name, stage, 1 if is_required else 0),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM materials WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)

    def submit_material(self, material_id: int, file_path: str = "") -> dict[str, Any]:
        """Mark a material as submitted."""
        self.conn.execute(
            """UPDATE materials SET is_submitted = 1, submitted_date = ?,
               file_path = ? WHERE id = ?""",
            (_today_str(), file_path, material_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
        return _row_to_dict(row)

    def get_materials(
        self, member_id: int, stage: str | None = None
    ) -> list[dict[str, Any]]:
        if stage:
            rows = self.conn.execute(
                "SELECT * FROM materials WHERE member_id = ? AND stage = ? "
                "ORDER BY is_required DESC, id ASC",
                (member_id, stage),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM materials WHERE member_id = ? "
                "ORDER BY is_required DESC, id ASC",
                (member_id,),
            ).fetchall()
        return _rows_to_dicts(rows)

    # ── Material Import Batches ────────────────────────────

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

    def update_material_import_batch(
        self, batch_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        if not kwargs:
            return self.get_material_import_batch(batch_id)
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
            "SELECT * FROM material_import_batches WHERE member_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (member_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_material_import_batches(
        self, member_id: int, limit: int = 5
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM material_import_batches WHERE member_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (member_id, limit),
        ).fetchall()
        return _rows_to_dicts(rows)

    # ── Imported Material Files ────────────────────────────

    def add_material_file(
        self,
        batch_id: int,
        member_id: int,
        original_name: str,
        stored_path: str,
        extension: str,
        parser_type: str,
        parse_status: str,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO material_files
               (batch_id, member_id, original_name, stored_path,
                extension, parser_type, parse_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                batch_id,
                member_id,
                original_name,
                stored_path,
                extension,
                parser_type,
                parse_status,
            ),
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
        if not kwargs:
            return self.get_material_file(file_id)
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

    # ── OCR Review Tasks ───────────────────────────────────

    def create_ocr_task(
        self,
        member_id: int,
        batch_id: int,
        material_file_id: int,
        status: str,
        raw_segments_json: str,
        confidence_summary_json: str,
        confirmed_text_path: str = "",
        review_notes: str = "",
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO ocr_tasks
               (member_id, batch_id, material_file_id, status, raw_segments_json,
                confidence_summary_json, confirmed_text_path, review_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id,
                batch_id,
                material_file_id,
                status,
                raw_segments_json,
                confidence_summary_json,
                confirmed_text_path,
                review_notes,
            ),
        )
        self.conn.commit()
        return self.get_ocr_task(int(cursor.lastrowid))

    def get_ocr_task(self, task_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM ocr_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return _row_to_dict(row)

    def update_ocr_task(self, task_id: int, **kwargs: Any) -> dict[str, Any]:
        if not kwargs:
            return self.get_ocr_task(task_id)
        sets = []
        params: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.append(_now_str())
        params.append(task_id)
        self.conn.execute(
            f"UPDATE ocr_tasks SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_ocr_task(task_id)

    def list_member_ocr_tasks(
        self,
        member_id: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        parts = ["SELECT * FROM ocr_tasks WHERE member_id = ?"]
        params: list[Any] = [member_id]
        if status:
            parts.append("AND status = ?")
            params.append(status)
        parts.append("ORDER BY created_at DESC, id DESC")
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    def get_ocr_task_by_material_file(self, material_file_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM ocr_tasks WHERE material_file_id = ?",
            (material_file_id,),
        ).fetchone()
        return _row_to_dict(row)

    # ── Member Memories ────────────────────────────────────

    def create_member_memory(
        self,
        member_id: int,
        kind: str,
        title: str,
        content: str,
        importance: int = 2,
        pinned: int = 0,
        source: str = "",
        merged_into_id: int | None = None,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO member_memories
               (member_id, kind, title, content, importance, pinned, source, merged_into_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id,
                kind,
                title,
                content,
                importance,
                pinned,
                source,
                merged_into_id,
            ),
        )
        self.conn.commit()
        return self.get_member_memory(int(cursor.lastrowid))

    def get_member_memory(self, memory_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM member_memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_member_memories(
        self,
        member_id: int,
        include_merged: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        parts = ["SELECT * FROM member_memories WHERE member_id = ?"]
        params: list[Any] = [member_id]
        if not include_merged:
            parts.append("AND merged_into_id IS NULL")
        parts.append("ORDER BY pinned DESC, updated_at DESC, id DESC LIMIT ?")
        params.append(limit)
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    def update_member_memory(self, memory_id: int, **kwargs: Any) -> dict[str, Any]:
        if not kwargs:
            return self.get_member_memory(memory_id)
        sets = []
        params: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.append(_now_str())
        params.append(memory_id)
        self.conn.execute(
            f"UPDATE member_memories SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_member_memory(memory_id)

    def delete_member_memory(self, memory_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM member_memories WHERE id = ?",
            (memory_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ── Material Check Results ─────────────────────────────

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
               (member_id, batch_id, status, error_count, warning_count,
                review_count, summary_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id,
                batch_id,
                status,
                error_count,
                warning_count,
                review_count,
                summary_json,
            ),
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
            "SELECT * FROM member_material_checks WHERE member_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (member_id,),
        ).fetchone()
        return _row_to_dict(row)

    # ── Reminders ───────────────────────────────────────────

    def add_reminder(
        self,
        member_id: int,
        title: str,
        description: str = "",
        due_date: str = "",
        remind_before_days: int = 7,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO reminders
               (member_id, title, description, due_date, remind_before_days)
               VALUES (?, ?, ?, ?, ?)""",
            (member_id, title, description, due_date, remind_before_days),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)

    def get_reminders(
        self,
        member_id: int | None = None,
        is_sent: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        parts = ["SELECT * FROM reminders WHERE 1=1"]
        params: list[Any] = []
        if member_id is not None:
            parts.append("AND member_id = ?")
            params.append(member_id)
        if is_sent is not None:
            parts.append("AND is_sent = ?")
            params.append(is_sent)
        parts.append("ORDER BY due_date ASC, created_at DESC")
        parts.append(f"LIMIT ?")
        params.append(limit)
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    # ── Agent Runs ──────────────────────────────────────────

    def create_agent_run(
        self,
        run_id: str,
        member_id: int | None,
        user_input: str,
        tool_calls_json: str = "[]",
        status: str = "completed",
        duration_ms: int = 0,
        model_used: str = "",
        result_summary: str = "",
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO agent_runs
               (run_id, member_id, user_input, tool_calls_json, status,
                duration_ms, model_used, result_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                member_id,
                user_input,
                tool_calls_json,
                status,
                duration_ms,
                model_used,
                result_summary,
            ),
        )
        self.conn.commit()
        return self.get_agent_run(run_id)

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_agent_runs(
        self, limit: int = 50, member_id: int | None = None
    ) -> list[dict[str, Any]]:
        parts = ["SELECT * FROM agent_runs WHERE 1=1"]
        params: list[Any] = []
        if member_id is not None:
            parts.append("AND member_id = ?")
            params.append(member_id)
        parts.append("ORDER BY created_at DESC LIMIT ?")
        params.append(limit)
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    def create_agent_run_tool_call(
        self,
        run_id: str,
        tool_name: str,
        arguments_json: str = "{}",
        result_summary: str = "",
        duration_ms: int = 0,
        call_order: int = 0,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO agent_run_tool_calls
               (run_id, tool_name, arguments_json, result_summary, duration_ms, call_order)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, tool_name, arguments_json, result_summary, duration_ms, call_order),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM agent_run_tool_calls WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _row_to_dict(row)

    def list_agent_run_tool_calls(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM agent_run_tool_calls WHERE run_id = ? ORDER BY call_order ASC",
            (run_id,),
        ).fetchall()
        return _rows_to_dicts(rows)

    # ── Meeting Actions ─────────────────────────────────────

    def create_meeting_action(
        self,
        action_text: str,
        meeting_title: str = "",
        responsible_person: str = "",
        due_date: str = "",
        status: str = "pending",
        member_id: int | None = None,
        reminder_id: int | None = None,
        source_meeting_id: str = "",
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO meeting_actions
               (action_text, meeting_title, responsible_person, due_date,
                status, member_id, reminder_id, source_meeting_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action_text,
                meeting_title,
                responsible_person,
                due_date,
                status,
                member_id,
                reminder_id,
                source_meeting_id,
            ),
        )
        self.conn.commit()
        return self.get_meeting_action(int(cursor.lastrowid))

    def get_meeting_action(self, action_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM meeting_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list_meeting_actions(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        parts = ["SELECT * FROM meeting_actions WHERE 1=1"]
        params: list[Any] = []
        if status:
            parts.append("AND status = ?")
            params.append(status)
        parts.append("ORDER BY due_date ASC, created_at DESC LIMIT ?")
        params.append(limit)
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return _rows_to_dicts(rows)

    def update_meeting_action(self, action_id: int, **kwargs: Any) -> dict[str, Any]:
        if not kwargs:
            return self.get_meeting_action(action_id)
        sets = []
        params: list[Any] = []
        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.append(_now_str())
        params.append(action_id)
        self.conn.execute(
            f"UPDATE meeting_actions SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_meeting_action(action_id)

    def delete_meeting_action(self, action_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM meeting_actions WHERE id = ?",
            (action_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ── Dashboard ───────────────────────────────────────────
    def get_dashboard(self) -> dict[str, Any]:
        """Aggregate overview data for the web dashboard."""
        result: dict[str, Any] = {}

        # total members
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM members").fetchone()
        result["total_members"] = row["cnt"] if row else 0

        # by stage
        stage_rows = self.conn.execute(
            "SELECT stage, COUNT(*) AS cnt FROM members "
            "WHERE status = 'active' GROUP BY stage"
        ).fetchall()
        by_stage: dict[str, int] = {s: 0 for s in _STAGE_DATE_FIELD}
        for r in stage_rows:
            by_stage[r["stage"]] = r["cnt"]
        result["by_stage"] = by_stage

        # overdue events
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM timeline_events "
            "WHERE status = 'overdue'"
        ).fetchone()
        result["overdue_events"] = row["cnt"] if row else 0

        # pending materials
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM materials "
            "WHERE is_submitted = 0 AND is_required = 1"
        ).fetchone()
        result["pending_materials"] = row["cnt"] if row else 0

        # today's reminders
        today = _today_str()
        reminder_rows = self.conn.execute(
            "SELECT * FROM reminders WHERE due_date = ? AND is_sent = 0 "
            "ORDER BY created_at DESC LIMIT 20",
            (today,),
        ).fetchall()
        result["today_reminders"] = _rows_to_dicts(reminder_rows)

        return result

    # ── Internal helpers ────────────────────────────────────

    def _auto_generate_events(
        self, member_id: int, stage: str, base_date: str
    ) -> None:
        """Insert timeline events for a given stage."""
        events = _STAGE_TRANSITION_EVENTS.get(stage, [])
        for ev in events:
            self.conn.execute(
                """INSERT INTO timeline_events
                   (member_id, event_type, event_date, status, notes)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (member_id, ev["event_type"], base_date, ev["note"]),
            )
        self.conn.commit()

    def _auto_generate_materials(self, member_id: int, stage: str) -> None:
        """Insert material checklist items for a given stage."""
        materials = MATERIALS_PER_STAGE.get(stage, [])
        for mat_name in materials:
            self.conn.execute(
                """INSERT INTO materials
                   (member_id, material_name, stage, is_required)
                   VALUES (?, ?, ?, 1)""",
                (member_id, mat_name, stage),
            )
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return
        self.conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
        self.conn.commit()

    # ── Chat Memory ─────────────────────────────────────────

    def get_chat_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None

    def create_chat_session(self, session_id: str, title: str = "", member_id: int | None = None) -> dict[str, Any]:
        self.conn.execute(
            """INSERT INTO chat_sessions (id, title, member_id)
               VALUES (?, ?, ?)""",
            (session_id, title, member_id),
        )
        self.conn.commit()
        return self.get_chat_session(session_id) or {}

    def update_chat_session(self, session_id: str, title: str | None = None, message_count: int | None = None) -> None:
        sets = []
        params = []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if message_count is not None:
            sets.append("message_count = ?")
            params.append(message_count)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(_now_str())
        params.append(session_id)
        self.conn.execute(
            f"UPDATE chat_sessions SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()

    def list_chat_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return _rows_to_dicts(rows)

    def delete_chat_session(self, session_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    def add_chat_message(self, session_id: str, role: str, content: str, tool_calls_json: str = "") -> dict[str, Any]:
        cursor = self.conn.execute(
            """INSERT INTO chat_messages (session_id, role, content, tool_calls_json)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, tool_calls_json),
        )
        msg_id = cursor.lastrowid
        self.conn.execute(
            "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
            (_now_str(), session_id)
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM chat_messages WHERE id = ?", (msg_id,)).fetchone()
        return _row_to_dict(row)

    def get_chat_messages(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return _rows_to_dicts(list(reversed(rows)))

    def close(self) -> None:
        self.conn.close()
