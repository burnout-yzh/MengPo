# MengPo v0.12.0

## Quick-Start Experience: `setup.bat` + `requirements.txt` + First-Time User Guide

MengPo is now **zero-friction to clone and run**. No more hunting for which pip packages to install.

### New files
- **`setup.bat`** — One-click environment bootstrap. Auto-detects Python 3.10+,
  probes Aliyun / Tsinghua / PyPI mirrors (China-friendly), installs
  `requirements.txt`, and verifies MengPo imports.  Also works with `uv sync`.
- **`requirements.txt`** — Minimal dependency declaration: `mcp>=1.0`,
  `sqlite-vec==0.1.9`, `pyyaml>=6.0`.
- **`首次使用_first_time_use.md`** — Complete first-time user guide (Chinese).
  Covers: prerequisites, three-step start, optional Ollama installation
  (PowerShell one-liners), "first-run self-expansion" explanation, MCP
  configuration for QwenPaw Desktop and Claude Desktop, and FAQ.

### README bilingual refresh
- Both `README.md` and `README.zh.md` now open with a Quick Start section.
- Added **Version History** table covering v0.10.78 → v0.12.0.

### Design rationale
- **Strategy A (requirements.txt + pip)** and **Strategy B (uv sync)** are
  both supported — user picks their preferred tool.
- `setup.bat` is idempotent: safe to re-run after updates.
- Offline-friendly: once dependencies are cached by pip/uv, no network needed.

### No code changes
- `pyproject.toml`: version bumped to `0.12.0`.
- `memory_mcp/` — unchanged.

---

# MengPo v0.11.0

## bowl.yaml — Now the Single Source of Truth

`config.py` reads all parameters from `bowl.yaml`. Every parameter defined in the bowl is now wired to the code. Priority chain: **environment variable > bowl.yaml > code default**.

### New module: `memory_mcp/config.py`
- `Config` class with 10 nested config groups (embedding, decay, retrieval, sansheng_stone, dedup, chunk, server, storage, injection, rebuild).
- `Config.load()` — loads `bowl.yaml`, applies env var overrides.
- `Config.load_cached()` — singleton cache for repeated calls.
- `Config._find_bowl_yaml()` — auto-discovers `bowl.yaml` from CWD or repo root.
- `Config._apply_env_overrides()` — env vars supersede YAML values when set.

### First-Run Auto-Injection
`get_relevant_memories` now detects an empty database on first call, spawns
`inject_memory.py` in a background thread, and returns a friendly welcome
message: *"欢迎使用，首次嵌入可能需要2分钟"*.  A `.mengpo_initialized` flag
prevents repeated injection.

### Modules migrated from hardcoded defaults to Config:

| Module | Before | After |
|--------|--------|-------|
| `retrieval.py` | `SEMANTIC_CANDIDATE_LIMIT = 45` (hardcoded) | `Config.load_cached().retrieval.candidate_limit` |
| `retrieval.py` | `RESULT_LIMIT = 5` (hardcoded) | `Config.load_cached().retrieval.result_limit` |
| `retrieval.py` | `FRESHNESS_WEIGHT = 0.368` (hardcoded) | `Config.load_cached().retrieval.freshness_weight` |
| `freshness.py` | `FreshnessParams(half_life_days=7.0)` (hardcoded!) | `FreshnessParams.from_config()` → `decay.tau=10.71` |
| `dedup.py` | `DEFAULT_DEDUP_THRESHOLD = 0.95` (hardcoded) | `Config.load_cached().dedup.threshold` |
| `reranker.py` | `DEFAULT_RERANK_MODEL = "qwen3-reranker-0.6b:latest"` (hardcoded) | `Config.load_cached().server.rerank_model` |
| `rebuild_limits.py` | `DEFAULT_WARN_MAX_FILES = 250_000` etc. (hardcoded) | `Config.load_cached().rebuild.*` |
| `server.py` | `_from_env()` + local `ServerConfig` dataclass | `Config.load_cached()` throughout, 8 call sites updated |
| `inject_memory.py` | 7 `os.getenv("MENGPO_*")` defaults | `Config.load()` → `cfg.injection.memory_dir` |
| `scripts/bridge.py` | `os.getenv("MENGPO_DB_PATH", ...)` | `Config.load_cached().storage.db_path` |
| `scripts/s1_probe.py` | `os.getenv("MENGPO_DB_PATH", ...)` | `Config.load_cached().storage.db_path` |
| `scripts/inject_sample.py` | 3 `os.getenv("MENGPO_*")` defaults | `Config.load_cached().*` |

