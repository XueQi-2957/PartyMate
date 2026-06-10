from __future__ import annotations

import unittest
from pathlib import Path

from partymate.services.material_check_service import MaterialCheckService
from tests.support import make_temp_repo


class MaterialCheckServiceTests(unittest.TestCase):
    def test_run_for_member_reports_missing_duplicate_and_stage_conflicts(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                grade="2023级",
                major="计算机科学与技术",
                student_id="2023010001",
                apply_date="2026-03-01",
            )
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed",
            )
            text_dir = Path(temp_dir.name) / "texts"
            text_dir.mkdir()

            first = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书-1.docx",
                stored_path="a.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            second = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书-2.docx",
                stored_path="b.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            late_stage = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="转正申请书.docx",
                stored_path="c.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )

            (text_dir / "file_1.txt").write_text(
                "张三 2023010001 敬爱的党组织 2026年3月1日",
                encoding="utf-8",
            )
            (text_dir / "file_2.txt").write_text(
                "张三 2023010001 敬爱的党组织 2026年3月1日",
                encoding="utf-8",
            )
            (text_dir / "file_3.txt").write_text(
                "张三 于2025年1月1日提出转正申请",
                encoding="utf-8",
            )

            repo.update_material_file(
                first["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_1.txt"),
            )
            repo.update_material_file(
                second["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_2.txt"),
            )
            repo.update_material_file(
                late_stage["id"],
                material_type="转正申请书",
                material_stage="full_member",
                recognition_source="filename_exact",
                full_text_path=str(text_dir / "file_3.txt"),
            )

            result = MaterialCheckService(repo).run_for_member(member["id"], batch["id"])
            error_codes = {item["code"] for item in result["errors"]}
            warning_codes = {item["code"] for item in result["warnings"]}

            self.assertIn("duplicate_material", error_codes)
            self.assertIn("missing_required_material", error_codes)
            self.assertIn("stage_sequence_conflict", warning_codes)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_run_for_member_reports_identity_conflicts_and_review_items(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                major="计算机科学与技术",
                student_id="2023010001",
            )
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed_with_review",
            )
            text_dir = Path(temp_dir.name) / "texts"
            text_dir.mkdir()
            record = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="思想汇报Q1.docx",
                stored_path="a.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            (text_dir / "file_1.txt").write_text(
                "李四 软件工程 2023010001 思想汇报",
                encoding="utf-8",
            )
            repo.update_material_file(
                record["id"],
                material_type="思想汇报",
                material_stage="activist",
                recognition_source="filename_alias",
                full_text_path=str(text_dir / "file_1.txt"),
                needs_review=1,
            )

            result = MaterialCheckService(repo).run_for_member(member["id"], batch["id"])
            review_codes = {item["code"] for item in result["needs_review"]}

            self.assertIn("identity_conflict", review_codes)
            self.assertIn("unresolved_import_file", review_codes)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
