# MengPo (M.E.N.G.P.O.)

**燃尽冗余，方得共鸣。**
*Burn the redundant, find the resonant.*

## Quick Start

```bash
git clone https://github.com/burnout-yzh/MengPo.git && cd MengPo
setup.bat                  # auto-install deps (aliyun/tsinghua mirrors)
python -m memory_mcp.server
```

> See `首次使用_first_time_use.md` for Ollama setup and MCP integration.

---

## Overview

**Memory Evolution & Next-Gen Preference Orchestrator.**

A cognitive metabolism system built on the Model Context Protocol (MCP). By implementing the Ramanujan-Noodle decay constant ($\tau = 24/\sqrt{5}$), MengPo facilitates the evolution from "static archival" to "dynamic resonance."

### Core Principle: The Cognitive Metabolism Pipeline

MengPo transcends conventional CRUD operations. Every memory fragment must undergo a rigorous metabolic cycle:

**Naihe Bridge (Semantic Gating / S1)**: Executes candidate gating via semantic vector similarity, filtering the top 45 relevant memories.

**Samsara Rank (Temporal Reshaping / S2)**: Applies Ramanujan Decay to perform spatio-temporal re-ranking, determining which memories deserve "reincarnation" within the current context.

$$\text{S1: 语义门控}\quad R = \text{cosine\_similarity}(q, m)$$
$$\text{S2: 轮回排序}\quad Score = R^{\,(1-w)} \cdot \left(e^{-\Delta t / \tau}\right)^{w}, \quad w = 0.368$$

**Sansheng Stone (Anchor Reinforcement / S3)**: Performs write-back privilege escalation for high-frequency or pivotal anchors, etching the "Karmic Weight" of temporal depth.

**Wang Chuan (The River of Oblivion / Decay)**: All redundant and stale information eventually sinks beneath the current, resting in the eternal silence of the abyss (Nine Abysses).

> "Burn the redundant, find the resonant."

---

## Project Meta

- English README: `README.md`
- License: MIT

## Current Status

Implemented and tested:

- Atomic `store_memory` boundary across `memories`, `chunks_vec`, and `chunks_meta`.
- Soft delete visibility helpers.
- WangYou_Decay (忘忧衰减) freshness scoring as a secondary re-rank signal.
- Safe Markdown directory scanning with symlink guardrails.
- Retrieval JSONL event helpers.
- Ollama embedding client policy: `timeout=10s`, `retry=0`.
- Retrieval ranking policy: semantic top45 candidate gate, freshness re-rank, fixed return limit 5.
- Retrieval round flow helper: strict S2 `{"<memory_id>": 0|1}` protocol validation, session-level expand exclusion, S3-only writeback.
- S3 writeback reinforcement with configurable `shrink_factor` (default `0.368`, i.e. `1/e`).
- Consistency checker for `memories/chunks_meta/chunks_vec` linkage plus utility script `scripts/check_consistency.py`.
- Dedup adjudication policy, pre-store preflight routing, merge-append helper, and dedup audit events.
- Reliability hardening in store path: `scan_memory_dir` root-path fix, `apply_merge_append` bounds validation + concurrency lock, and `Database.transaction` mutex protection.
- Atomic store input guards: embedding type / UTF-8 / JSON pre-validation before persistence.
- Config-driven embedding dimension (`embedding.dim`) with runtime dimension consistency checks in embedding/rerank paths.
- Retrieval observability hardening: telemetry and duoshe reads are best-effort; optional S1 stats logging via `retrieval.log_s1_stats`.
- Debug logging toggles: `storage.debug_log_to_file` and `storage.debug_log_path` are wired in server and `scripts/inject_memory.py`.
- Injection progress logging in `scripts/inject_memory.py`: start marker, per-200-chunk elapsed time, and final totals.
- Script runtime normalization: `inject_sample` / `inject_memory` / `bridge` / `s1_probe` use package-style execution (no `sys.path` injection) with friendlier exception handling.
- Configurable first-round duoshe injection for new sessions (disabled by default): force-syncs the latest persona on a session's first retrieval by injecting prompts from `AGENTS.md`, `MEMORY.md`, `PROFILE.md`, and `SOUL.md`. Configure in `memory_mcp/retrieval_service.py` via `enable_duoshe` and `duoshe_root`.

