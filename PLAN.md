# PLAN.md

## WORKING ON — v0.10.79

### 智能日记时间注入
- `inject_memory.py` 从文件名提取日期作为 `created_at`
- 策略：匹配 `YYYY-MM-DD` 格式或者`MM-DD-YYYY`格式 → 日期字符串；匹配不到 → 文件 metadata 创建时间 (mtime)；再匹配不到 → 当前时间
- **为何重要**：当前所有 chunk 的 `created_at` 都是注入时刻。日记文件 `2026-05-14.md` 的 chunk 应该显示为 5月14日创建，不是注入时的 7月某日。这直接影响 WangYou_Decay 的新鲜度计算。

### Dedup 扫描分批
- 当前 2807 条单批嵌入 → Ollama 超时
- 改：每 100 条一批，逐批嵌入 + vec0 搜索


---

## DONE

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
