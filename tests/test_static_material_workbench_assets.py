from __future__ import annotations

import unittest
from pathlib import Path


class StaticMaterialWorkbenchAssetTests(unittest.TestCase):
    def test_member_material_workbench_markup_and_scripts_exist(self) -> None:
        html = Path("partymate/web/static/index.html").read_text(encoding="utf-8")
        js = Path("partymate/web/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="memberArchiveInput"', html)
        self.assertIn('id="ocrReviewPanel"', html)
        self.assertIn("openMemberArchivePicker(", js)
        self.assertIn("handleMemberArchiveSelected(", js)
        self.assertIn("runMemberMaterialCheck(", js)
        self.assertIn("openOCRReviewTask(", js)
        self.assertIn("confirmOCRReviewTask(", js)
        self.assertIn("/api/materials/archive/import", js)
        self.assertIn("/materials/check", js)
        self.assertIn("/api/ocr/tasks/", js)
        self.assertIn("/api/ocr/confirm", js)


if __name__ == "__main__":
    unittest.main()