### Bug fixed: `decay.tau` mismatch
`FreshnessParams.half_life_days` was hardcoded to **7.0 days**, while `bowl.yaml` specifies `decay.tau: 10.71` (the correct 84-day-data-derived value). Now `FreshnessParams.from_config()` reads `decay.tau=10.71` from the bowl. **This was an active bug** — the code and the bowl were out of sync since v0.10.78.

### New tests: `test_config.py` (17 tests)
Covers: default values, `bowl.yaml` loading, missing file fallback, 7 env var override scenarios, empty env no-op, singleton cache, equality, dingzhen health check.

### Dependency
`pyyaml>=6.0` added to `pyproject.toml`.

### Upgrade notes
- No manual migration needed. Old env vars (`MENGPO_DB_PATH`, `MENGPO_MEMORY_DIR`, etc.) continue to work with higher priority than `bowl.yaml`.
- For E-drive deployment, simply edit `bowl.yaml`'s `injection.memory_dir` and `storage.db_path` instead of setting env vars.

---

# MengPo v0.10.79

## Smart Diary Date Injection
`_extract_diary_date()` extracts the original creation date from diary filenames.

- 8 date formats supported: `YYYY-MM-DD`, `YYYY_MM_DD`, `YYYYMMDD`, `MM-DD-YYYY`, `MMDDYYYY`
- Optional HHMM time extraction (minute precision, e.g. `2026-03-19-0820.md` → `2026-03-19T08:20`)
- Single-digit month/day auto zero-padded (`2026-1-5` → `2026-01-05`)
- Three-tier fallback: filename date → file mtime → CURRENT_TIMESTAMP
- `store_memory_atomic()` now accepts optional `created_at` parameter (backward compatible)
- 22 tests (`tests/test_diary_date.py`)

**Why it matters:** Without this, all 145 diary files injected during migration would have the same `created_at`, collapsing WangYou_Decay freshness scoring.

## Dedup Strategy — Zero Ollama Re-embedding
The dedup similarity scan no longer re-embeds chunks via `embed_batch()`.

- Vectors already stored in `chunks_vec` during injection → reused directly
- `_vec_blob_to_json()` converts sqlite-vec BLOB format to JSON for MATCH queries
- SQL JOIN `chunks_meta` + `chunks_vec` replaces the batch-embed loop
- 8 tests (`tests/test_vec_blob.py`)

## Test Suite
- 152 tests, all passing (130 existing + 22 new)

---

# MengPo v0.10.78

## bowl.yaml — the MengPo Bowl
Centralised YAML config: 乾 (algorithm hyperparams) + 坤 (ops). All params with human-readable comments and suggested ranges.

## Chunk Strategy Improvements
- `size_min`: 80→160, `size_max`: 500. Short paragraphs accumulate to min before emission; long paragraphs split at sentence boundaries (。！？).
- Hard boundaries (hr, code fence) flush the buffer.
- Result: 10KB diary from 93 chunks → 43 (-54%), avg 245 chars.

## Batch Embedding + GPU Release
- `OllamaEmbeddingClient.embed_batch()` — embed multiple texts in one API call.
- `inject_memory.py` defaults to 15/batch. Measured: 145 files, 2807 chunks, full rebuild **99.8s** (vs ~8 min sequential).
- `ollama stop` auto-releases GPU after injection.
- Structured log (`inject.log`) with 50-chunk progress timestamps.

## Incremental Update — content-hash comparison
- SHA256 content-hash comparison: same hash → skip, different → soft-delete old + insert new.
- 145 files unchanged: **1.9s** all skipped.

## Dedup LLM Adjudication Pipeline
- `chunks_meta.pending_review` + auto-migration.
- Batch vector similarity scan after injection → flag for review.
- MCP tools: `get_pending_reviews()` + `resolve_dedup_review()`.
- `memory_stats()` includes `pending_reviews` count.

## Reranker Reserved
- `EmbeddingReranker` (cosine similarity), default off. S1+S2 sufficient.
- `rerank_model` field reserved for future cross-encoder integration.

## Performance Benchmark
- `BENCHMARK.md` with full perf data (145 files, 2807 chunks, 99.8s).
- README ops notes: DB clear command + perf baseline table.

## Tests
- 122/122 tests. New: `embed_batch`(11), `chunk_text`(8), `EmbeddingReranker`(7).

