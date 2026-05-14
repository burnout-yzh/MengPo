# PLAN.md

## v0.10.78 — bowl.yaml + 增量更新 + Dedup 裁决

### bowl.yaml（孟婆汤碗）
集中式 YAML 配置，乾（算法超参）+ 坤（运维参数），所有参数附建议区间注释。

### 增量更新 — content hash 比对
- SHA256 content hash 比对：同 hash 跳过，不同 hash → 软删旧版 + 插入新版
- `updated` 输出计数

### Dedup LLM 裁决链路
- `pending_review` 字段 + 自动迁移
- 注入后向量扫描 → 标记待裁决
- MCP 工具：`get_pending_reviews()` + `resolve_dedup_review()`

### Batch 嵌入 + GPU 释放
- `embed_batch()` 批量嵌入，15/batch
- `ollama stop` 自动释放 GPU
- 结构化 log（`inject.log`），50 chunk 进度打点

### Chunk 策略改进
- min_size: 80→160, max_size: 500
- 短段累积合并 + 句子边界优先切
- 93→43 chunks (10KB 文件)

---

## v0.10.75 已知问题 — 全部关闭

| # | 问题 | 修复版本 |
|---|------|:--:|
| 1 | inject_memory 硬编码年份 + 非递归 | 0.10.77 |
| 2 | inject_memory 非幂等写入 | 0.10.77 |
| 3 | server.py 硬编码 schema | 0.10.76 |
| 4 | CHUNK_SIZE 不可配 | 0.10.77 |
| 5 | Bare except | 0.10.77 |
| 6 | memory_stats() 缺测试 | 0.10.76 |
| 7 | 日期硬编码 | 0.10.76 |
| 8 | AI slop | 0.10.76 |

---

## v0.10.76 — 代码审计

| # | 发现 | 修复 |
|---|------|------|
| 1 | server.py 独立表 `memory_metadata`+`vec_memories` | 重写为 facade |
| 2 | server.py `result_limit=15` | 统一 `RESULT_LIMIT=5` |
| 3 | server.py `_rank()` 直接乘积 | 废弃，用 `Samsara_Rank` |
| 4 | embeddings/schema 中嵌入模型名 | 统一 `qwen3-embedding-0.6b` |
| 5 | S1_vector_search 每行一个事务 | 1 个事务 + 批量 JOIN |
| 6 | __init__.py docstring 过时 | 更新 |
| 7 | freshness_score 永远 0.0 | 补 WangYou_Decay 填充 |
| 8 | pyproject.toml 版本 0.10.74 | 0.10.76, authors=pawpaw |
| 9 | LICENSE vs pyproject 署名不一致 | 统一 pawpaw |
| 11 | 夺舍 duoshe_root | 保留，默认关闭 |

新增：`expand_retrieval` MCP 工具 + S3 写回测试 (6 cases)

---

## 架构现状

```
server.py (MCP facade)
  ├─ get_relevant_memories → S1_vector_search + Samsara_Rank (全量 blend 缓存)
  ├─ expand_retrieval → 排序缓存切片 [cursor:cursor+5]
  ├─ Sansheng_Stone → db.Sansheng_Stone()
  ├─ memory_stats → db.row_counts()
  ├─ get_pending_reviews + resolve_dedup_review → dedup 裁决

scripts/
  inject_memory.py    — batch 嵌入 + content-hash 增量 + dedup 扫描 + log
  bridge.py           — S1→S2 冒烟测试
  s1_probe.py         — vec0 探针
  inject_sample.py    — demo 样本注入

底层模块 (memory_mcp/)
  database / schema / retrieval / freshness / atomic_store /
  store_flow / dedup / consistency / scanner / embeddings / reranker
```

## 已知限制

- Dedup 扫描大批量嵌入超时 → 需分页
- `_blend()` 与 Samsara_Rank 公式重复 → 统一导出
- 第二轮 S1 排除 → 暂不实现
- 嵌入客户端 URL 硬编码在 S1_vector_search 默认参数

---

## Injection Placeholders

- `memory_test_files/AGENTS.md`
- `memory_test_files/MEMORY.md`
- `memory_test_files/PROFILE.md`
- `memory_test_files/SOUL.md`

## TODOs

See `RELEASE_NOTES.zh.md` + `BENCHMARK.md`.
