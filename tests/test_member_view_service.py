from __future__ import annotations

import unittest
from pathlib import Path

from partymate.services.member_view_service import MemberViewService
from tests.support import make_temp_repo


class MemberViewServiceTests(unittest.TestCase):
    def test_build_member_detail_returns_frontend_ready_fields(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", apply_date="2026-03-01", notes="重点培养")
            material = repo.get_materials(member["id"])[0]
            repo.submit_material(material["id"], file_path="archives/入党申请书.docx")
            service = MemberViewService(repo)

            detail = service.build_member_detail(member["id"])

            self.assertIn("timeline", detail)
            self.assertIn("latest_import_batch", detail)
            self.assertIn("latest_material_check", detail)
            self.assertEqual(detail["materials"][0]["name"], "入党申请书")
            self.assertIn("submitted", detail["materials"][0])
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_build_dashboard_returns_total_and_stage_groups(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            repo.add_member(name="张三")
            repo.add_member(name="李四")
            service = MemberViewService(repo)

            dashboard = service.build_dashboard()

            self.assertIn("total", dashboard)
            self.assertIn("stages", dashboard)
            self.assertIn("applicant", dashboard["stages"])
            self.assertIn("members", dashboard["stages"]["applicant"])
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_build_member_detail_includes_pending_ocr_tasks(self) -> None:
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
            record = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="申请书扫描件.jpg",
                stored_path="scan.jpg",
                extension=".jpg",
                parser_type="image",
                parse_status="parsed",
            )
            repo.update_material_file(
                record["id"],
                full_text_path=str(raw_path),
                needs_review=1,
            )
            task = repo.create_ocr_task(
                member_id=member["id"],
                batch_id=batch["id"],
                material_file_id=record["id"],
                status="review_required",
                raw_segments_json='[{"text":"敬爱的党组只","confidence":0.42}]',
                confidence_summary_json='{"segment_count":1,"low_confidence_count":1}',
            )
            repo.update_material_file(
                record["id"],
                ocr_task_id=task["id"],
                review_status="review_required",
            )
            detail = MemberViewService(repo).build_member_detail(member["id"])

            self.assertEqual(detail["pending_ocr_task_count"], 1)
            self.assertEqual(detail["pending_ocr_tasks"][0]["task_id"], task["id"])
            self.assertEqual(
                detail["pending_ocr_tasks"][0]["review_status"],
                "review_required",
            )
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_build_member_detail_includes_active_memories(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            repo.create_member_memory(
                member_id=member["id"],
                kind="instruction",
                title="提醒事项",
                content="优先核对思想汇报时间线。",
                importance=3,
                pinned=1,
                source="manual",
            )
            repo.create_member_memory(
                member_id=member["id"],
                kind="note",
                title="已合并旧记录",
                content="旧记忆不再显示",
                importance=1,
                pinned=0,
                source="manual",
                merged_into_id=1,
            )

            detail = MemberViewService(repo).build_member_detail(member["id"])

            self.assertIn("memories", detail)
            self.assertEqual(detail["memory_count"], 1)
            self.assertEqual(detail["pinned_memory_count"], 1)
            self.assertEqual(detail["memories"][0]["title"], "提醒事项")
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
