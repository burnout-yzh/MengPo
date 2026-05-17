#!/usr/bin/env python3
"""sqlite-vec probe — quick vector search sanity check.

Usage:
    python -m scripts.s1_probe "your query"
"""

from __future__ import annotations

import sys
from pathlib import Path

from memory_mcp.config import Config
from memory_mcp import Database
from memory_mcp.embeddings import EmbeddingError
from memory_mcp.retrieval import S1_vector_search, SEMANTIC_CANDIDATE_LIMIT

DB_PATH = Config.load_cached().storage.db_path


def main() -> None:
    query = " ".join(sys.argv[1:]) or "memory sqlite-vec MengPo"
    print(f"Query: {query}")

    if not Path(DB_PATH).exists():
        print(f"ERROR: no DB at {DB_PATH}. Run python -m scripts.inject_memory first.")
        sys.exit(1)

    db = Database(DB_PATH)
    try:
        try:
            candidates = S1_vector_search(db, query, candidate_limit=SEMANTIC_CANDIDATE_LIMIT)
        except (EmbeddingError, RuntimeError) as exc:
            print(f"ERROR: S1 probe failed ({exc})")
            raise SystemExit(2)
        print(f"Results: {len(candidates)}\n")

        if not candidates:
            return

        print(f"{'Rank':<6}{'Dist':<8}{'Source':<30}Preview")
        print("-" * 85)
        for rk, c in enumerate(candidates[:5], 1):
            preview = c.content[:70].replace("\n", " ")
            dist = 1.0 - c.semantic_score
            src = c.source_file or "-"
            print(f"{rk:<6}{dist:<8.4f}{src:<30}{preview}")

        sem_scores = [c.semantic_score for c in candidates]
        print(f"\nSemantic score range: {min(sem_scores):.4f} - {max(sem_scores):.4f}")
        freshness_vals = [c.freshness_score for c in candidates]
        print(f"Freshness range:     {min(freshness_vals):.4f} - {max(freshness_vals):.4f}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
