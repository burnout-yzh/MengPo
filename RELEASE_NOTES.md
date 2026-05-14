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

### 8. AI Slop
- The codebase currently exists in a "vibe slop" state — barely struggling to reach minimum viable validation.
- Planned: manual code audit to fix slop artifacts, logic mismatches from original intent, and general code quality.
- The repo is published now to stake a claim; completion follows perfection. Ships now, refines later.

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
