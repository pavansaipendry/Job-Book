"""
One-time cleanup: removes ALL SimplifyJobs entries from the database.
Run this ONCE before deploying the new date-filtered SimplifyJobs client.

Usage: python cleanup.py
"""

import sqlite3
import sys


def cleanup_simplifyjobs(db_path: str = "./database/jobs.db"):
    """Remove all SimplifyJobs entries from the database."""
    conn = sqlite3.connect(db_path)

    total_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    simplify_count = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE source = 'SimplifyJobs'"
    ).fetchone()[0]

    print(f"BEFORE cleanup:")
    print(f"  Total jobs:    {total_before}")
    print(f"  SimplifyJobs:  {simplify_count}")
    print(f"  Other sources: {total_before - simplify_count}")

    if simplify_count == 0:
        print("\nNo SimplifyJobs entries found. Nothing to clean.")
        conn.close()
        return

    # Delete
    conn.execute("DELETE FROM jobs WHERE source = 'SimplifyJobs'")
    conn.commit()

    total_after = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    print(f"\n✅ Removed {simplify_count} SimplifyJobs entries")
    print(f"\nAFTER cleanup:")
    print(f"  Total jobs: {total_after}")

    # Source breakdown
    rows = conn.execute(
        "SELECT source, COUNT(*) as c FROM jobs "
        "WHERE (archived = 0 OR archived IS NULL) "
        "GROUP BY source ORDER BY c DESC"
    ).fetchall()
    print(f"\nSource breakdown:")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")

    conn.close()


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "./database/jobs.db"
    print("=" * 50)
    print("SimplifyJobs Cleanup")
    print("=" * 50)
    cleanup_simplifyjobs(db)