"""SQLite schema for Memory MCP (T1 scope only).

Design notes
------------
The production vector store is `sqlite-vec` (vec0 virtual table). For T1 we
only need to prove that writes to *memories*, *chunks_meta*, and *chunks_vec*
land atomically within a single SQLite transaction. vec0 participates in
SQLite's transaction machinery identically to a normal table, so we back
`chunks_vec` with a regular table here. When sqlite-vec is wired up in a
later task, only the `CREATE ... chunks_vec` statement changes to:

    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
        USING vec0(embedding FLOAT[1024]);

The transaction-boundary contract (all-or-nothing across the three tables)
does not change.
"""

from __future__ import annotations

# Vector dimension: 1024 (qwen3-embedding-0.6b native dimension).
DEFAULT_EMBEDDING_DIM = 1024

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS memories (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        namespace       TEXT    NOT NULL,
        content         TEXT    NOT NULL,
        source_file     TEXT,
        content_hash    TEXT    NOT NULL,
        metadata_json   TEXT,
        deleted_at      TEXT,
        last_effective_recall_at TEXT,
        effective_recall_count INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_namespace
        ON memories(namespace);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_deleted_at
        ON memories(deleted_at);
    """,
    # chunks_vec: regular table stand-in for sqlite-vec vec0 virtual table.
    # rowid is the join key with chunks_meta, matching vec0 convention.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
        USING vec0(embedding FLOAT[1024]);
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks_meta (
        rowid            INTEGER PRIMARY KEY,
        memory_id        INTEGER NOT NULL,
        namespace        TEXT    NOT NULL,
        chunk_index      INTEGER NOT NULL,
        content          TEXT    NOT NULL,
        source_file      TEXT,
        paragraph_start  INTEGER,
        paragraph_end    INTEGER,
        pending_review   INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chunks_meta_memory_id
        ON chunks_meta(memory_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chunks_meta_namespace
        ON chunks_meta(namespace);
    """,
)


def apply_schema(conn) -> None:
    """Create tables idempotently. Safe to call multiple times."""
    cur = conn.cursor()
    try:
        for stmt in SCHEMA_STATEMENTS:
            cur.execute(stmt)
        columns = {
            row[1]
            for row in cur.execute("PRAGMA table_info(memories)").fetchall()
        }
        if "last_effective_recall_at" not in columns:
            cur.execute(
                "ALTER TABLE memories ADD COLUMN last_effective_recall_at TEXT"
            )
        if "effective_recall_count" not in columns:
            cur.execute(
                "ALTER TABLE memories ADD COLUMN effective_recall_count INTEGER NOT NULL DEFAULT 0"
            )
        # Migration: pending_review in chunks_meta (v0.10.78)
        cm_columns = {
            row[1]
            for row in cur.execute("PRAGMA table_info(chunks_meta)").fetchall()
        }
        if "pending_review" not in cm_columns:
            cur.execute(
                "ALTER TABLE chunks_meta ADD COLUMN pending_review INTEGER NOT NULL DEFAULT 0"
            )
    finally:
        cur.close()
