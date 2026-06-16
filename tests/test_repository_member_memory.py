from __future__ import annotations

import unittest

from tests.support import make_temp_repo


class RepositoryMemberMemoryTests(unittest.TestCase):
    def test_create_tables_adds_member_memories_table(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            names = {
                row["name"]
                for row in repo.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("member_memories", names)
        finally:
            repo.close()
            temp_dir.cleanup()

    def test_repository_creates_lists_updates_and_deletes_member_memories(self) -> None:
        temp_dir, repo = make_temp_repo()
        try:
            member = repo.add_member(name="张三")
            first = repo.create_member_memory(
                member_id=member["id"],
                kind="note",
                title="基本情况",
                content="需要重点跟进培养联系人安排",
                importance=2,
                pinned=0,
                source="manual",
            )
            second = repo.create_member_memory(
                member_id=member["id"],
                kind="risk",
                title="风险提醒",
                content="政审材料需要尽快补齐",
                importance=3,
                pinned=1,
                source="manual",
            )

            active = repo.list_member_memories(member["id"])
            self.assertEqual([item["id"] for item in active], [second["id"], first["id"]])

            updated = repo.update_member_memory(
                first["id"],
                merged_into_id=second["id"],
                pinned=0,
            )
            self.assertEqual(updated["merged_into_id"], second["id"])

            active_after_merge = repo.list_member_memories(member["id"])
            self.assertEqual([item["id"] for item in active_after_merge], [second["id"]])

            with_merged = repo.list_member_memories(member["id"], include_merged=True)
            self.assertEqual(len(with_merged), 2)

            self.assertTrue(repo.delete_member_memory(first["id"]))
            self.assertEqual(repo.get_member_memory(first["id"]), {})
        finally:
            repo.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
