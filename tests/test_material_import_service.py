from __future__ import annotations

import unittest
from pathlib import Path

from partymate.services.material_import_service import MaterialImportService
from tests.support import make_temp_repo, make_zip_bytes


class MaterialImportServiceExtractionTests(unittest.TestCase):
    def test_import_archive_blocks_zip_slip_and_skips_unsupported_files(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三", student_id="2023010001")
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
