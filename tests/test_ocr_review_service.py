from __future__ import annotations

import unittest
from pathlib import Path

from partymate.services.ocr_review_service import OCRReviewService
from tests.support import make_temp_repo


class OCRReviewServiceTests(unittest.TestCase):
    def test_build_task_detail_loads_raw_text_and_low_confidence_segments(self) -> None:
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
                raw_segments_json=(
                    '[{"text":"敬爱的党组只","confidence":0.42,"bbox":[[0,0],[1,0],[1,1],[0,1]]}]'
                ),
                confidence_summary_json=(
                    '{"segment_count":1,"low_confidence_count":1,"average_confidence":0.42}'
                ),
            )
            repo.update_material_file(
                material_file["id"],
                ocr_task_id=task["id"],
                review_status="review_required",
            )

            detail = OCRReviewService(repo, data_root=Path(temp_dir.name)).build_task_detail(
                task["id"]
            )

            self.assertEqual(detail["raw_text"], "敬爱的党组只")
            self.assertEqual(detail["confidence_summary"]["low_confidence_count"], 1)
            self.assertEqual(len(detail["low_confidence_segments"]), 1)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_confirm_task_persists_confirmed_text_and_updates_states(self) -> None:
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

            service = OCRReviewService(repo, data_root=Path(temp_dir.name))
            updated = service.confirm_task(
                task["id"],
                confirmed_text="敬爱的党组织 张三",
                review_notes="修正了组织二字",
            )

            self.assertEqual(updated["status"], "confirmed")
            self.assertTrue(Path(updated["confirmed_text_path"]).exists())
            self.assertEqual(
                repo.get_material_file(material_file["id"])["review_status"],
                "confirmed",
            )
            self.assertEqual(
                service.resolve_file_text(repo.get_material_file(material_file["id"])),
                "敬爱的党组织 张三",
            )
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
