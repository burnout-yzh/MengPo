"""Reproducible fault-matrix runner producing T1 evidence.

Usage:
    python -m tests.run_fault_matrix

Writes a JSON report to stdout and to
``.sisyphus/evidence/task-1-atomic-store.json`` containing per-fault
before/after row counts for the memories/chunks_meta/chunks_vec tables.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from memory_mcp import (
    AtomicStoreError,
    ChunkInput,
    Database,
    FaultPoint,
    store_memory_atomic,
)


def _mk_chunk(i: int) -> ChunkInput:
    return ChunkInput(
        content=f"chunk-{i}",
        embedding=bytes([i % 256]) * 8,
        chunk_index=i,
        paragraph_start=i,
        paragraph_end=i + 1,
    )


def _seed(db: Database) -> None:
    store_memory_atomic(
        db,
        namespace="seed",
        content="pre-existing",
        content_hash="hseed",
        chunks=[_mk_chunk(0), _mk_chunk(1)],
    )


def run() -> dict:
    report: dict = {"happy_path": {}, "fault_injections": []}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "matrix.db"
        db = Database(db_path)
        _seed(db)
        baseline = db.row_counts()

        r = store_memory_atomic(
            db,
            namespace="projects/demo",
            content="happy-path",
            content_hash="hhappy",
            chunks=[_mk_chunk(0), _mk_chunk(1), _mk_chunk(2)],
        )
        report["happy_path"] = {
            "baseline": baseline,
            "after_happy": db.row_counts(),
            "memory_id": r.memory_id,
            "chunk_rowids": list(r.chunk_rowids),
            "delta": {
                k: db.row_counts()[k] - baseline[k] for k in baseline
            },
        }
        post_happy = db.row_counts()
        db.close()

        for fp in FaultPoint:
            db_path = Path(tmp) / f"matrix-{fp.value}.db"
            db = Database(db_path)
            _seed(db)
            before = db.row_counts()
            err: str | None = None
            try:
                store_memory_atomic(
                    db,
                    namespace="abort",
                    content="should-not-land",
                    content_hash="habort",
                    chunks=[_mk_chunk(0), _mk_chunk(1), _mk_chunk(2)],
                    fault=fp,
                )
            except AtomicStoreError as exc:
                err = str(exc)
            after = db.row_counts()
            report["fault_injections"].append({
                "fault_point": fp.value,
                "before": before,
                "after": after,
                "delta": {k: after[k] - before[k] for k in before},
                "error": err,
                "rollback_clean": before == after and err is not None,
            })
            db.close()

    report["all_rollbacks_clean"] = all(
        r["rollback_clean"] for r in report["fault_injections"]
    )
    report["happy_path_delta_matches_chunks"] = (
        report["happy_path"]["delta"]["chunks_meta"] == 3
        and report["happy_path"]["delta"]["chunks_vec"] == 3
        and report["happy_path"]["delta"]["memories"] == 1
    )
    return report


def main() -> int:
    report = run()
    out_dir = Path(".sisyphus/evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "task-1-atomic-store.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = report["all_rollbacks_clean"] and report["happy_path_delta_matches_chunks"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
