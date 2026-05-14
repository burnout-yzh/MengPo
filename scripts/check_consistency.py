from __future__ import annotations

import argparse

from memory_mcp import Database, run_consistency_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Memory MCP consistency checks")
    parser.add_argument("db_path", help="Path to SQLite database")
    args = parser.parse_args()

    db = Database(args.db_path)
    try:
        report = run_consistency_check(db)
    finally:
        db.close()

    print(f"ok={report.ok}")
    print(f"critical_issues={report.critical_issues}")
    print(f"orphan_meta_count={report.orphan_meta_count}")
    print(f"orphan_vec_count={report.orphan_vec_count}")
    print(f"orphan_memories_count={report.orphan_memories_count}")
    print(f"duplicate_meta_rowid_count={report.duplicate_meta_rowid_count}")
    print(f"duplicate_chunk_index_count={report.duplicate_chunk_index_count}")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
