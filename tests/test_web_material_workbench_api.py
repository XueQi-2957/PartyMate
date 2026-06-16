from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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

    def test_ocr_task_endpoints_and_member_detail_pending_tasks(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir=str(Path(temp_dir.name) / "extract"),
                status="completed_with_review",
            )
            text_dir = Path(temp_dir.name) / "texts"
            text_dir.mkdir()
            raw_path = text_dir / "file_1.txt"
            raw_path.write_text("敬爱的党组只", encoding="utf-8")
            material_file = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="申请书扫描件.jpg",
                stored_path="scan.jpg",
                extension=".jpg",
                parser_type="image",
                parse_status="parsed",
            )
            repo.update_material_file(
                material_file["id"],
                full_text_path=str(raw_path),
                needs_review=1,
            )
            task = repo.create_ocr_task(
                member_id=member["id"],
                batch_id=batch["id"],
                material_file_id=material_file["id"],
                status="review_required",
                raw_segments_json='[{"text":"敬爱的党组只","confidence":0.42}]',
                confidence_summary_json='{"segment_count":1,"low_confidence_count":1}',
            )
            repo.update_material_file(
                material_file["id"],
                ocr_task_id=task["id"],
                review_status="review_required",
            )
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            with TestClient(app) as client:
                task_resp = client.get(f"/api/ocr/tasks/{task['id']}")
                confirm_resp = client.post(
                    "/api/ocr/confirm",
                    json={
                        "task_id": task["id"],
                        "confirmed_text": "敬爱的党组织 张三",
                        "review_notes": "修正 OCR 错字",
                    },
                )
                detail_resp = client.get(f"/api/members/{member['id']}")

            self.assertEqual(task_resp.status_code, 200)
            self.assertEqual(task_resp.json()["task"]["id"], task["id"])
            self.assertEqual(task_resp.json()["raw_text"], "敬爱的党组只")
            self.assertEqual(confirm_resp.status_code, 200)
            self.assertEqual(confirm_resp.json()["task"]["status"], "confirmed")
            self.assertIn("pending_ocr_tasks", detail_resp.json()["member"])
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

    def test_member_memory_endpoints_support_crud_and_merge(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            with TestClient(app) as client:
                create_one = client.post(
                    f"/api/members/{member['id']}/memories",
                    json={
                        "kind": "risk",
                        "title": "政审提醒",
                        "content": "政审材料需要重点跟进。",
                        "importance": 3,
                        "pinned": True,
                    },
                )
                create_two = client.post(
                    f"/api/members/{member['id']}/memories",
                    json={
                        "kind": "note",
                        "title": "补充观察",
                        "content": "提交材料节奏偏慢。",
                        "importance": 2,
                    },
                )
                listed = client.get(f"/api/members/{member['id']}/memories")

                memory_one_id = create_one.json()["memory"]["id"]
                memory_two_id = create_two.json()["memory"]["id"]
                patched = client.patch(
                    f"/api/members/{member['id']}/memories/{memory_two_id}",
                    json={"pinned": True, "title": "已更新观察"},
                )
                merged = client.post(
                    f"/api/members/{member['id']}/memories/merge",
                    json={
                        "memory_ids": [memory_one_id, memory_two_id],
                        "kind": "summary",
                        "title": "合并结论",
                        "content": "政审材料和提交节奏都需持续跟进。",
                        "importance": 3,
                        "pinned": True,
                    },
                )
                deleted = client.delete(
                    f"/api/members/{member['id']}/memories/{memory_one_id}"
                )
                active_after = client.get(f"/api/members/{member['id']}/memories")

            self.assertEqual(create_one.status_code, 200)
            self.assertEqual(create_two.status_code, 200)
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(len(listed.json()["memories"]), 2)
            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["memory"]["pinned"], 1)
            self.assertEqual(merged.status_code, 200)
            self.assertEqual(merged.json()["memory"]["kind"], "summary")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(active_after.status_code, 200)
            self.assertEqual(len(active_after.json()["memories"]), 1)
        finally:
            repo.close()
            temp_dir.cleanup()

    @patch("partymate.agent.run_agent", new_callable=AsyncMock)
    def test_chat_endpoint_passes_member_context_when_member_id_present(
        self,
        mock_run_agent,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                major="计算机科学与技术",
                student_id="2023010001",
            )
            repo.create_member_memory(
                member_id=member["id"],
                kind="instruction",
                title="提醒",
                content="思想汇报需重点关注时政结合部分。",
                importance=3,
                pinned=1,
                source="manual",
            )
            mock_run_agent.return_value = "ok"
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            with TestClient(app) as client:
                response = client.post(
                    "/api/chat",
                    json={"message": "请给出下一步建议", "member_id": member["id"]},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"], "ok")
            self.assertEqual(mock_run_agent.await_args.args[0], "请给出下一步建议")
            member_context = mock_run_agent.await_args.kwargs["member_context"]
            self.assertIn("成员姓名: 张三", member_context)
            self.assertIn("思想汇报需重点关注时政结合部分。", member_context)
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

    @patch("partymate.services.material_import_service.parse_file")
    def test_import_confirm_ocr_then_check_flow_clears_unresolved_review_issue(
        self,
        mock_parse,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                major="计算机科学与技术",
                student_id="2023010001",
            )
            mock_parse.return_value = {
                "filename": "思想汇报扫描件.jpg",
                "type": "image",
                "text": "李四 软件工程 2023010001 思想汇报",
                "pages": 1,
                "preview": "李四 软件工程 2023010001 思想汇报",
                "ocr_segments": [
                    {
                        "text": "李四 软件工程 2023010001 思想汇报",
                        "confidence": 0.42,
                        "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    }
                ],
                "error": None,
            }
            app = create_app(repository=repo, data_root=Path(temp_dir.name))
            zip_bytes = make_zip_bytes({"思想汇报扫描件.jpg": b"fake-image"})

            with TestClient(app) as client:
                import_resp = client.post(
                    "/api/materials/archive/import",
                    files={"file": ("materials.zip", zip_bytes, "application/zip")},
                    data={"member_id": str(member["id"])},
                )
                self.assertEqual(import_resp.status_code, 200)
                imported_file = import_resp.json()["files"][0]
                self.assertEqual(imported_file["review_status"], "review_required")

                first_check = client.post(
                    f"/api/members/{member['id']}/materials/check",
                    json={},
                )
                self.assertEqual(first_check.status_code, 200)
                first_review_codes = {
                    item["code"] for item in first_check.json()["needs_review"]
                }
                self.assertIn("unresolved_import_file", first_review_codes)
                self.assertIn("identity_conflict", first_review_codes)

                task_resp = client.get(f"/api/ocr/tasks/{imported_file['ocr_task_id']}")
                self.assertEqual(task_resp.status_code, 200)

                confirm_resp = client.post(
                    "/api/ocr/confirm",
                    json={
                        "task_id": imported_file["ocr_task_id"],
                        "confirmed_text": "张三 计算机科学与技术 2023010001 思想汇报",
                        "review_notes": "修正姓名与专业字段",
                    },
                )
                self.assertEqual(confirm_resp.status_code, 200)

                second_check = client.post(
                    f"/api/members/{member['id']}/materials/check",
                    json={},
                )
                self.assertEqual(second_check.status_code, 200)
                second_review_codes = {
                    item["code"] for item in second_check.json()["needs_review"]
                }
                self.assertNotIn("unresolved_import_file", second_review_codes)
                self.assertNotIn("identity_conflict", second_review_codes)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
