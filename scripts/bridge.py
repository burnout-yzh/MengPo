#!/usr/bin/env python3
"""Naihe_Bridge + Samsara_Rank — S1→S2 end-to-end smoke test.

Usage:
    python scripts/bridge.py "your query"
    python -m scripts.bridge "your query"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_mcp.config import Config
from memory_mcp import Database
from memory_mcp.retrieval import (
    S1_vector_search,
    Samsara_Rank,
    SEMANTIC_CANDIDATE_LIMIT,
    RESULT_LIMIT,
    FRESHNESS_WEIGHT,
)

DB_PATH = Config.load_cached().storage.db_path


def main() -> None:
    query = " ".join(sys.argv[1:]) or "memory sqlite-vec MengPo"
    print(f"Query: {query}")
    print(f"DB:    {DB_PATH}\n")

    if not Path(DB_PATH).exists():
        print(f"ERROR: database not found at {DB_PATH}")
        sys.exit(1)

    db = Database(DB_PATH)
    try:
        # ── S1: vector search ──
        candidates = S1_vector_search(db, query, candidate_limit=SEMANTIC_CANDIDATE_LIMIT)
        if not candidates:
            print("S1: no candidates found.")
            return

        print(f"S1: {len(candidates)} candidates")
        print(f"    sim range: {min(c.semantic_score for c in candidates):.4f} - "
              f"{max(c.semantic_score for c in candidates):.4f}")
        print(f"    freshness range: {min(c.freshness_score for c in candidates):.4f} - "
              f"{max(c.freshness_score for c in candidates):.4f}")

        # ── S2: blend re-rank ──
        ranked = Samsara_Rank(
            candidates,
            candidate_limit=SEMANTIC_CANDIDATE_LIMIT,
            result_limit=RESULT_LIMIT,
        )
        print(f"\nS2: {len(ranked)} results (blend ranked, top {RESULT_LIMIT})")
        print(f"{'#':<4}{'mem_id':<8}{'semantic':<10}{'freshness':<10}{'source_file':<30}content")
        print("-" * 90)
        for i, r in enumerate(ranked, 1):
            preview = r.content[:60].replace("\n", " ")
            print(f"{i:<4}{r.memory_id:<8}{r.semantic_score:<10.4f}{r.freshness_score:<10.4f}"
                  f"{r.source_file or '-':<30}{preview}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
