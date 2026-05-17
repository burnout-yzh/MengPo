"""MengPo MCP server entrypoint — thin facade over memory_mcp modules.

All S1–S3 retrieval, write-back, and statistics are delegated to the
underlying Database / retrieval / freshness modules.  No raw sqlite3
connections or independent table definitions live here.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
UTC = timezone.utc
from math import log
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import Config
from .database import Database
from .embeddings import OllamaEmbeddingClient
from .retrieval import (
    FRESHNESS_WEIGHT,
    RESULT_LIMIT,
    RANK_SCORE_EPSILON,
    SEMANTIC_CANDIDATE_LIMIT,
    RetrievalCandidate,
    RankedMemory,
    S1_vector_search,
    Samsara_Rank,
)

# ═══════════════════════════════════════════════════════════════════════
#  Configuration — everything from bowl.yaml, env vars override
# ═══════════════════════════════════════════════════════════════════════

_cfg = Config.load_cached()
_cfg_server = _cfg.server
_cfg_storage = _cfg.storage
_cfg_retrieval = _cfg.retrieval
_cfg_embedding = _cfg.embedding

logging.basicConfig(
    filename=_cfg_storage.log_path,
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
if _cfg_storage.debug_log_to_file:
    _debug_handler = logging.FileHandler(_cfg_storage.debug_log_path, encoding="utf-8")
    _debug_handler.setLevel(logging.DEBUG)
    _debug_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.getLogger().addHandler(_debug_handler)
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("debug log enabled: %s", _cfg_storage.debug_log_path)

mcp = FastMCP(_cfg_server.mcp_name, port=_cfg_server.mcp_port)

# ═══════════════════════════════════════════════════════════════════════
#  Shared state
# ═══════════════════════════════════════════════════════════════════════

_db: Database | None = None
_db_lock = threading.Lock()


import subprocess
import sys
import threading


def _get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database(_cfg_storage.db_path)
                logging.debug("db initialized: %s", _cfg_storage.db_path)
    return _db


# ── First-run injection flag ──────────────────────────────────────────────

_INIT_FLAG = Path(__file__).resolve().parent.parent / ".mengpo_initialized"


def _is_first_run() -> bool:
    """Return True if the DB is empty and the init flag doesn't exist."""
    if _INIT_FLAG.exists():
        return False
    db = _get_db()
    counts = db.row_counts()
    if counts.get("memories", 0) > 0:
        # DB has data but no flag — create the flag and move on
        _INIT_FLAG.write_text("", encoding="utf-8")
        return False
    return True


