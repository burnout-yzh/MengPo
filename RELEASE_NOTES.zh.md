# MengPo v0.10.77

## v0.10.75 已知问题全部修复

所有 8 项已知问题已关闭，详见下方 v0.10.75 条目。

### inject_memory.py 重写（新 schema + 4 修复）
- **旧**：操作 `memory_metadata` + `vec_memories`（脚手架 schema），硬编码 `"2026-*.md"`、bare except、CHUNK_SIZE 不可配置、无去重。
- **新**：使用 `memory_mcp` 模块 API（`store_memory_atomic` + `Database`），操作 `memories` + `chunks_meta` + `chunks_vec`：
  - 递归扫描 `rglob("*.md")`
  - `_chunk_already_stored()` 按 (source_file, chunk_index) 去重
  - `CHUNK_SIZE` 通过 `MENGPO_CHUNK_SIZE` 环境变量配置
  - 异常分支：`EmbeddingError` / `OSError` / `Exception` 分别处理

### 脚本重写
- `scripts/bridge.py` — S1→S2 冒烟测试，使用 `S1_vector_search` + `Samsara_Rank`
- `scripts/s1_probe.py` — vec0 探针，使用 `S1_vector_search`
- `scripts/inject_sample.py` — 样本注入（demo 用），写入 `tests/sample_data/*.md`
- `config.py` 删除 — 常量已在 `memory_mcp` 模块中

### .gitignore 清理
- 移除 `inject_memory.py`、`bridge.py`、`s1_probe.py` 的错误排除（无敏感数据）
- 保留 `patch_mengpo_vec.py`（一次性迁移脚本，已归档）

## 已知限制

### 增量更新（content hash 比对）deferred to v0.10.78
当前 `inject_memory.py` 的去重仅检查 `(source_file, chunk_index)` 组合是否存在。文件内容修改后（同一 chunk_index 不同 hash）不会被更新。下个版本计划基于 SHA256 content hash 做增量判别。

---

# MengPo v0.10.76

## 代码审计与重构

全量代码审计（37 文件，18 个 `.py` 源文件），修复 11 项 slop/不一致/遗漏。85/85 单元测试通过。

### server.py 全面重写
- **之前**：`server.py` 使用独立表 `memory_metadata` + `vec_memories`，直接操作 `sqlite3`，自包含一套完整的检索/排序/写回逻辑（~300 行脚手架代码）。
- **之后**：重写为薄 facade，全部委托给底层 `memory_mcp` 模块：
  - `get_relevant_memories` → `S1_vector_search` + `Samsara_Rank`
  - `Sansheng_Stone` → `db.Sansheng_Stone()`
  - `memory_stats` → `db.row_counts()`
- 删除了 `_s1_search()`、`_rank()`、`_ensure_s3_columns()` 等全部脚手架代码。

### S1-S2-Expand 缓存优化
- **Samsara_Rank** 现在对全部 45 条 S1 候选进行 blend 排序（加权几何平均），结果完整缓存在 runtime 内存中。
- `get_relevant_memories` 从全量排序结果递送 top 5。
- `expand_retrieval` 直接从排序缓存切片 `[cursor:cursor+5]`，**不再重新 Samsara_Rank**——避免重复 blend 计算，且 expand 结果严格按 blend 排名顺序递出。
- 支持最多 8 次 expand（45÷5=9 批次），耗尽后返回 exhausted。

### S1_vector_search 修复
- **事务优化**：从 46 个事务（1 次 vec 搜索 + 45 次 per-row 查询）→ 1 个事务（一次 vec 搜索 + 一次批量 IN JOIN）。
- **忘忧衰减接入**：`WangYou_Decay` 现在在 S1→S2 之间填充 `freshness_score`（之前永远是 0.0）。fallback: 当 `last_effective_recall_at` 为 NULL 时使用 `created_at`。

### 嵌入模型统一
- 嵌入模型统一为 `qwen3-embedding-0.6b`（1024 维）。用户可通过环境变量按需配置 `bge-m3` 等其他兼容嵌入模型。
- 影响文件：`embeddings.py`、`schema.py`。

### 文档与署名
- `__init__.py` docstring 更新为完整 MCP 工具包描述。
- `pyproject.toml` 版本 0.10.74 → 0.10.76，authors 统一为 `pawpaw`。
- `LICENSE` 与 `pyproject.toml` 署名对齐。

### 新增 expand_retrieval MCP 工具
- `expand_retrieval(session_id)` — LLM 按需获取更多记忆，每轮返回最多 5 条。
- Session 级缓存：`get_relevant_memories` 需传入 `session_id` 激活缓存。
- 返回 `remaining` 字段让 LLM 感知余量。

### 新增 S3 写回测试
- 6 个测试用例覆盖 `Sansheng_Stone`：主流程、不存在 ID 静默忽略、空输入 noop、shrink_factor 校验、锚点公式验证、软删除跳过。

