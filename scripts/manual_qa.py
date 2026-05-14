from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from memory_mcp import ChunkInput, Database, store_memory_atomic
from memory_mcp.freshness import WangYou_Decay
from memory_mcp.scanner import scan_memory_dir
from memory_mcp.telemetry import append_event, make_event


def chunk(i: int, text: str) -> ChunkInput:
    v = [float(i + 1)] * 1024
    return ChunkInput(content=text, embedding=json.dumps(v, separators=(",", ":")).encode(), chunk_index=i)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        db = Database(root / "qa.db")
        try:
            r1 = store_memory_atomic(db, namespace="demo", content="visible", content_hash="h1", chunks=[chunk(0, "a")])
            r2 = store_memory_atomic(db, namespace="demo", content="deleted", content_hash="h2", chunks=[chunk(1, "b")])
            db.soft_delete_memory(r2.memory_id)

            visible = db.list_memories(namespace="demo")
            recycle = db.list_memories(namespace="demo", include_deleted=True)
            print(f"visible_count={len(visible)} expected=1")
            print(f"recycle_count={len(recycle)} expected=2")
            print(f"visible_top_id={visible[0]['id']} expected={r1.memory_id}")

            docs = root / "docs"
            docs.mkdir()
            (docs / "a.md").write_text("# a\n", encoding="utf-8")
            outside = root / "outside.md"
            outside.write_text("# outside\n", encoding="utf-8")
            try:
                (docs / "link_out.md").symlink_to(outside)
            except OSError:
                pass
            scan = scan_memory_dir(docs)
            print(f"scan_files={len(scan.files)} expected=1")
            print(f"scan_skipped_symlinks={len(scan.skipped_symlinks)} expected>=0")

            now = datetime.now(UTC)
            s0 = WangYou_Decay(now=now, last_effective_recall_at=now)
            s30 = WangYou_Decay(now=now, last_effective_recall_at=now - timedelta(days=30))
            print(f"freshness_now={s0:.6f}")
            print(f"freshness_30d={s30:.6f}")

            event = make_event(
                query="hello",
                namespace="demo",
                memory_id=r1.memory_id,
                semantic_score=0.9,
                WangYou_Decay=0.8,
                rank_before=2,
                rank_after=1,
                s2_effective=True,
                s3_written_back=True,
            )
            log_path = root / "retrieval_events.jsonl"
            append_event(log_path, event)
            print(f"telemetry_lines={len(log_path.read_text(encoding='utf-8').splitlines())} expected=1")
        finally:
            db.close()


if __name__ == "__main__":
    main()
