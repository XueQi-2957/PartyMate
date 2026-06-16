"""
PartyMate — Import members from CSV.

CSV format (UTF-8, with BOM support):
  name, stage, apply_date, notes
  (stage defaults to 'applicant' if omitted)
"""

from __future__ import annotations

import csv
from io import StringIO

from partymate.db.repository import Repository


def import_from_csv(content: str) -> dict:
    """Import members from a CSV string.

    Returns:
        {"imported": int, "errors": [{"row": int, "error": str}, ...]}
    """
    reader = csv.DictReader(StringIO(content))
    repo = Repository()
    results: dict = {"imported": 0, "errors": []}

    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            results["errors"].append({
                "row": reader.line_num,
                "error": "缺少姓名 (name)"
            })
            continue

        stage = (row.get("stage") or "applicant").strip()
        apply_date = (row.get("apply_date") or "").strip()
        notes = (row.get("notes") or "").strip()

        try:
            member = repo.add_member(
                name=name,
                apply_date=apply_date or "",
                notes=notes,
            )
            member_id = member["id"]

            # Advance to the specified stage if beyond applicant
            valid_stages = [
                "applicant", "activist", "candidate",
                "probationary", "full_member",
            ]
            target_idx = valid_stages.index(stage) if stage in valid_stages else 0
            current_member = member
            for _ in range(target_idx):
                try:
                    current_member = repo.advance_stage(
                        current_member["id"],
                        event_date=apply_date,
                    )
                except ValueError:
                    break  # already at final stage

            results["imported"] += 1
        except Exception as e:
            results["errors"].append({
                "row": reader.line_num,
                "error": str(e),
            })

    return results
