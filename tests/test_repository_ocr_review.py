from __future__ import annotations

import unittest

from tests.support import make_temp_repo


class RepositoryOCRReviewTests(unittest.TestCase):
    def test_create_tables_adds_ocr_task_table_and_material_file_columns(
        self,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            names = {
                row["name"]
                for row in repo.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("ocr_tasks", names)

            columns = {
                row["name"]
                for row in repo.conn.execute(
                    "PRAGMA table_info(material_files)"
                ).fetchall()
            }
            self.assertIn("ocr_task_id", columns)
            self.assertIn("review_status", columns)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_repository_persists_and_lists_member_ocr_tasks(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            batch = repo.create_material_import_batch(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_path="archive.zip",
                extract_dir="extract",
                status="completed_with_review",
            )
            material_file = repo.add_material_file(
                batch_id=batch["id"],
                member_id=member["id"],
                original_name="申请书扫描件.jpg",
                stored_path="scan.jpg",
                extension=".jpg",
                parser_type="image",
                parse_status="parsed",
            )
            task = repo.create_ocr_task(
                member_id=member["id"],
                batch_id=batch["id"],
                material_file_id=material_file["id"],
                status="review_required",
                raw_segments_json='[{"text":"敬爱的党组织","confidence":0.42}]',
                confidence_summary_json='{"segment_count":1,"low_confidence_count":1}',
            )
            repo.update_material_file(
                material_file["id"],
                ocr_task_id=task["id"],
                review_status="review_required",
            )

            pending = repo.list_member_ocr_tasks(
                member["id"],
                status="review_required",
            )

            self.assertEqual(pending[0]["material_file_id"], material_file["id"])
            self.assertEqual(pending[0]["status"], "review_required")
            self.assertEqual(
                repo.get_ocr_task_by_material_file(material_file["id"])["id"],
                task["id"],
            )
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
