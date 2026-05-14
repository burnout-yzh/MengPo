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
from datetime import datetime
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
            "SELECT content, source_file, timestamp FROM memory_metadata WHERE id = ?",
            (row["rowid"],),
        ).fetchone()
        if meta is None:
            continue
        results.append(
            {
                "content": meta["content"],
                "source_file": meta["source_file"],
                "timestamp": meta["timestamp"],
                "distance": row["distance"],
            }
        )

    conn.close()
    return results


def _rank(candidates: list[dict]) -> list[dict]:
    now = datetime.now()

    for item in candidates:
        try:
            dt = datetime.strptime(item["timestamp"], "%Y-%m-%d")
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


def main() -> None:
    print("MengPo MCP Server starting...")
    print(f"  DB: {CFG.db_path}")
    print(f"  HALF_LIFE_TAU: {CFG.half_life_tau:.4f} days")
    print(f"  Log: {CFG.log_path}")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
