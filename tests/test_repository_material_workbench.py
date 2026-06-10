from __future__ import annotations

import unittest

from tests.support import make_temp_repo


class RepositoryMaterialWorkbenchTests(unittest.TestCase):
    def test_create_tables_adds_material_workbench_tables(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            names = {
                row["name"]
                for row in repo.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertTrue(
                {
                    "material_import_batches",
                    "material_files",
                    "member_material_checks",
                }.issubset(names)
            )
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_repository_persists_batch_file_and_check_rows(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="data/material_imports/member_1/batch_1/source/materials.zip",
                extract_dir="data/material_imports/member_1/batch_1/extracted",
                status="processing",
            )
            material_file = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="入党申请书.docx",
                stored_path="data/material_imports/member_1/batch_1/extracted/入党申请书.docx",
                extension=".docx",
                parser_type="docx",
                parse_status="parsed",
            )
            repo.update_material_file(
                material_file["id"],
                material_type="入党申请书",
                material_stage="applicant",
                recognition_source="filename_exact",
                text_excerpt="敬爱的党组织",
                full_text_path="data/material_imports/member_1/batch_1/parsed/file_1.txt",
                page_count=1,
            )
            repo.create_member_material_check(
                member_id=member["id"],
                batch_id=batch["id"],
                status="completed",
                error_count=1,
                warning_count=0,
                review_count=0,
                summary_json='{"errors":[{"code":"missing_required_material"}]}',
            )

            latest_batch = repo.get_latest_material_import_batch(member["id"])
            latest_check = repo.get_latest_material_check(member["id"])
            files = repo.list_material_files(batch["id"])

            self.assertEqual(latest_batch["archive_name"], "materials.zip")
            self.assertEqual(files[0]["material_type"], "入党申请书")
            self.assertEqual(latest_check["error_count"], 1)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