def _trigger_initial_injection() -> None:
    """Background: run inject_memory.py to populate the vector store."""
    repo_root = _INIT_FLAG.resolve().parent
    inject_script = repo_root / "scripts" / "inject_memory.py"
    if not inject_script.is_file():
        logging.error("First-run inject script not found: %s", inject_script)
        return
    logging.debug("first-run injection triggered: %s", inject_script)

    def _run() -> None:
        try:
            result = subprocess.run(
                [sys.executable, str(inject_script)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logging.info("First-run injection OK (%d chunks)", result.stdout.count("Chunks:"))
            else:
                logging.error("First-run injection FAILED:\n%s", result.stderr)
        except subprocess.TimeoutExpired:
            logging.error("First-run injection timed out after 300s")
        finally:
            _INIT_FLAG.write_text("", encoding="utf-8")

    threading.Thread(target=_run, daemon=True).start()


# Per-session S1 candidate cache for expand tool.
#  Key: session_id.  Value: dict with "ranked" (fully blend-sorted list)
#  and "cursor" (index into ranked for next expand slice).
_session_cache: dict[str, dict] = {}
_MAX_SESSION_CACHE = 1024


def _blend(semantic: float, freshness: float) -> float:
    """Weighted geometric mean — same formula as Samsara_Rank."""
    sem = max(RANK_SCORE_EPSILON, min(1.0, semantic))
    fresh = max(RANK_SCORE_EPSILON, min(1.0, freshness))
    from math import exp as _exp
    return _exp((1.0 - FRESHNESS_WEIGHT) * log(sem) + FRESHNESS_WEIGHT * log(fresh))


# ═══════════════════════════════════════════════════════════════════════
#  MCP Tools
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
def get_relevant_memories(query: str, session_id: str = "") -> str:
    """S1→S2 retrieval pipeline: vector search → freshness re-rank.

    Args:
        query: Natural-language search query.
        session_id: Optional session key to cache S1 results for expand.
    """
    # ── First-run: auto-inject if the database is empty ──
    if _is_first_run():
        _trigger_initial_injection()
        return json.dumps({
            "message": "欢迎使用，首次嵌入可能需要2分钟",
            "results": [],
            "count": 0,
        })

    db = _get_db()

    try:
        candidates = S1_vector_search(
            db,
            query,
            candidate_limit=_cfg_retrieval.candidate_limit,
            embed_client=OllamaEmbeddingClient(
                base_url=_cfg_server.ollama_base_url,
                model=_cfg_embedding.model,
            ),
        )
    except FileNotFoundError:
        return json.dumps({"error": "Memory database not found. Run ingest first."})
    except RuntimeError as exc:
        return json.dumps({"error": f"retrieval failed: {exc}"})

    if not candidates:
        return json.dumps({"results": [], "count": 0})

    # Full blend-sort over all candidates — no truncation so expand can
    # slice the cached result without re-ranking.
    ranked_all = Samsara_Rank(
        candidates,
        candidate_limit=_cfg_retrieval.candidate_limit,
        result_limit=len(candidates),
    )

    # ── Deliver top-N, cache full ranked list for expand ──
    delivery = ranked_all[: _cfg_retrieval.result_limit]

    if session_id:
        _session_cache[session_id] = {
            "ranked": ranked_all,
            "cursor": len(delivery),
        }
        if len(_session_cache) > _MAX_SESSION_CACHE:
            oldest = next(iter(_session_cache))
            if oldest != session_id:
                _session_cache.pop(oldest, None)

    if delivery:
        top = delivery[0]
        logging.info(
            "QUERY=%s | TOP1=%s | SCORE=%.4f",
            query,
            top.source_file or f"mem_{top.memory_id}",
            top.semantic_score,
        )

    output = [
        {
            "memory_id": r.memory_id,
            "source_file": r.source_file,
            "content": r.content[:200],
            "semantic_score": round(r.semantic_score, 4),
            "freshness_score": round(r.freshness_score, 4),
            "final_score": round(_blend(r.semantic_score, r.freshness_score), 4),
        }
        for r in delivery
    ]
    return json.dumps(
        {"query": query, "count": len(output), "results": output},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def Sansheng_Stone(  # 真名: reinforce_memories — S3 写回，刻下缘分锚点
    memory_rowids: list[int],
    shrink_factor: float = 0.368,
) -> str:
    """三生石 (Sansheng_Stone): Report which memories were effective.

    Call this after returning search results to reinforce useful memories.
    The elapsed interval from prior effective recall to 'now' is shrunk
    to shrink_factor (default 1/e=0.368), mimicking biological memory
    reconsolidation.

    To mark a memory as *not* useful, omit it from memory_rowids —
    no change is applied.

    Args:
        memory_rowids: List of memory ids that were useful (max 50).
        shrink_factor: 0.0–1.0, how much to shrink the interval (0.368=1/e).
    """
    if not memory_rowids:
        return json.dumps({"updated": 0, "message": "No memories to reinforce."})
    if len(memory_rowids) > 50:
        return json.dumps({"error": "Max 50 memory_rowids per call."})
    if shrink_factor <= 0 or shrink_factor > 1:
        return json.dumps({"error": "shrink_factor must be in (0, 1]."})

    db = _get_db()
    updated = db.Sansheng_Stone(
        memory_ids=memory_rowids,
        shrink_factor=shrink_factor,
        now=datetime.now(UTC),
    )
    logging.info(
        "SANSHENG_STONE | reinforced=%d | factor=%.3f", updated, shrink_factor
    )
    return json.dumps(
        {
            "updated": updated,
            "message": f"Reinforced {updated} memory anchor(s) on 三生石.",
        }
    )


@mcp.tool()
def expand_retrieval(session_id: str) -> str:
    """Request the next batch of S2-ranked memories for the same session.

    Call this when the LLM has not found useful results in the initial
    delivery and needs more candidates from the cached S1 vector-search
    pool.  Each call returns up to 5 additional memories.  When the pool
    is exhausted the returned list is empty.

    Args:
        session_id: The session key used in a prior get_relevant_memories call.
    """
    if not session_id or session_id not in _session_cache:
        return json.dumps({
            "results": [],
            "count": 0,
            "message": "No session cache. Run get_relevant_memories first with session_id.",
        })

    cached = _session_cache[session_id]
    ranked: list = cached["ranked"]
    cursor: int = cached["cursor"]

    # Direct slice — already blend-sorted, no re-ranking needed.
    batch = ranked[cursor:cursor + _cfg_retrieval.result_limit]
    cached["cursor"] = cursor + len(batch)

    if not batch:
        # All cached candidates exhausted.
        _session_cache.pop(session_id, None)
        return json.dumps({
            "results": [],
            "count": 0,
            "remaining": 0,
            "message": "All cached candidates exhausted. Try a new query.",
        })

    output = [
        {
            "memory_id": r.memory_id,
            "source_file": r.source_file,
            "content": r.content[:200],
            "semantic_score": round(r.semantic_score, 4),
            "freshness_score": round(r.freshness_score, 4),
            "final_score": round(_blend(r.semantic_score, r.freshness_score), 4),
        }
        for r in batch
    ]
    remaining = len(ranked) - cached["cursor"]
    return json.dumps(
        {"count": len(output), "remaining": remaining, "results": output},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_pending_reviews(limit: int = 10) -> str:
    """Return chunks flagged for dedup adjudication.

    Call this after inject_memory reports pending_review > 0.
    The LLM should inspect each chunk's content and the original memory
    it was compared against, then call resolve_dedup_review().

    Args:
        limit: Max number of pending reviews to return (default 10).
    """
    db = _get_db()
    rows = db.get_pending_reviews(limit=limit)
    if not rows:
        return json.dumps({"count": 0, "reviews": []})

    output = []
    for r in rows:
        output.append({
            "memory_id": r["memory_id"],
            "chunk_rowid": r["chunk_rowid"],
            "source_file": r["source_file"],
            "chunk_index": r["chunk_index"],
            "content_preview": (r["chunk_content"] or "")[:300],
            "memory_preview": (r["memory_content"] or "")[:300],
            "created_at": r["created_at"],
        })
    return json.dumps(
        {"count": len(output), "reviews": output},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def resolve_dedup_review(memory_id: int, verdict: str) -> str:
    """Resolve one pending dedup adjudication.

    Args:
        memory_id: The memory_id from get_pending_reviews().
        verdict: ``"duplicate"`` (reject — soft-delete the chunk) or
                 ``"false_positive"`` (keep — clear the pending flag).
    """
    if verdict not in ("duplicate", "false_positive"):
        return json.dumps({"error": "verdict must be 'duplicate' or 'false_positive'"})

    db = _get_db()
    try:
        resolved = db.resolve_pending_review(memory_id, verdict=verdict)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    action = "soft-deleted" if verdict == "duplicate" else "cleared"
    return json.dumps({
        "memory_id": memory_id,
        "verdict": verdict,
        "action": action,
        "resolved": resolved,
    })


@mcp.tool()
def memory_stats() -> str:
    """Return basic statistics about the memory database."""
    try:
        db = _get_db()
    except Exception:
        return json.dumps({"error": "Memory database not found."})

    counts = db.row_counts()
    pending = db.pending_review_count()
    return json.dumps(
        {
            "total_memories": counts.get("memories", 0),
            "total_chunks": counts.get("chunks_meta", 0),
            "vec_chunks": counts.get("chunks_vec", 0),
            "pending_reviews": pending,
        },
        indent=2,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Entrypoint
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    print("MengPo MCP Server starting...")
    print(f"  DB: {_cfg_storage.db_path}")
    print(f"  Log: {_cfg_storage.log_path}")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
