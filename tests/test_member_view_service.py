from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
