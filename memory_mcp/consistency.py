"""T14 consistency checks for memory/chunk linkage integrity."""

from __future__ import annotations

from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True)
class ConsistencyReport:
    orphan_meta_count: int
    orphan_vec_count: int
    orphan_memories_count: int
    duplicate_meta_rowid_count: int
    duplicate_chunk_index_count: int

    @property
    def critical_issues(self) -> int:
        return (
            self.orphan_meta_count
            + self.orphan_vec_count
            + self.orphan_memories_count
            + self.duplicate_meta_rowid_count
            + self.duplicate_chunk_index_count
        )

    @property
    def ok(self) -> bool:
        return self.critical_issues == 0


def run_consistency_check(db: Database) -> ConsistencyReport:
    """Return integrity report across memories/chunks_meta/chunks_vec."""
    cur = db.conn.cursor()
    try:
        orphan_meta_count = cur.execute(
            """
            SELECT COUNT(*)
              FROM chunks_meta m
              LEFT JOIN chunks_vec v ON v.rowid = m.rowid
             WHERE v.rowid IS NULL
            """
        ).fetchone()[0]

        orphan_vec_count = cur.execute(
            """
            SELECT COUNT(*)
              FROM chunks_vec v
              LEFT JOIN chunks_meta m ON m.rowid = v.rowid
             WHERE m.rowid IS NULL
            """
        ).fetchone()[0]

        orphan_memories_count = cur.execute(
            """
            SELECT COUNT(*)
              FROM memories mem
             WHERE mem.deleted_at IS NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM chunks_meta m
                     WHERE m.memory_id = mem.id
               )
            """
        ).fetchone()[0]

        duplicate_meta_rowid_count = cur.execute(
            """
            SELECT COUNT(*)
              FROM (
                    SELECT rowid
                      FROM chunks_meta
                  GROUP BY rowid
               HAVING COUNT(*) > 1
               ) d
            """
        ).fetchone()[0]

        duplicate_chunk_index_count = cur.execute(
            """
            SELECT COUNT(*)
              FROM (
                    SELECT memory_id, chunk_index
                      FROM chunks_meta
                  GROUP BY memory_id, chunk_index
                    HAVING COUNT(*) > 1
              ) d
            """
        ).fetchone()[0]
    finally:
        cur.close()

    return ConsistencyReport(
        orphan_meta_count=orphan_meta_count,
        orphan_vec_count=orphan_vec_count,
        orphan_memories_count=orphan_memories_count,
        duplicate_meta_rowid_count=duplicate_meta_rowid_count,
        duplicate_chunk_index_count=duplicate_chunk_index_count,
    )
