# MengPo (M.E.N.G.P.O.)

**燃尽冗余，方得共鸣。**
*Burn the redundant, find the resonant.*

## Overview

**Memory Evolution & Next-Gen Preference Orchestrator.**

A cognitive metabolism system built on the Model Context Protocol (MCP). By implementing the Ramanujan-Noodle decay constant ($\tau = 24/\sqrt{5}$), MengPo facilitates the evolution from "static archival" to "dynamic resonance."

### Core Principle: The Cognitive Metabolism Pipeline

MengPo transcends conventional CRUD operations. Every memory fragment must undergo a rigorous metabolic cycle:

**Naihe Bridge (Semantic Gating / S1)**: Executes candidate gating via semantic vector similarity, filtering the top 45 relevant memories.

**Samsara Rank (Temporal Reshaping / S2)**: Applies Ramanujan Decay to perform spatio-temporal re-ranking, determining which memories deserve "reincarnation" within the current context.

$$Score = (1 - \text{Distance}) \cdot e^{-\frac{\Delta t}{\tau}}$$

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
- Configurable first-round duoshe injection for new sessions (disabled by default), configured in `memory_mcp/retrieval_service.py` via `enable_duoshe` and `duoshe_root`.

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
python3 -m unittest discover -v
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

## Configuration

Core algorithm parameters (including decay constants, thresholds, etc.) are carried by `bowl.yaml` (The Bowl of MengPo). Developers may fine-tune according to their own cognitive fundamental frequency $R$.

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

## Roadmap

The active roadmap lives in this repository's issue and commit history.

## Project Status

This project is provided as-is. I am not actively maintaining it, though improvements may happen over time. Issues or pull requests may not be reviewed.

Forks, rewrites, and continued development are welcome. If you find this project useful, a star would be appreciated.

## License

This project is licensed under the MIT License. See `LICENSE`.

---

*A thirtieth-anniversary gift to this vivid world*
