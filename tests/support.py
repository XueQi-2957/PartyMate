from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from partymate.db.repository import Repository


def make_temp_repo() -> tuple[tempfile.TemporaryDirectory[str], Repository]:
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

