from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from partymate.web import server
from partymate.web.server import create_app
from tests.support import make_temp_repo, make_zip_bytes


class MaterialWorkbenchApiTests(unittest.TestCase):
    def test_emit_startup_banner_handles_gbk_stdout(self) -> None:
        class GbkConsole(io.StringIO):
            encoding = "gbk"

            def write(self, s: str) -> int:
                s.encode(self.encoding)
                return super().write(s)

        console = GbkConsole()

        server._emit_startup_banner(console)

        output = console.getvalue()
        self.assertIn("PartyMate Web", output)
        self.assertIn("http://localhost:8567", output)

    @patch("partymate.services.material_import_service.parse_file")
    def test_import_endpoint_saves_member_archive_batch(self, mock_parse) -> None:
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
            zip_bytes = make_zip_bytes({"入党申请书.docx": b"fake-docx"})
            with TestClient(app) as client:
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

    def test_material_check_endpoint_uses_latest_batch_when_batch_id_missing(self) -> None:
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
            with TestClient(app) as client:
                response = client.post(
                    f"/api/members/{member['id']}/materials/check",
                    json={},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["batch_id"], batch["id"])
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_dashboard_and_member_endpoints_return_frontend_ready_shapes(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            with TestClient(app) as client:
                dashboard = client.get("/api/dashboard")
                detail = client.get(f"/api/members/{member['id']}")

            self.assertEqual(dashboard.status_code, 200)
            self.assertIn("total", dashboard.json())
            self.assertIn("stages", dashboard.json())
            self.assertIn("timeline", detail.json()["member"])
        finally:
            repo.close()
            temp_dir.cleanup()

    @patch("partymate.services.material_import_service.parse_file")
    def test_import_then_check_flow_returns_structured_summary(self, mock_parse) -> None:
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
            zip_bytes = make_zip_bytes({"入党申请书.docx": b"fake-docx"})
            with TestClient(app) as client:
                import_resp = client.post(
                    "/api/materials/archive/import",
                    files={"file": ("materials.zip", zip_bytes, "application/zip")},
                    data={"member_id": str(member["id"])},
                )
                check_resp = client.post(
                    f"/api/members/{member['id']}/materials/check",
                    json={},
                )

            self.assertEqual(import_resp.status_code, 200)
            self.assertEqual(check_resp.status_code, 200)
            self.assertIn("summary", check_resp.json())
            self.assertIn("errors", check_resp.json())
            self.assertIn("warnings", check_resp.json())
            self.assertIn("needs_review", check_resp.json())
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