Validated in integration runs:

- Real `sqlite-vec` vec0 wiring and SQL retrieval are working.
- End-to-end retrieval path (write → ingest → retrieve → return) is working.
- Chunker, dedup adjudication runtime, and LLM callback branch handling are working.

Still to expand:

- Full MCP tool surface integration of current helpers.

Current MCP server note:

- `memory_mcp/server.py` provides a working local MCP entrypoint.
- It has been validated in real qwenpaw integration runs.

## Development

Run tests directly from the repository root:

```bash
python -m pytest -q
```

Run the manual QA script after installing in editable mode:

```bash
python3 -m pip install -e .
python3 scripts/manual_qa.py
python3 scripts/check_consistency.py /path/to/memory.db
```

Without installing the package, use:

```bash
PYTHONPATH=. python3 scripts/manual_qa.py
```

## Configuration — Single Source of Truth

All parameters live in **`bowl.yaml`** (The Bowl of MengPo) at the repository root. The `memory_mcp/config.py` module reads the YAML on startup and feeds typed values to every module.

### Priority Chain

```
environment variable  >  bowl.yaml value  >  code default
```

Set an env var like `MENGPO_DB_PATH` to temporarily override `storage.db_path` without touching the bowl.

### Key Paths in bowl.yaml

```yaml
storage:
  db_path: ./mengpo_memory.db      # SQLite database file
  log_path: ./mcp_access.log       # MCP server access log

injection:
  memory_dir: ./memory              # Markdown diary directory to scan
  batch_size: 15                    # Embedding batch size

server:
  ollama_base_url: http://127.0.0.1:11434
  mcp_port: 18081
  mcp_name: MengPo Memory Server
  rerank_model: qwen3-reranker-0.6b
```

### Deploying on a Different Drive (e.g. E:)

1. Copy the repository to `E:\MengPo\`
2. Edit `bowl.yaml`:

   ```yaml
   storage:
     db_path: E:\MengPo\mengpo_memory.db
   injection:
     memory_dir: E:\MengPo\memory
   ```
3. Run normally — no env vars or code changes needed.

### Full Parameter Reference

| bowl.yaml path | Config attribute | Type | Default |
|---|---|---|---|
| `embedding.model` | `embedding.model` | str | `qwen3-embedding-0.6b` |
| `embedding.dim` | `embedding.dim` | int | 1024 |
| `decay.tau` | `decay.tau` | float | 10.71 |
| `decay.initial_strength` | `decay.initial_strength` | float | 1.0 |
| `decay.floor` | `decay.floor` | float | 0.01 |
| `retrieval.candidate_limit` | `retrieval.candidate_limit` | int | 45 |
| `retrieval.result_limit` | `retrieval.result_limit` | int | 5 |
| `retrieval.freshness_weight` | `retrieval.freshness_weight` | float | 0.368 |
| `sansheng_stone.shrink_factor` | `sansheng_stone.shrink_factor` | float | 0.368 |
| `dedup.threshold` | `dedup.threshold` | float | 0.95 |
| `chunk.size_min` | `chunk.size_min` | int | 160 |
| `chunk.size_max` | `chunk.size_max` | int | 500 |
| `server.ollama_base_url` | `server.ollama_base_url` | str | `http://127.0.0.1:11434` |
| `server.mcp_port` | `server.mcp_port` | int | 18081 |
| `server.mcp_name` | `server.mcp_name` | str | `MengPo Memory Server` |
| `server.rerank_model` | `server.rerank_model` | str | `qwen3-reranker-0.6b` |
| `storage.db_path` | `storage.db_path` | str | `./mengpo_memory.db` |
| `storage.log_path` | `storage.log_path` | str | `./mcp_access.log` |
| `storage.debug_log_to_file` | `storage.debug_log_to_file` | bool | `false` |
| `storage.debug_log_path` | `storage.debug_log_path` | str | `./mcp_debug.log` |
| `injection.memory_dir` | `injection.memory_dir` | str | `./memory` |
| `injection.file_pattern` | `injection.file_pattern` | str | `*.md` |
| `injection.batch_size` | `injection.batch_size` | int | 15 |
| `retrieval.log_s1_stats` | `retrieval.log_s1_stats` | bool | `false` |
| `rebuild.warn_max_files` | `rebuild.warn_max_files` | int | 250000 |
| `rebuild.hard_max_files` | `rebuild.hard_max_files` | int | 500000 |
| `rebuild.warn_max_bytes` | `rebuild.warn_max_bytes` | int | 26843545600 |
| `rebuild.hard_max_bytes` | `rebuild.hard_max_bytes` | int | 53687091200 |

