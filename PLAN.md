# PLAN.md

## WORKING ON

(empty — see RELEASE_NOTES.zh.md)

---

## DONE

### v0.12.1 — 人工审计收尾与稳健性增强 ✅
- 审计收尾：`scanner/store_flow/atomic_store/database/schema/retrieval*/embeddings/reranker/freshness/dedup*/consistency` 与 `scripts/*` 全链路巡检并落修
- 安全与稳定：修复 `scan_memory_dir` 根路径 bug；`apply_merge_append` 增加越界校验与并发锁；`Database.transaction` 增加互斥
- 原子存储前置校验：embedding 类型 / UTF-8 / JSON 验证后再落库
- 配置一致性：向量维度改为 `embedding.dim` 配置驱动，并在 embedding/rerank 路径增加维度一致性检查
- 可观测性：retrieval telemetry/duoshe 读取改为 best-effort；`retrieval.log_s1_stats` 开关接入；MCP tool 文案改为“何时用+怎么用”精简版
- 调试能力：`bowl.yaml` 新增 `storage.debug_log_to_file` 与 `storage.debug_log_path`，并在服务端与 `inject_memory.py` 落地文件 debug 日志
- 注入进度日志：`inject_memory.py` 增加“开始嵌入 / 每 200 条耗时 / 完成总量与总耗时”输出
- 脚本规范：`inject_sample/inject_memory/bridge/s1_probe` 统一包方式运行（移除 `sys.path` 注入）并补异常友好处理
- 验证：`python -m pytest -q` 通过（`168 passed, 1 skipped, 7 subtests passed`）

### v0.11.0 — bowl.yaml 配置中心化重构 ✅
- `memory_mcp/config.py` 新建：Config 类，完整映射 bowl.yaml 全部 10 个配置组
- **所有**模块的硬编码参数/env-var 默认值统一为 config 驱动
- 新增首次注入友好体验：空库时自动后台注入，返回"欢迎使用，首次嵌入可能需要2分钟"：
  - `freshness.py`：`FreshnessParams.from_config()` — 修复 `half_life_days=7.0` → `decay.tau=10.71` bug
  - `retrieval.py`：`SEMANTIC_CANDIDATE_LIMIT` / `RESULT_LIMIT` / `FRESHNESS_WEIGHT` 从 config 读
  - `dedup.py`、`reranker.py`、`rebuild_limits.py`：各阈值/模型名从 config 读
  - `server.py`：移除 `_from_env()`+本地`ServerConfig`，全量通过 `Config.load_cached()`
  - `inject_memory.py`：7 个 `os.getenv()` 硬编码全部删除，从 config 读
  - `scripts/bridge.py`、`s1_probe.py`、`inject_sample.py`：DB_PATH/OLLAMA_URL 从 config 读
- `bowl.yaml` 新增 `injection.file_pattern: "*.md"`（默认只扫 md，注释声明其他格式未验证）
- 优先级链：环境变量 > bowl.yaml > 代码默认值
- 依赖：pyyaml>=6.0
- 版本 0.11.0
- 17 个新测试（`tests/test_config.py`）
- 双语 RELEASE_NOTES + README 配置章节重写
- 修复 Python 3.10 下 `from datetime import UTC` 预存兼容问题（11 文件）
- 169/169 测试全部通过

### v0.10.79 — 智能日记时间注入 + 去重策略优化 ✅
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
