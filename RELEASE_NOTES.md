# MengPo v0.10.73

First public open-source release of MengPo.

## Highlights

- Atomic `store_memory` write boundary across `memories`, `chunks_meta`, and `chunks_vec`.
- Retrieval policy: take semantic top-45 candidates first, then re-rank within that candidate set using WangYou_Decay, and return a fixed 5 results.
- WangYou_Decay freshness re-rank signal.
- S1/S2/S3 retrieval loop helpers and S3 writeback reinforcement.
- Dedup preflight, adjudication branches, and audit event logging.
- Consistency checker and manual QA scripts.

## Integration Status

- sqlite-vec vec0 wiring is validated in integration runs.
- End-to-end path is validated: write -> ingest -> retrieve -> return.
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
