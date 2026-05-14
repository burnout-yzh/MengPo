# PLAN.md

Public release placeholder.

This file is intentionally minimal in the open-source copy.

## Injection Placeholders

Public copy keeps these four placeholder files for runtime injection shape:

- `memory_test_files/AGENTS.md`
- `memory_test_files/MEMORY.md`
- `memory_test_files/PROFILE.md`
- `memory_test_files/SOUL.md`


---

## TODOs

> **Note**: These issues are now formally disclosed with fix commitments in [RELEASE_NOTES.md](./RELEASE_NOTES.md) (v0.10.75).

### 1. inject_memory.py 硬编码年份过滤器 + 非递归扫描

- `glob.glob(os.path.join(MEMORY_DIR, "2026-*.md"))` 硬编码了 2026，2027 年直接炸
- 不递归子目录，`memory_test_files/memory/appendix/*` 永远不会被扫描
- 修复方案：替换为 `glob.glob(os.path.join(MEMORY_DIR, "**/*.md"), recursive=True)`

### 2. inject_memory.py 全量非幂等写入 — 无增量注入 + 无去重

- 每次跑都是全量重扫所有文件、重嵌入、全量 INSERT，没有增量判别
- 没有 dedup → 跑 N 次就膨胀 N 倍，`mengpo_memory.db` 会无限变大
- INSERT 不幂等：同一个文件的同一个 chunk 在不同注入轮次会产生不同的 rowid
- 修复方向：注入前按 (source_file, chunk_index) 去重判别，已有则跳过

### 3. server.py \_s1_search() 硬编码的 schema 依赖

- `SELECT rowid, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT ?`
- 如果 vec0 虚拟表 schema 变化（比如 embedding 维度变更），这里不会自动适配
- 环境变量 `MENGPO_CANDIDATE_LIMIT` 已经外置，但 `MENGPO_DB_PATH` 默认值绑死在 `Path.cwd() / "mengpo_memory.db"`
- 修复方向：`Limit` 等参数应考虑前置一致性检查

### 4. 硬编码常量缺少环境变量重写

- `inject_memory.py` 中的 `CHUNK_SIZE=500` 不可配置
- `server.py` 中的 `half_life_tau` 等超参虽然已有环境变量，但默认值推导在模块加载时执行，单元测试中改环境变量需要重启解释器
- 修复方向：对 `CHUNK_SIZE` 加环境变量 `MENGPO_CHUNK_SIZE`

### 5. Bare except 隐患

- `inject_memory.py:65` 的 `except:` 没有指定异常类型，SQLite 错误和 embedding 失败会被同一锅端，无法区分
- 修复方向：拆分为 `except sqlite3.Error` 和 `except EmbeddingError`，后续在 PLAN.md 移除此条目

### 6. server.py memory_stats() 缺少单元测试覆盖

- 修复过程中发现了 memory_stats() 没有 `sqlite_vec.load` 的 bug，但该函数在已有测试套件中无覆盖
- 修复方向：在 `tests/` 中补一个 `test_server_stats.py`，对新加的功能函数做回归

### 7. 日期硬编码：RELEASE_NOTES 含具体日期

- 非阻塞项，但发布流程中的具体日期需要每次手动更新，容易漏
- 修复方向：考虑用 `git tag` 代替版本号中的日期字段

