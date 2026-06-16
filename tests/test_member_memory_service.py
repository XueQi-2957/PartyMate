from __future__ import annotations

import unittest

from partymate.services.member_memory_service import MemberMemoryService
from tests.support import make_temp_repo


class MemberMemoryServiceTests(unittest.TestCase):
    def test_create_memory_validates_kind_and_content(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            service = MemberMemoryService(repo)

            created = service.create_memory(
                member_id=member["id"],
                kind="instruction",
                title="沟通方式",
                content="优先提醒其提前准备思想汇报。",
                importance=3,
                pinned=True,
                source="manual",
            )

            self.assertEqual(created["kind"], "instruction")
            self.assertEqual(created["importance"], 3)
            self.assertEqual(created["pinned"], 1)

            with self.assertRaises(ValueError):
                service.create_memory(
                    member_id=member["id"],
                    kind="invalid",
                    content="无效类型",
                )

            with self.assertRaises(ValueError):
                service.create_memory(
                    member_id=member["id"],
                    kind="note",
                    content="   ",
                )
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_merge_memories_creates_new_active_memory_and_archives_sources(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            service = MemberMemoryService(repo)
            first = service.create_memory(
                member_id=member["id"],
                kind="risk",
                title="风险1",
                content="材料日期存在前后不一致。",
            )
            second = service.create_memory(
                member_id=member["id"],
                kind="correction",
                title="修订1",
                content="已确认应以支部登记表日期为准。",
            )

            merged = service.merge_memories(
                member_id=member["id"],
                memory_ids=[first["id"], second["id"]],
                kind="summary",
                title="合并结论",
                content="日期冲突已人工确认，以支部登记表日期为准。",
                pinned=True,
                importance=3,
            )

            self.assertEqual(merged["kind"], "summary")
            self.assertEqual(merged["pinned"], 1)
            active = service.list_memories(member["id"])
            self.assertEqual([item["id"] for item in active], [merged["id"]])
            self.assertEqual(
                repo.get_member_memory(first["id"])["merged_into_id"],
                merged["id"],
            )
            self.assertEqual(
                repo.get_member_memory(second["id"])["merged_into_id"],
                merged["id"],
            )
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_build_agent_context_includes_member_facts_and_active_memories(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(
                name="张三",
                major="计算机科学与技术",
                student_id="2023010001",
                notes="重点培养",
            )
            repo.update_member(member["id"], stage="activist")
            service = MemberMemoryService(repo)
            service.create_memory(
                member_id=member["id"],
                kind="instruction",
                title="提醒",
                content="思想汇报需重点关注时政结合部分。",
                pinned=True,
            )
            service.create_memory(
                member_id=member["id"],
                kind="note",
                title="观察",
                content="近期提交材料速度较慢。",
                pinned=False,
            )

            context = service.build_agent_context(member["id"])

            self.assertIn("成员姓名: 张三", context)
            self.assertIn("当前阶段: activist", context)
            self.assertIn("计算机科学与技术", context)
            self.assertIn("思想汇报需重点关注时政结合部分。", context)
            self.assertIn("近期提交材料速度较慢。", context)
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