## Known Limitations
- Dedup scan batch timeout → paginated in v0.10.79.
- `_blend()` duplicates Samsara_Rank formula.
- Smart diary time injection → v0.10.79.

---

# MengPo v0.10.77

## v0.10.75 Known Issues — All Resolved

All 8 issues closed. See v0.10.75 entries below for details.

### inject_memory.py Rewrite (new schema + 4 fixes)
- **Old**: operated on `memory_metadata` + `vec_memories` (scaffolding schema), with hardcoded `"2026-*.md"`, bare except, non-configurable `CHUNK_SIZE`, and no dedup.
- **New**: uses `memory_mcp` module APIs (`store_memory_atomic` + `Database`) against `memories` + `chunks_meta` + `chunks_vec`:
  - Recursive scan via `rglob("*.md")`
  - `_chunk_already_stored()` dedup on (source_file, chunk_index)
  - `CHUNK_SIZE` configurable via `MENGPO_CHUNK_SIZE` env var
  - Specific exception branches: `EmbeddingError` / `OSError` / `Exception`

### Script Rewrites
- `scripts/bridge.py` — S1→S2 smoke test, using `S1_vector_search` + `Samsara_Rank`
- `scripts/s1_probe.py` — vec0 probe, using `S1_vector_search`
- `scripts/inject_sample.py` — sample data injection (demo), writes `tests/sample_data/*.md`
- `config.py` removed — constants now live in `memory_mcp` modules

### .gitignore Cleanup
- Removed erroneous exclusions for `inject_memory.py`, `bridge.py`, `s1_probe.py` (no sensitive data)
- Kept `patch_mengpo_vec.py` (one-shot migration, archived)

## Known Limitations

None. All v0.10.75 known issues are closed; incremental content-hash update is implemented.

---

# MengPo v0.10.76

## Code Audit & Refactoring

Full codebase audit (37 files, 18 `.py` source files), 11 findings addressed. 85/85 tests pass.

### server.py Rewrite
- **Before**: `server.py` operated on its own `memory_metadata` + `vec_memories` tables, opening raw `sqlite3` connections, containing a complete self-contained retrieval/ranking/write-back pipeline (~300 lines of scaffolding).
- **After**: Thin facade delegating entirely to `memory_mcp` modules:
  - `get_relevant_memories` → `S1_vector_search` + `Samsara_Rank`
  - `Sansheng_Stone` → `db.Sansheng_Stone()`
  - `memory_stats` → `db.row_counts()`
- Removed all scaffolding: `_s1_search()`, `_rank()`, `_ensure_s3_columns()`.

### S1-S2-Expand Cache Optimisation
- **Samsara_Rank** now blend-sorts all 45 S1 candidates (weighted geometric mean) and the full ranked list is cached in-memory.
- `get_relevant_memories` delivers the top 5 from the cached ranked list.
- `expand_retrieval` slices `[cursor:cursor+5]` directly from the cache — **no re-ranking**, delivering results in strict blend-ranked order.
- Supports up to 8 expand calls (45÷5=9 batches); returns exhausted when depleted.

### S1_vector_search Fixes
- **Transaction optimisation**: 46 transactions (1 vec search + 45 per-row lookups) → 1 transaction (1 vec search + 1 batch IN-JOIN).
- **Freshness wired in**: `WangYou_Decay` now populates `freshness_score` between S1 and S2 (was always 0.0). Falls back to `created_at` when `last_effective_recall_at` is NULL.

### Embedding Model Unification
- Embedding model unified to `qwen3-embedding-0.6b` (1024 dim). Users may configure `bge-m3` or other compatible models via environment variables.
- Affected files: `embeddings.py`, `schema.py`.

### Docs & Attribution
- `__init__.py` docstring updated to reflect the full MCP toolkit surface.
- `pyproject.toml` version 0.10.74 → 0.10.76, authors unified to `pawpaw`.
- `LICENSE` and `pyproject.toml` attribution aligned.

### New `expand_retrieval` MCP Tool
- `expand_retrieval(session_id)` — LLM can request additional memories on demand, up to 5 per call.
- Session-level cache: `get_relevant_memories` must be called with `session_id` first.
- Returns `remaining` count so the LLM can gauge how many more are available.

### New S3 Write-Back Tests
- 6 test cases covering `Sansheng_Stone`: happy path, non-existent IDs silently ignored, empty input noop, `shrink_factor` validation, time-anchor formula verification, soft-deleted memory skip.

