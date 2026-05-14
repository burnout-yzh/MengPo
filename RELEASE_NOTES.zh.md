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
- 全仓库删除 `bge-m3` 引用，统一为 `qwen3-embedding-0.6b`（1024 维）。
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

### 1. inject_memory.py 硬编码年份过滤器 + 非递归扫描
- `glob.glob(os.path.join(MEMORY_DIR, "2026-*.md"))` 硬编码了 2026，进入 2027 年后直接失效
- 不递归子目录，`memory_test_files/memory/appendix/*` 等深层目录永远不会被扫描
- **承诺修复**：替换为 `glob.glob(os.path.join(MEMORY_DIR, "**/*.md"), recursive=True)`

### 2. inject_memory.py 全量非幂等写入
- 每次运行都是全量重扫所有文件、重嵌入、全量 INSERT，没有增量判别
- 无去重 → 跑 N 次就膨胀 N 倍，mengpo_memory.db 无限增长
- INSERT 不幂等：同一文件同一 chunk 在不同轮次产生不同 rowid
- **承诺修复**：注入前按 (source_file, chunk_index) 做去重判别，已有则跳过

### 3. server.py _s1_search() 硬编码 schema 依赖
- vec0 虚拟表 schema 变化（如 embedding 维度变更）时不会自动适配
- `MENGPO_DB_PATH` 默认值绑死在 `Path.cwd() / "mengpo_memory.db"`
- **承诺修复**：参数前置一致性检查

### 4. 硬编码常量缺少环境变量重写
- `inject_memory.py` 中的 `CHUNK_SIZE=500` 不可配置
- 部分超参依赖环境变量但默认值在模块加载时推导，单元测试需重启解释器
- **承诺修复**：为 CHUNK_SIZE 加环境变量 `MENGPO_CHUNK_SIZE`

### 5. Bare except 隐患
- `inject_memory.py:65` 的 `except:` 没有指定异常类型，SQLite 错误和 embedding 失败被同一锅端
- **承诺修复**：拆分为 `except sqlite3.Error` 和 `except EmbeddingError`

### 6. server.py memory_stats() 缺少单元测试覆盖
- 该函数在已有测试套件中无覆盖
- **承诺修复**：补 `test_server_stats.py`

### 7. 日期硬编码
- RELEASE_NOTES 含具体日期，每次发布需手动更新，容易遗漏
- **承诺修复**：改用 `git tag` 替代版本号中的日期字段

### 8. AI slop — ✅ 已于 v0.10.76 完成全量审计修复
- ~~全量代码审计（37 文件）已完成，11 项发现全部修复。~~
- ~~server.py 重写为 facade、S1_vector_search 事务优化、新鲜度链路补全、bge-m3 清理等。~~

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