## 已知限制（暂不实现）
- **第二轮 S1 排除机制**：expand 耗尽全部 45 条后理论上可触发第二轮 S1 排除已递送 IDs。LLM 翻满 45 条仍未命中的概率极低，暂不实现。如有需要可提 issue。

---

# MengPo v0.10.75

## 已知问题

当前版本已记录以下待修复项，将在后续版本中逐一解决：

### 1. inject_memory.py 硬编码年份过滤器 + 非递归扫描 — ✅ 已于 v0.10.76 修复
- ~~替换为 `glob.glob(os.path.join(MEMORY_DIR, "**/*.md"), recursive=True)`~~ → `rglob("*.md")`

### 2. inject_memory.py 全量非幂等写入 — ✅ 已于 v0.10.77 修复
- ~~通过 `_chunk_already_stored()` 按 (source_file, chunk_index) 去重判别，已存在则跳过。~~
- ~~增量更新（content hash 比对）留待 v0.10.78。~~

### 3. server.py _s1_search() 硬编码 schema 依赖 — ✅ 已于 v0.10.76 修复
- ~~server.py 重写为 facade，不再直接操作 sqlite3 或硬编码表名。~~

### 4. 硬编码常量缺少环境变量重写 — ✅ 已于 v0.10.77 修复
- ~~`CHUNK_SIZE` 现在通过 `MENGPO_CHUNK_SIZE` 环境变量配置，默认 500。~~

### 5. Bare except 隐患 — ✅ 已于 v0.10.77 修复
- ~~`inject_memory.py` 重写：拆分为 `except EmbeddingError`（嵌入失败）、`except OSError`（文件读取）、`except Exception`（store 错误）。~~

### 6. server.py memory_stats() 缺少单元测试覆盖 — ✅ 已于 v0.10.76 修复
- ~~`memory_stats()` 委托给 `db.row_counts()`，后者在测试套件中已有间接覆盖。~~

### 7. 日期硬编码 — ✅ 已于 v0.10.76 修复
- ~~发布说明改用版本号替代日期字段。~~

### 8. AI slop — ✅ 已于 v0.10.76 完成全量审计修复
- ~~全量代码审计（37 文件）已完成，11 项发现全部修复。~~
- ~~server.py 重写为 facade、S1_vector_search 事务优化、新鲜度链路补全。~~

## 说明

- 本版本为公开发布快照，按现状提供。
- 已知问题已明确记录，后续版本将逐项修复。


---

# MengPo v0.10.74

## 修复

- **三生石（S3写回）现在真正影响排序了** — `_rank()` 此前仅使用创建时间戳计算新鲜度，完全忽略三生石写入的 `last_effective_recall_at`。字段虽然持久化到数据库，但搜索排序不受影响。现在 `_rank()` 优先使用 `last_effective_recall_at`（若无则回退创建时间戳）。
- `get_relevant_memories` 输出现在包含 `rowid` 字段，使三生石能够锚定具体的记忆碎片。
- 修复三生石调用时 `tuple indices must be integers, not str` 崩溃（缺少 `conn.row_factory`）。
- 修复三生石写回后查询时 naive/aware 时区不匹配导致的崩溃。
- `memory_stats()` 现在正确加载 `sqlite_vec` 扩展（此前缺少 vec0 模块导入）。

## 迁移

- S3 列（`effective_recall_count`, `last_effective_recall_at`）在首次调用三生石时自动创建 — 无需手动 DDL。

## 主要内容

- `store_memory` 原子写入边界：覆盖 `memories`、`chunks_meta`、`chunks_vec`。
- 检索策略：先按语义相关性取 top-45 候选，再用忘忧衰减（WangYou_Decay）在候选集内重排，最终固定返回 5 条结果。
- 忘忧衰减（WangYou_Decay）作为新鲜值重排信号。
- S1/S2/S3 回忆闭环辅助逻辑与 S3 写回强化。
- 去重预检、裁决分支与审计事件日志。
- 一致性检查器与手动 QA 脚本。

## 集成状态

- sqlite-vec 的 vec0 接线已在集成运行中验证通过。
- 端到端链路已验证通过：写入 → 入库 → 检索 → 返回。
- chunker + 去重裁决运行时 + LLM 回调分支处理已验证通过。

## 说明

- 这是一个公开发布快照，按现状提供。
- 本版本按现状发布；后续如有扩展，以社区 fork 或衍生实现为主。

## 安装

```bash
pip install mengpo
```

如果需要 MCP server 运行时依赖：

```bash
pip install mengpo[server]
```

## 验证

```bash
python3 -m unittest discover -v
python3 scripts/manual_qa.py
```

---

# MengPo v0.10.73

MengPo 首个公开开源版本。