## Known Limitations (Deferred)
- **Second-round S1 exclusion**: When expand exhausts all 45 cached candidates, a second S1 round excluding already-delivered IDs is theoretically possible. In practice, an LLM failing to find useful hits after flipping through 45 results is extremely unlikely. Deferred — file an issue if needed.

---

# MengPo v0.10.75

## Known Issues

The following issues are acknowledged in this release and will be addressed in subsequent versions:

### 1. inject_memory.py — hardcoded year filter + non-recursive scanning — ✅ resolved in v0.10.77
- ~~Replaced `glob("2026-*.md")` with `rglob("*.md")` across all subdirectories.~~

### 2. inject_memory.py — non-idempotent full-rescan writes — ✅ resolved in v0.10.77
- ~~`_chunk_already_stored()` checks (source_file, chunk_index) before insertion.~~
- ~~Incremental content-hash update deferred to v0.10.78.~~

### 3. server.py `_s1_search()` — hardcoded schema dependency — ✅ resolved in v0.10.76
- ~~server.py rewritten as facade; no raw sqlite3 or hardcoded table names remain.~~

### 4. Hardcoded constants without environment variable override — ✅ resolved in v0.10.77
- ~~`CHUNK_SIZE` now configurable via `MENGPO_CHUNK_SIZE` env var (default 500).~~

### 5. Bare except — ✅ resolved in v0.10.77
- ~~`inject_memory.py` rewritten with specific `except EmbeddingError` / `except OSError` / `except Exception` branches.~~

### 6. server.py `memory_stats()` — missing unit test coverage — ✅ resolved in v0.10.76
- ~~`memory_stats()` delegates to `db.row_counts()`, which receives indirect test coverage.~~

### 7. Hardcoded dates — ✅ resolved in v0.10.76
- ~~Release notes now use version numbers instead of date fields.~~

### 8. AI Slop — ✅ resolved in v0.10.76~~
- ~~The codebase existed in a "vibe slop" state.~~
- ~~Full code audit (37 files) completed, all 11 findings addressed.~~
- ~~server.py facade rewrite, S1_vector_search transaction optimisation, freshness pipeline wired.~~

## Notes

- This is a public release snapshot, provided as-is.
- Known issues are clearly documented and will be addressed in subsequent versions.

---

# MengPo v0.10.74

## Fixes

- **S3 write-back (Sansheng_Stone) now actually affects ranking** — `_rank()` previously computed freshness exclusively from creation timestamp, ignoring `last_effective_recall_at` written by Sansheng_Stone. The field was persisted to DB but had zero effect on search results. Now `_rank()` prefers `last_effective_recall_at` when available.
- `get_relevant_memories` output now includes `rowid` field, enabling Sansheng_Stone to target specific chunks.
- Fixed `tuple indices must be integers, not str` crash in Sansheng_Stone (missing `conn.row_factory`).
- Fixed naive/aware datetime crash when querying after Sansheng_Stone write-back.
- `memory_stats()` now loads `sqlite_vec` extension (was missing vec0 module import).

## Migration

- S3 columns (`effective_recall_count`, `last_effective_recall_at`) are auto-created on first Sansheng_Stone call — no manual DDL needed.

## Highlights

- Atomic `store_memory` write boundary across `memories`, `chunks_meta`, and `chunks_vec`.
- Retrieval policy: take semantic top-45 candidates first, then re-rank within that candidate set using WangYou_Decay, and return a fixed 5 results.
- WangYou_Decay freshness re-rank signal.
- S1/S2/S3 retrieval loop helpers and S3 writeback reinforcement.
- Dedup preflight, adjudication branches, and audit event logging.
- Consistency checker and manual QA scripts.

## Integration Status

- sqlite-vec vec0 wiring is validated in integration runs.
- End-to-end path is validated: write → ingest → retrieve → return.
- Chunker + dedup adjudication runtime + LLM callback branch handling are validated.

## Notes

- This is a public release snapshot and is provided as-is.
- This version is released as-is; any further expansion is expected to come mainly from community forks or downstream implementations.

## Install

```bash
pip install mengpo
```

For MCP server runtime dependencies:

```bash
pip install mengpo[server]
```

## Verify

```bash
python3 -m unittest discover -v
python3 scripts/manual_qa.py
```

---

# MengPo v0.10.73

First public open-source release of MengPo.
