"""Experimental MCP server entrypoint for local retrieval smoke tests.

This module is intentionally isolated from repository-root scripts/config so it
can run from an installed package without sys.path hacks.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import sqlite_vec
from mcp.server.fastmcp import FastMCP

from .embeddings import OllamaEmbeddingClient


@dataclass(frozen=True)
class ServerConfig:
    db_path: str
    log_path: str
    ollama_base_url: str
    ollama_model: str
    half_life_tau: float
    candidate_limit: int
    result_limit: int
    mcp_name: str


def _from_env() -> ServerConfig:
    default_db_path = str(Path.cwd() / "mengpo_memory.db")
    default_log_path = str(Path.cwd() / "mcp_access.log")
    return ServerConfig(
        db_path=os.getenv("MENGPO_DB_PATH", default_db_path),
        log_path=os.getenv("MENGPO_LOG_PATH", default_log_path),
        ollama_base_url=os.getenv("MENGPO_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("MENGPO_OLLAMA_MODEL", "qwen3-embedding-0.6b"),
        half_life_tau=float(os.getenv("MENGPO_HALF_LIFE_TAU", str(24 / math.sqrt(5)))),
        candidate_limit=int(os.getenv("MENGPO_CANDIDATE_LIMIT", "45")),
        result_limit=int(os.getenv("MENGPO_RESULT_LIMIT", "15")),
        mcp_name=os.getenv("MENGPO_MCP_NAME", "MengPo Memory Server"),
    )


CFG = _from_env()

logging.basicConfig(
    filename=CFG.log_path,
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

mcp = FastMCP(CFG.mcp_name, port=18081)


def _ensure_s3_columns(conn: sqlite3.Connection) -> None:
    """Add S3 write-back columns to memory_metadata if they do not exist."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(memory_metadata)").fetchall()
    }
    if "effective_recall_count" not in existing:
        conn.execute(
            "ALTER TABLE memory_metadata ADD COLUMN effective_recall_count "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_effective_recall_at" not in existing:
        conn.execute(
            "ALTER TABLE memory_metadata ADD COLUMN last_effective_recall_at TEXT"
        )


def _s1_search(query: str) -> list[dict]:
    conn = sqlite3.connect(CFG.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.row_factory = sqlite3.Row

    ec = OllamaEmbeddingClient(base_url=CFG.ollama_base_url, model=CFG.ollama_model)
    qv = ec.embed(query)
    qj = json.dumps(qv, separators=(",", ":"))

    rows = conn.execute(
        "SELECT rowid, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (qj, CFG.candidate_limit),
    ).fetchall()

    results = []
    for row in rows:
        meta = conn.execute(
            "SELECT content, source_file, timestamp, last_effective_recall_at, effective_recall_count FROM memory_metadata WHERE id = ?",
            (row["rowid"],),
        ).fetchone()
        if meta is None:
            continue
        results.append(
            {
                "content": meta["content"],
                "source_file": meta["source_file"],
                "timestamp": meta["timestamp"],
                "last_effective_recall_at": meta["last_effective_recall_at"],
                "effective_recall_count": meta["effective_recall_count"],
                "rowid": row["rowid"],
                "distance": row["distance"],
            }
        )

    conn.close()
    return results


def _rank(candidates: list[dict]) -> list[dict]:
    now = datetime.now(UTC).replace(tzinfo=None)

    for item in candidates:
        raw = item.get("last_effective_recall_at") or item["timestamp"]
        try:
            if "T" in raw or " " in raw:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                dt = datetime.strptime(raw, "%Y-%m-%d")
        except (ValueError, TypeError):
            dt = now
        delta_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        decay = math.exp(-delta_days / CFG.half_life_tau)
        sem = 1.0 - item["distance"]
        item["final_score"] = round(sem * decay, 4)
        item["decay_factor"] = round(decay, 4)
        item["delta_days"] = round(delta_days, 1)

    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    seen = set()
    deduped = []
    for item in candidates:
        key = (item["source_file"], item["timestamp"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[: CFG.result_limit]


@mcp.tool()
def get_relevant_memories(query: str) -> str:
    if not os.path.exists(CFG.db_path):
        return json.dumps({"error": "Memory database not found. Run ingest first."})

    candidates = _s1_search(query)
    if not candidates:
        return json.dumps({"results": [], "count": 0})

    ranked = _rank(candidates)
    if ranked:
        top = ranked[0]
        logging.info(
            "QUERY=%s | TOP1=%s | SCORE=%s | DIST=%s",
            query,
            top["source_file"],
            top["final_score"],
            top["distance"],
        )

    output = [
        {
            "rowid": row.get("rowid"),
            "source_file": row["source_file"],
            "timestamp": row["timestamp"],
            "content": row["content"][:200],
            "semantic_score": round(1.0 - row["distance"], 4),
            "decay_factor": row["decay_factor"],
            "final_score": row["final_score"],
            "delta_days": row["delta_days"],
        }
        for row in ranked
    ]
    return json.dumps({"query": query, "count": len(output), "results": output}, ensure_ascii=False, indent=2)


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
        memory_rowids: List of vec_memories rowids that were useful (max 50).
        shrink_factor: 0.0-1.0, how much to shrink the interval (0.368=1/e).
    """
    if not memory_rowids:
        return json.dumps({"updated": 0, "message": "No memories to reinforce."})
    if len(memory_rowids) > 50:
        return json.dumps({"error": "Max 50 memory_rowids per call."})
    if shrink_factor <= 0 or shrink_factor > 1:
        return json.dumps({"error": "shrink_factor must be in (0, 1]."})

    conn = sqlite3.connect(CFG.db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        _ensure_s3_columns(conn)
        now_utc = datetime.now(UTC)

        placeholders = ",".join("?" for _ in memory_rowids)
        rows = conn.execute(
            f"""
            SELECT id, last_effective_recall_at, timestamp AS created_at
              FROM memory_metadata
             WHERE id IN ({placeholders})
            """,
            tuple(memory_rowids),
        ).fetchall()

        updated = 0
        for row in rows:
            base_raw = row["last_effective_recall_at"]
            if base_raw:
                base = datetime.fromisoformat(
                    base_raw.replace("Z", "+00:00")
                ).astimezone(UTC)
            else:
                base = datetime.fromisoformat(
                    row["created_at"].replace("Z", "+00:00")
                ).astimezone(UTC)

            delta = now_utc - base
            if delta.total_seconds() < 0:
                delta = now_utc - now_utc

            reinforced_at = now_utc - (delta * shrink_factor)
            reinforced_iso = reinforced_at.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )

            conn.execute(
                """
                UPDATE memory_metadata
                   SET last_effective_recall_at = ?,
                       effective_recall_count = effective_recall_count + 1
                 WHERE id = ?
                """,
                (reinforced_iso, row["id"]),
            )
            updated += 1

        conn.commit()
        logging.info(
            "SANSHENG_STONE | reinforced=%d | factor=%.3f",
            updated,
            shrink_factor,
        )
        return json.dumps(
            {
                "updated": updated,
                "message": f"Reinforced {updated} memory anchor(s) on 三生石.",
            }
        )
    finally:
        conn.close()


@mcp.tool()
def memory_stats() -> str:
    """Return basic statistics about the memory database."""
    if not os.path.exists(CFG.db_path):
        return json.dumps({"error": "Memory database not found."})

    conn = sqlite3.connect(CFG.db_path)
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    except Exception:
        pass
    try:
        _ensure_s3_columns(conn)
        total = conn.execute("SELECT COUNT(*) FROM memory_metadata").fetchone()[0]
        recalled = conn.execute(
            "SELECT COUNT(*) FROM memory_metadata WHERE effective_recall_count > 0"
        ).fetchone()[0]
        orphaned = conn.execute(
            "SELECT COUNT(*) FROM memory_metadata WHERE id NOT IN "
            "(SELECT rowid FROM vec_memories)"
        ).fetchone()[0]
        sources = conn.execute(
            "SELECT source_file, COUNT(*) AS cnt FROM memory_metadata "
            "GROUP BY source_file ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        return json.dumps(
            {
                "total_chunks": total,
                "recalled_chunks": recalled,
                "orphaned_chunks": orphaned,
                "top_sources": {r[0]: r[1] for r in sources},
            },
            indent=2,
        )
    finally:
        conn.close()


def main() -> None:
    print("MengPo MCP Server starting...")
    print(f"  DB: {CFG.db_path}")
    print(f"  HALF_LIFE_TAU: {CFG.half_life_tau:.4f} days")
    print(f"  Log: {CFG.log_path}")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
