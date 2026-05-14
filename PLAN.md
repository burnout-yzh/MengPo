# PLAN.md

## v0.10.78 — bowl.yaml + 增量更新

### bowl.yaml（孟婆汤碗）
集中式 YAML 配置，乾（算法超参）+ 坤（运维参数），所有参数附建议区间注释。

### 增量更新 — content hash 比对
`inject_memory.py` 现在比较 SHA256 content hash：
- 同 hash → 跳过（未变）
- 不同 hash → 软删旧版本 + 插入新版本
- 不存在 → 正常插入

新增 `updated` 输出计数。

### Dedup LLM 裁决链路
- `chunks_meta.pending_review` 字段 + 自动迁移
- `inject_memory.py` 注入后向量扫描 → 标记待裁决
- MCP 工具：`get_pending_reviews()` + `resolve_dedup_review()`
- `memory_stats()` 含 `pending_reviews` 计数

### 当前状态
- 85/85 测试通过
- v0.10.75 全部已知问题关闭
- 4 个 scripts 已上线（inject/bridge/s1_probe/inject_sample）
- server.py 已重写为 facade
- S1-S2-Expand 缓存优化已实装

v0.10.75 的全部 8 个已知问题已修复。85/85 单元测试通过。

### v0.10.75 已知问题关闭清单

| # | 问题 | 修复版本 |
|---|------|:--:|
| 1 | inject_memory 硬编码年份 + 非递归 | 0.10.77 — `rglob("*.md")` |
| 2 | inject_memory 非幂等写入 | 0.10.77 — `_chunk_already_stored()` 去重 |
| 3 | server.py 硬编码 schema | 0.10.76 — facade 重写 |
| 4 | CHUNK_SIZE 不可配 | 0.10.77 — `MENGPO_CHUNK_SIZE` 环境变量 |
| 5 | Bare except | 0.10.77 — 具体异常分支 |
| 6 | memory_stats() 缺测试 | 0.10.76 — 间接覆盖 |
| 7 | 日期硬编码 | 0.10.76 — 改用版本号 |
| 8 | AI slop | 0.10.76 — 全量审计修复 |

### 新增 / 重写脚本

| 脚本 | 说明 |
|------|------|
| `scripts/inject_memory.py` | 新 schema 重写，4 修复，环境变量配置 |
| `scripts/bridge.py` | S1→S2 冒烟测试（`S1_vector_search` + `Samsara_Rank`） |
| `scripts/s1_probe.py` | vec0 探针（`S1_vector_search`） |
| `scripts/inject_sample.py` | 样本注入（demo 用） |

### 架构现状（截至 v0.10.77）

```
server.py (MCP facade)
  ├─ get_relevant_memories → S1_vector_search + Samsara_Rank (全量 blend 缓存)
  ├─ expand_retrieval → 排序缓存切片 [cursor:cursor+5]
  ├─ Sansheng_Stone → db.Sansheng_Stone()
  └─ memory_stats → db.row_counts()

scripts/
  inject_memory.py    — 文件扫描 → chunk → 嵌入 → atomic_store（去重+幂等）
  bridge.py           — S1→S2 手动冒烟测试
  s1_probe.py         — vec0 检索探针
  inject_sample.py    — demo 样本注入
  check_consistency.py — 一致性检查
  manual_qa.py        — 手动 QA

底层模块（memory_mcp/）
  database.py    — 连接工厂 + Sansheng_Stone + 软删除 + 列表
  schema.py      — memories + chunks_meta + chunks_vec (vec0)
  retrieval.py   — S1_vector_search / Samsara_Rank / Naihe_Bridge
  freshness.py   — WangYou_Decay
  atomic_store.py — 三表原子写入
  store_flow.py   — 去重预检 → 原子写入编排
  dedup.py        — 向量相似度裁决 (threshold 0.95)
  consistency.py  — 完整性检查
  scanner.py      — 目录扫描
  embeddings.py   — Ollama 嵌入客户端
  reranker.py     — Ollama 重排序客户端
```

---

## Injection Placeholders

### 审计修复清单

