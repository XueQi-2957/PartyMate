"""PartyMate v2 — Agent Run Trace Service

Tracks every agent execution with:
- User input, model used, duration
- Individual tool calls with arguments and results
- Audit trail for accountability
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from partymate.db.repository import Repository


class AgentTraceService:
    """Records and queries agent execution history."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def start_run(
        self,
        user_input: str,
        member_id: int | None = None,
        model_used: str = "",
    ) -> tuple[str, float]:
        """Start a new agent run, returning (run_id, start_time)."""
        run_id = uuid.uuid4().hex[:12]
        # We write a placeholder; the real content is written on completion
        self.repo.create_agent_run(
            run_id=run_id,
            member_id=member_id,
            user_input=user_input,
            status="running",
            model_used=model_used,
        )
        return run_id, time.time()

    def record_tool_call(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        call_order: int,
        duration_ms: int,
    ) -> None:
        """Record a single tool call within a run."""
        self.repo.create_agent_run_tool_call(
            run_id=run_id,
            tool_name=tool_name,
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            result_summary=result[:200],
            duration_ms=duration_ms,
            call_order=call_order,
        )

    def finish_run(
        self,
        run_id: str,
        start_time: float,
        result_summary: str,
        status: str = "completed",
    ) -> dict[str, Any]:
        """Complete an agent run with final metadata."""
        duration_ms = int((time.time() - start_time) * 1000)
        # Retrieve tool calls for JSON
        tool_calls = self.repo.list_agent_run_tool_calls(run_id)
        tool_calls_json = json.dumps(
            [
                {
                    "tool_name": tc["tool_name"],
                    "result_summary": tc["result_summary"],
                    "duration_ms": tc["duration_ms"],
                }
                for tc in tool_calls
            ],
            ensure_ascii=False,
        )
        self.repo.conn.execute(
            "UPDATE agent_runs SET status = ?, duration_ms = ?, "
            "result_summary = ?, tool_calls_json = ? WHERE run_id = ?",
            (status, duration_ms, result_summary[:500], tool_calls_json, run_id),
        )
        self.repo.conn.commit()
        return self.repo.get_agent_run(run_id)

    def list_runs(self, limit: int = 30, member_id: int | None = None) -> list[dict[str, Any]]:
        """List recent agent runs."""
        return self.repo.list_agent_runs(limit=limit, member_id=member_id)

    def get_run_detail(self, run_id: str) -> dict[str, Any]:
        """Get a run with its tool calls."""
        run = self.repo.get_agent_run(run_id)
        if not run:
            return {}
        run["tool_calls"] = self.repo.list_agent_run_tool_calls(run_id)
        return run