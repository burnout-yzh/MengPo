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

### 8.AI slop
- 当前仅勉强挣扎着完成最小可行性验证的 vibe slop状态，计划未来进行代码的人工审查，修复各种slop问题，修复各与原意图不一致的代码逻辑。
- 当前仅勉强挣扎着完成最小可行性验证，项目repo放出来先占坑，基于完成再完美的思路。

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
