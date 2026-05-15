# PLAN.md

## WORKING ON — v0.10.79

(empty — v0.10.79 items moved to DONE)



---

## DONE
### 智能日记时间注入 ✅
- `_extract_diary_date()` 从文件名提取日期 + 可选时间（分钟精度）
- 兼容 8 种格式：YYYY-MM-DD / YYYY_MM_DD / YYYYMMDD / MM-DD-YYYY / MMDDYYYY / 带 HHMM 时间
- 单数字月日自动零补（`2026-1-5` → `2026-01-05`）
- 非法日期拒绝（month 13, day 30, year < 2020）
- `created_at` 写入：文件名日期 → 文件 mtime → CURRENT_TIMESTAMP（三级 fallback）
- `store_memory_atomic()` 新增可选 `created_at` 参数，向后兼容
- 22 个测试覆盖（`tests/test_diary_date.py`）

### 去重策略优化 ✅
- 不再重新调用 Ollama `embed_batch()` — 直接从 `chunks_vec` 取已存向量
- `_vec_blob_to_json()` 转换 sqlite-vec BLOB → JSON 用于 MATCH 查询
- JOIN `chunks_meta` + `chunks_vec` 替代 batch-embed 循环
- 8 个测试覆盖（`tests/test_vec_blob.py`）


### v0.10.78 — bowl.yaml + 增量更新 + Dedup 裁决
- bowl.yaml（乾+坤）、content-hash 增量更新、dedup LLM 裁决链路
- batch 嵌入 (`embed_batch`)、`ollama stop` GPU 释放、结构化 log
- chunk 策略改进：min=160, cumulative merge, 句子边界切（93→43 chunks/10KB）
- `EmbeddingReranker`（余弦相似度，默认关闭）
- BENCHMARK.md（145 文件, 2807 chunks, 99.8s）
- 122/122 tests（新增 embed_batch, chunk_text, EmbeddingReranker 测试）

### v0.10.77 — 已知问题清零 + 脚本重写
- v0.10.75 全部 8 个已知问题关闭
- inject_memory.py 重写（新 schema）、bridge/s1_probe/inject_sample 重写
- .gitignore 清理、config.py 移除

### v0.10.76 — 代码审计
- 全量审计 37 文件，11 项发现修复
- server.py 重写为 facade、S1-S2 expand 缓存优化
- S1_vector_search 事务 46→1 + WangYou_Decay 填充
- bge-m3 → qwen3-embedding-0.6b
- 新增 `expand_retrieval` MCP 工具 + 6 S3 测试

---

## 架构现状

```
server.py (MCP facade)
  ├─ get_relevant_memories / expand_retrieval
  ├─ Sansheng_Stone / memory_stats
  └─ get_pending_reviews / resolve_dedup_review

scripts/inject_memory.py  — batch 嵌入 + hash 增量 + dedup 扫描 + log
memory_mcp/               — 18 modules (database/schema/retrieval/...)
```

## 已知限制
- Dedup 扫描大批量嵌入超时（v0.10.79 修）
- `_blend()` 与 Samsara_Rank 公式重复
- 嵌入客户端 URL 硬编码在 S1_vector_search 默认参数
- 第二轮 S1 排除 → 暂不实现

## 缺测试覆盖
- ✅ `embed_batch()` — 11 tests
- ✅ `EmbeddingReranker` — 7 tests
- ✅ `chunk_text()` min_size + cumulative merge — 8 tests
- `inject_memory.py` 整体集成 — 缺（需真实 Ollama）

## Injection Placeholders
- `memory_test_files/AGENTS.md` / `MEMORY.md` / `PROFILE.md` / `SOUL.md`

## TODOs
See `RELEASE_NOTES.zh.md` + `BENCHMARK.md`.
