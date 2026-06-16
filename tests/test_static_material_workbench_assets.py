from __future__ import annotations

import unittest
from pathlib import Path


class StaticMaterialWorkbenchAssetTests(unittest.TestCase):
    def test_member_material_workbench_markup_and_scripts_exist(self) -> None:
        html = Path("partymate/web/static/index.html").read_text(encoding="utf-8")
        js = Path("partymate/web/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="memberArchiveInput"', html)
        self.assertIn('id="ocrReviewPanel"', html)
        self.assertIn('id="chatMemberContextBar"', html)
        self.assertIn("openMemberArchivePicker(", js)
        self.assertIn("handleMemberArchiveSelected(", js)
        self.assertIn("runMemberMaterialCheck(", js)
        self.assertIn("openOCRReviewTask(", js)
        self.assertIn("confirmOCRReviewTask(", js)
        self.assertIn("bindMemberChatContext(", js)
        self.assertIn("clearChatMemberContext(", js)
        self.assertIn("saveMemberMemory(", js)
        self.assertIn("toggleMemberMemoryPinned(", js)
        self.assertIn("deleteMemberMemory(", js)
        self.assertIn("mergeSelectedMemories(", js)
        self.assertIn("/api/materials/archive/import", js)
        self.assertIn("/materials/check", js)
        self.assertIn("/api/ocr/tasks/", js)
        self.assertIn("/api/ocr/confirm", js)
        self.assertIn("/memories", js)
        self.assertIn("member_id: window._chatMemberId || null", js)


if __name__ == "__main__":
    unittest.main()
