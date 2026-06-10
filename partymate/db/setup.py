"""PartyMate v2 — database setup & sample data seeding.

Usage:
    uv run python -m partymate.db.setup
"""

from __future__ import annotations

import sys

from partymate.db.repository import Repository
from partymate.services.member_view_service import MemberViewService


def seed_sample_data(repo: Repository) -> None:
    """Insert 3 sample members at different stages with events & materials."""
    # ── Member 1: applicant ────────────────────────────────
    m1 = repo.add_member(
        name="张三",
        gender="男",
        grade="2023级",
        major="计算机科学与技术",
        student_id="2023010001",
        phone="13800001111",
        apply_date="2026-03-01",
        notes="开学递交申请书",
    )
    repo.update_member(m1["id"], notes="重点培养对象")

    # mark applicant materials as submitted
    for mat in repo.get_materials(m1["id"]):
        if mat["material_name"] == "入党申请书":
            repo.submit_material(mat["id"], file_path="archives/张三_2023级_计算机科学与技术/01_入党申请/入党申请书.pdf")

    repo.add_reminder(
        member_id=m1["id"],
        title="安排入党谈话",
        description="张三递交申请书已满25天，请在5天内安排入党谈话",
        due_date="2026-03-26",
        remind_before_days=5,
    )

    # ── Member 2: activist ─────────────────────────────────
    m2 = repo.add_member(
        name="李四",
        gender="女",
        grade="2022级",
        major="软件工程",
        student_id="2022020002",
        phone="13800002222",
        apply_date="2025-09-10",
    )
    repo.update_member(m2["id"], stage="activist", activist_date="2026-01-15")
    repo._auto_generate_events(m2["id"], "activist", "2026-01-15")
    repo._auto_generate_materials(m2["id"], "activist")

    # mark some materials submitted
    mats2 = repo.get_materials(m2["id"])
    for mat in mats2:
        if mat["material_name"] in ("党员推荐入党积极分子登记表", "群团组织推优表"):
            repo.submit_material(mat["id"])

    repo.add_reminder(
        member_id=m2["id"],
        title="收集季度思想汇报",
        description="李四Q2思想汇报到期",
        due_date="2026-06-30",
        remind_before_days=7,
    )

    # ── Member 3: probationary (预备党员) ──────────────────
    m3 = repo.add_member(
        name="王五",
        gender="男",
        grade="2021级",
        major="数据科学与大数据技术",
        student_id="2021030003",
        phone="13800003333",
        apply_date="2024-03-05",
    )
    # Fast-forward through stages
    repo.update_member(
        m3["id"],
        stage="probationary",
        probationary_date="2025-12-20",
        activist_date="2024-06-15",
        candidate_date="2025-06-10",
    )
    repo._auto_generate_events(m3["id"], "probationary", "2025-12-20")
    repo._auto_generate_materials(m3["id"], "probationary")

    mats3 = repo.get_materials(m3["id"])
    for mat in mats3:
        if mat["material_name"] in ("预审请示", "预审批复"):
            repo.submit_material(mat["id"])

    repo.add_reminder(
        member_id=m3["id"],
        title="预备期满提醒",
        description="王五预备期即将满1年，请提醒其准备转正申请",
        due_date="2026-12-20",
        remind_before_days=14,
    )

    print(f"  ✓  张三 (applicant, id={m1['id']})")
    print(f"  ✓  李四 (activist, id={m2['id']})")
    print(f"  ✓  王五 (probationary, id={m3['id']})")


def main() -> None:
    print("PartyMate v2 — Database Setup")
    print("=" * 40)
    print("Creating tables and seeding sample data...\n")

    repo = Repository()
    repo.create_tables()

    # Check if data already exists
    existing = repo.conn.execute("SELECT COUNT(*) AS cnt FROM members").fetchone()
    if existing and existing["cnt"] > 0:
        print(f"  Database already has {existing['cnt']} members. Skipping seed.")
        print("  To re-seed, delete or rename the database file first.")
    else:
        seed_sample_data(repo)

    # Verify
    dash = MemberViewService(repo).build_dashboard()
    stage_counts = {key: value["count"] for key, value in dash["stages"].items()}
    print(f"\nDashboard summary:")
    print(f"  Total members:  {dash['total']}")
    print(f"  Stage counts:   {stage_counts}")
    print(f"\nDB path: {repo.db_path}")

    repo.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