| # | 发现 | 修复 |
|---|------|------|
| 1 | `server.py` 用独立表 `memory_metadata`+`vec_memories` — 脚手架残留 | **重写**为 facade，全部委托给 Database / retrieval 模块 |
| 2 | server.py `result_limit=15` — stale | 统一为 `RESULT_LIMIT=5`（S2 最终递送条数） |
| 3 | server.py `_rank()` 直接乘积 — 废弃算法 | 删除，正规使用 `Samsara_Rank` 加权几何平均 |
| 4 | `embeddings.py` + `schema.py` 中嵌入模型名 | 统一为 `qwen3-embedding-0.6b` |
| 5 | `S1_vector_search()` 每行一个事务（46 个） | 改为一次 vec 搜索 + 一次批量 IN JOIN（1 个事务） |
| 6 | `__init__.py` docstring "foundation surface" — 过时 | 更新为完整 MCP 工具包描述 |
| 7 | `freshness_score` 永远是 0.0 — 忘忧衰减空转 | S1→S2 链补 `WangYou_Decay` 填充（fallback: created_at） |
| 8 | `pyproject.toml` 版本 0.10.74 | 改 0.10.75，authors 统一 pawpaw |
| 9 | LICENSE vs pyproject.toml 署名不一致 | 统一 pawpaw |
| 10 | `.gitignore` 里 4 个脚本名但文件不存在 | 保留预留名（`inject_memory.py` 等为内部脚本） |
| 11 | 夺舍 `duoshe_root` 指向 `memory_test_files/` | 保留功能，默认关闭，README 提示可手动开启 |

### 新增功能

| 功能 | 说明 |
|------|------|
| **expand_retrieval** MCP 工具 | session 级 S1 候选缓存，LLM 按需扩展开来获取更多记忆（每轮 +5 条） |
| **S3 写回单元测试** | 6 个测试用例覆盖：主流程/边界/shrink_factor/软删除 |

### 架构现状

```
server.py (MCP facade)
  ├─ get_relevant_memories → S1_vector_search + Samsara_Rank
  ├─ Sansheng_Stone → db.Sansheng_Stone()
  ├─ memory_stats → db.row_counts()
  └─ expand_retrieval → session cache + Samsara_Rank (batch re-rank)

底层模块（memory_mcp/）
  database.py    — 连接工厂 + Sansheng_Stone + 软删除 + 列表
  schema.py      — memories + chunks_meta + chunks_vec (vec0)
  retrieval.py   — S1_vector_search / Samsara_Rank / Naihe_Bridge / S3WritebackPlan
  freshness.py   — WangYou_Decay (艾宾浩斯遗忘曲线)
  atomic_store.py — 三表原子写入 + 故障注入
  store_flow.py   — 去重预检 → 原子写入编排
  dedup.py        — 向量相似度裁决 (threshold 0.95)
  consistency.py  — 完整性检查
  scanner.py      — 目录扫描 + symlink 安全
  embeddings.py   — Ollama 嵌入客户端
  reranker.py     — Ollama 重排序客户端
  retrieval_service.py — 夺舍 + session 管理
```

### 已知限制（待后续版本）

- 生产数据库（`D:\MengPo\mengpo_memory.db`）使用旧 schema (`memory_metadata`)，需迁移到新 schema (`memories`)。
- `inject_memory.py` 等内部脚本未提交进 repo，需独立处理。
- server.py 的 `_blend()` 与 Samsara_Rank 内部公式重复——后续统一导出 blended_score。
- 嵌入客户端 URL 硬编码在 S1_vector_search 默认参数中。
- **第二轮 S1 排除机制**：当 expand 耗尽全部 45 条缓存后，理论上可触发第二轮 S1 排除已递送 IDs。实际上 LLM 狂翻 45 条还没命中的概率极低，暂不实现。如有需要可提 issue。

---

## Injection Placeholders

Public copy keeps these four placeholder files for runtime injection shape:

- `memory_test_files/AGENTS.md`
- `memory_test_files/MEMORY.md`
- `memory_test_files/PROFILE.md`
- `memory_test_files/SOUL.md`


---

## TODOs

See [RELEASE_NOTES.zh.md](RELEASE_NOTES.zh.md) for planned improvements and known issues.
