from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_mcp import Database


class SchemaMigrationTests(unittest.TestCase):
    def test_apply_schema_adds_new_columns_to_existing_memories_table(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "legacy.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        namespace TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_file TEXT,
                        content_hash TEXT NOT NULL,
                        metadata_json TEXT,
                        deleted_at TEXT,
                        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            db = Database(db_path)
            try:
                cols = {
                    row[1]
                    for row in db.conn.execute("PRAGMA table_info(memories)").fetchall()
                }
                self.assertIn("last_effective_recall_at", cols)
                self.assertIn("effective_recall_count", cols)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
