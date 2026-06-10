from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from partymate.services.material_import_service import MaterialImportService
from tests.support import make_temp_repo, make_zip_bytes


class MaterialImportServiceExtractionTests(unittest.TestCase):
    @patch("partymate.services.material_import_service.parse_file")
    def test_import_archive_blocks_zip_slip_and_skips_unsupported_files(
        self,
        mock_parse,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            mock_parse.return_value = {
                "filename": "入党申请书.docx",
                "type": "docx",
                "text": "敬爱的党组织，我志愿加入中国共产党。",
                "pages": 1,
                "preview": "敬爱的党组织",
                "error": None,
            }
            zip_bytes = make_zip_bytes(
                {
                    "../evil.txt": "blocked",
                    "notes/readme.txt": "skip me",
                    "docs/入党申请书.docx": b"fake-docx",
                }
            )
            service = MaterialImportService(repo=repo, data_root=Path(temp_dir.name))

            result = service.import_archive(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_bytes=zip_bytes,
            )

            stored_names = [item["original_name"] for item in result["files"]]
            self.assertEqual(stored_names, ["入党申请书.docx"])
            self.assertEqual(result["skipped_files"], ["notes/readme.txt"])
            self.assertEqual(result["batch"]["status"], "completed")
            self.assertFalse((Path(temp_dir.name) / "evil.txt").exists())
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()


class MaterialImportServiceClassificationTests(unittest.TestCase):
    @patch("partymate.services.material_import_service.parse_file")
    def test_import_archive_classifies_files_and_persists_text_outputs(
        self,
        mock_parse,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            zip_bytes = make_zip_bytes(
                {
                    "入党申请书.docx": b"fake-docx-a",
                    "思想汇报Q1.docx": b"fake-docx-b",
                }
            )
            mock_parse.side_effect = [
                {
                    "filename": "入党申请书.docx",
                    "type": "docx",
                    "text": "敬爱的党组织，我志愿加入中国共产党。",
                    "pages": 1,
                    "preview": "敬爱的党组织",
                    "error": None,
                },
                {
                    "filename": "思想汇报Q1.docx",
                    "type": "docx",
                    "text": "思想汇报：我在本季度认真学习。",
                    "pages": 1,
                    "preview": "思想汇报",
                    "error": None,
                },
            ]

            service = MaterialImportService(repo=repo, data_root=Path(temp_dir.name))
            result = service.import_archive(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_bytes=zip_bytes,
            )

            files = repo.list_material_files(result["batch"]["id"])
            self.assertEqual(result["batch"]["recognized_files"], 2)
            self.assertEqual(files[0]["material_type"], "入党申请书")
            self.assertEqual(files[1]["material_type"], "思想汇报")
            self.assertTrue(Path(files[0]["full_text_path"]).exists())
            self.assertEqual(files[0]["recognition_source"], "filename_exact")
        finally:
            repo.close()
            temp_dir.cleanup()

    @patch("partymate.services.material_import_service.parse_file")
    def test_import_archive_creates_ocr_review_task_for_low_confidence_image(
        self,
        mock_parse,
    ) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
            zip_bytes = make_zip_bytes({"申请书扫描件.jpg": b"fake-image"})
            mock_parse.return_value = {
                "filename": "申请书扫描件.jpg",
                "type": "image",
                "text": "敬爱的党组只",
                "pages": 1,
                "preview": "敬爱的党组只",
                "ocr_segments": [
                    {
                        "text": "敬爱的党组只",
                        "confidence": 0.42,
                        "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    }
                ],
                "error": None,
            }

            service = MaterialImportService(repo=repo, data_root=Path(temp_dir.name))
            result = service.import_archive(
                member_id=member["id"],
                archive_name="materials.zip",
                archive_bytes=zip_bytes,
            )

            imported_file = result["files"][0]
            self.assertEqual(imported_file["review_status"], "review_required")
            self.assertTrue(imported_file["ocr_task_id"])

            task = repo.get_ocr_task(imported_file["ocr_task_id"])
            self.assertEqual(task["status"], "review_required")
            self.assertIn("敬爱的党组只", task["raw_segments_json"])
            self.assertIn("low_confidence_count", task["confidence_summary_json"])
        finally:
            repo.close()
            temp_dir.cleanup()
