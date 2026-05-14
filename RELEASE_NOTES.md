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
- All `bge-m3` references removed; unified to `qwen3-embedding-0.6b` (1024 dim).
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

### 1. inject_memory.py — hardcoded year filter + non-recursive scanning
- `glob.glob(os.path.join(MEMORY_DIR, "2026-*.md"))` hardcodes the year 2026 and will break in 2027.
- Non-recursive glob means `memory_test_files/memory/appendix/*` is never scanned.
- **Commitment**: Replace with `glob.glob(os.path.join(MEMORY_DIR, "**/*.md"), recursive=True)`.

### 2. inject_memory.py — non-idempotent full-rescan writes
- Each run re-scans, re-embeds, and INSERTs every file from scratch — no incremental detection.
- No dedup means N runs = N× database bloat; `mengpo_memory.db` grows without bound.
- INSERTs are not idempotent: the same file chunk produces different rowids across injection rounds.
- **Commitment**: Add (source_file, chunk_index) dedup check before insertion; skip if already present.

### 3. server.py `_s1_search()` — hardcoded schema dependency
- The vec0 virtual table query does not auto-adapt when the embedding dimension or table schema changes.
- `MENGPO_DB_PATH` default is hard-bound to `Path.cwd() / "mengpo_memory.db"`.
- **Commitment**: Add up-front schema consistency checks.

### 4. Hardcoded constants without environment variable override
- `CHUNK_SIZE=500` in `inject_memory.py` is not configurable.
- Some hyperparameters derive defaults at module load time, forcing interpreter restarts in unit tests.
- **Commitment**: Add `MENGPO_CHUNK_SIZE` environment variable.

### 5. Bare except
- `inject_memory.py:65` uses bare `except:`, lumping SQLite errors and embedding failures into the same branch.
- **Commitment**: Split into `except sqlite3.Error` and `except EmbeddingError`.

### 6. server.py `memory_stats()` — missing unit test coverage
- This function has zero coverage in the existing test suite.
- **Commitment**: Add `test_server_stats.py`.

### 7. Hardcoded dates
- RELEASE_NOTES contains specific dates that require manual updates on each release and are prone to being missed.
- **Commitment**: Replace date fields with `git tag`-based versioning.

### 8. AI Slop — ✅ resolved in v0.10.76
- ~~The codebase existed in a "vibe slop" state.~~
- ~~Full code audit (37 files) completed, all 11 findings addressed.~~
- ~~server.py facade rewrite, S1_vector_search transaction optimisation, freshness pipeline wired, bge-m3 cleanup.~~

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