### Backward Compatibility

All old environment variables (`MENGPO_DB_PATH`, `MENGPO_MEMORY_DIR`, `MENGPO_OLLAMA_URL`, etc.) continue to work and **take priority over** `bowl.yaml`.

## Rebuild Scan Limits (T15 precheck)

Before future `.md` corpus rebuild execution, scan precheck limits are defined in:

- `memory_mcp/rebuild_limits.py`

Defaults:

- `warn_max_files = 250000 (WARNING_CHUNKS)`
- `hard_max_files = 500000 (MAX_CHUNKS)`
- `warn_max_bytes = 25 GiB`
- `hard_max_bytes = 50 GiB`

Limit override rule:

- Set any bound to `-1` to mean unlimited capacity for that specific bound.

Related adjustable retrieval gate:

- Top semantic candidate limit is exposed via `candidate_limit` in `memory_mcp/retrieval.py` (`Samsara_Rank` / `Naihe_Bridge`).

## Operations Notes

### Clearing the Database (Keep Schema, Remove Data)

When the DB file is locked by a running MCP server and cannot be deleted, clear tables with SQL:

```bash
python -c "
import sqlite3, sqlite_vec
c=sqlite3.connect('mengpo_memory.db')
c.enable_load_extension(True); sqlite_vec.load(c)
c.execute('DELETE FROM chunks_vec')
c.execute('DELETE FROM chunks_meta')
c.execute('DELETE FROM memories')
c.commit(); c.execute('VACUUM'); c.close()
print('DB cleared')
"
```

> `chunks_vec` is a vec0 virtual table — the `sqlite_vec` extension must be loaded before DELETE. Rebuild the index by re-running `inject_memory.py`.

### v0.10.78 Performance Baseline (Windows + RTX 3070 Laptop 8GB)

| Scenario | Files | Injected | Time | GPU Released |
|------|:--:|------|------|:--:|
| Full rebuild (empty DB) | 145 | 2807 chunks | **99.8s** | ✅ ollama stop |
| Incremental (no changes) | 145 | 0 chunks | **1.9s** | ✅ |
| Single-file incremental (est.) | 1 | ~43 chunks | ~1-2s | ✅ |

Config: `chunk: size_min=160, size_max=500`, `batch_size=15`, `qwen3-embedding-0.6b`. See `BENCHMARK.md` for details.


## Version History

- **v0.12.1** — Manual audit closeout: reliability/safety hardening, config-driven embedding dimension checks, retrieval observability updates, and debug logging controls; test baseline `168 passed, 1 skipped, 7 subtests passed`
- **v0.12.0** — Quick-start experience: `setup.bat` + `requirements.txt` + `首次使用_first_time_use.md` (first-time user guide), dual pip/uv support
- **v0.11.0** — `bowl.yaml` configuration centralization: all parameters migrated from hardcoded defaults/env-vars to YAML-driven
- **v0.10.79** — Dedup reuses pre-computed vectors from `chunks_vec`, no re-embedding
- **v0.10.78** — Full cognitive metabolism pipeline: Naihe_Bridge / Samsara_Rank / Sansheng_Stone / Wang_Chuan
- Earlier releases — Core infrastructure: atomic store, embed, dedup, chunker

## Project Status

This project is provided as-is. I am not actively maintaining it, though improvements may happen over time. Issues or pull requests may not be reviewed.

Forks, rewrites, and continued development are welcome. If you find this project useful, a star would be appreciated.

## License

This project is licensed under the MIT License. See `LICENSE`.

---
