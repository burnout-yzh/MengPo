# MengPo v0.12.0

## 快速上手体验：`setup.bat` + `requirements.txt` + 首次使用指引

孟婆现在 **clone 即跑，零摩擦上手**。不再需要猜测安装哪些包。

### 新增文件
- **`setup.bat`** — 一键环境引导。自动检测 Python 3.10+，按阿里云 → 清华 → PyPI 顺序探测可用镜像（国内友好），安装 `requirements.txt` 依赖，验证孟婆导入。同时兼容 `uv sync`。
- **`requirements.txt`** — 最小依赖声明：`mcp>=1.0`、`sqlite-vec==0.1.9`、`pyyaml>=6.0`。
- **`首次使用_first_time_use.md`** — 完整的首次使用指引。涵盖：前置要求、三步启动、可选 Ollama 安装（PowerShell 一行命令）、"首次自展开"原理说明、QwenPaw Desktop 和 Claude Desktop 的 MCP 配置示例、常见问题排查。

### README 双语更新
- `README.md` 和 `README.zh.md` 均以"快速开始"章节开篇。
- 新增**版本历史**表，覆盖 v0.10.78 → v0.12.0。

### 设计考量
- **方案 A（requirements.txt + pip）** 与 **方案 B（uv sync）** 同时支持——用户自选顺手工具。
- `setup.bat` 幂等：更新后重新运行安全无副作用。
- 离线友好：pip/uv 缓存依赖后无需网络。

### 无代码改动
- `pyproject.toml`：版本升至 `0.12.0`。
- `memory_mcp/` — 未变动。

---

# MengPo v0.11.0

## bowl.yaml — 现为唯一配置源

`config.py` 从 `bowl.yaml` 读取全部参数。碗中定义的每个参数现已接线到代码。优先级链：**环境变量 > bowl.yaml > 代码默认值**。

### 新增模块：`memory_mcp/config.py`
- `Config` 类，含 10 个嵌套配置组（embedding, decay, retrieval, sansheng_stone, dedup, chunk, server, storage, injection, rebuild）。
- `Config.load()` — 加载 `bowl.yaml`，应用环境变量覆盖。
- `Config.load_cached()` — 单例缓存，重复调用不重复加载。
- `Config._find_bowl_yaml()` — 从 CWD 或仓库根目录自动发现 `bowl.yaml`。
- `Config._apply_env_overrides()` — 环境变量高于 YAML 值。

### 从硬编码迁移到 Config 的模块：

| 模块 | 修改前 | 修改后 |
|------|--------|--------|
| `retrieval.py` | `SEMANTIC_CANDIDATE_LIMIT = 45`（硬编码） | `Config.load_cached().retrieval.candidate_limit` |
| `retrieval.py` | `RESULT_LIMIT = 5`（硬编码） | `Config.load_cached().retrieval.result_limit` |
| `retrieval.py` | `FRESHNESS_WEIGHT = 0.368`（硬编码） | `Config.load_cached().retrieval.freshness_weight` |
| `freshness.py` | `FreshnessParams(half_life_days=7.0)`（**硬编码！**） | `FreshnessParams.from_config()` → `decay.tau=10.71` |
| `dedup.py` | `DEFAULT_DEDUP_THRESHOLD = 0.95`（硬编码） | `Config.load_cached().dedup.threshold` |
| `reranker.py` | `DEFAULT_RERANK_MODEL = "qwen3-reranker-0.6b:latest"`（硬编码） | `Config.load_cached().server.rerank_model` |
| `rebuild_limits.py` | `DEFAULT_WARN_MAX_FILES = 250_000` 等（硬编码） | `Config.load_cached().rebuild.*` |
| `server.py` | `_from_env()` + 本地 `ServerConfig` dataclass | 全文件共 8 处改为 `Config.load_cached()` |
| `inject_memory.py` | 7 个 `os.getenv("MENGPO_*")` 默认值 | `Config.load()` → `cfg.injection.memory_dir` |
| `scripts/bridge.py` | `os.getenv("MENGPO_DB_PATH", ...)` | `Config.load_cached().storage.db_path` |
| `scripts/s1_probe.py` | `os.getenv("MENGPO_DB_PATH", ...)` | `Config.load_cached().storage.db_path` |
| `scripts/inject_sample.py` | 3 个 `os.getenv("MENGPO_*")` 默认值 | `Config.load_cached().*` |

### 修复的 bug：decay.tau 不一致
`FreshnessParams.half_life_days` 之前硬编码为 **7.0 天**，但 `bowl.yaml` 写的是 `decay.tau: 10.71`（基于 84 天数据的黄金特征推导值）。现在 `FreshnessParams.from_config()` 从碗中读取 `decay.tau=10.71`。**这是一个活动 bug**——自 v0.10.78 起代码与碗不一致。

### 新增测试：`test_config.py`（17 个测试用例）
覆盖：默认值、`bowl.yaml` 加载、文件缺失回落、7 种环境变量覆盖场景、空环境变量不覆盖、单例缓存、等值、dingzhen 健康检查。

### 依赖
`pyproject.toml` 新增 `pyyaml>=6.0`。

### 升级说明
- 无需手动迁移。旧环境变量（`MENGPO_DB_PATH`、`MENGPO_MEMORY_DIR` 等）继续生效，优先级高于 `bowl.yaml`。
- E 盘部署只需在 `bowl.yaml` 中修改 `injection.memory_dir` 和 `storage.db_path`，无需设置环境变量。

---

# MengPo v0.10.79

## 智能日记时间注入
`_extract_diary_date()` 从日记文件名中提取原始创建日期。

- 支持 8 种日期格式：`YYYY-MM-DD`、`YYYY_MM_DD`、`YYYYMMDD`、`MM-DD-YYYY`、`MMDDYYYY`
- 可选 HHMM 时间提取（分钟精度，如 `2026-03-19-0820.md` → `2026-03-19T08:20`）
- 单数字月日自动零补（`2026-1-5` → `2026-01-05`）
- 三级 fallback：文件名日期 → 文件 mtime → CURRENT_TIMESTAMP
- `store_memory_atomic()` 新增可选 `created_at` 参数，向后兼容
- 22 个测试（`tests/test_diary_date.py`）

**为什么重要：** 没有此功能，迁移时 145 个日记文件的 chunk 将全部获得相同 `created_at`，导致 WangYou_Decay 新鲜度评分失效。

## 去重策略 — 零 Ollama 重嵌入
去重相似度扫描不再通过 `embed_batch()` 重新嵌入。

- 注入阶段已写入 `chunks_vec` 的向量直接复用
- `_vec_blob_to_json()` 将 sqlite-vec BLOB 格式转为 JSON 用于 MATCH 查询
- SQL JOIN `chunks_meta` + `chunks_vec` 替代批量嵌入循环
- 8 个测试（`tests/test_vec_blob.py`）

## 测试套件
- 152 个测试，全部通过（130 已有 + 22 新增）

---

# MengPo v0.10.78

## bowl.yaml — 孟婆汤碗
集中式 YAML 配置，乾（算法超参）+ 坤（运维参数）。所有参数附易懂注释与合理建议区间。

## Chunk 策略改进
- min_size: 80→160, max_size: 500。短段累积合并到 min_size 才输出，长段在句子边界（。！？）切断。
- 硬边界（分隔线、代码块）强制刷新缓冲区。
- 效果：10KB 日记从 93 chunk → 43 chunk（-54%），平均 245 chars。

## 批量嵌入 + GPU 释放
- `OllamaEmbeddingClient.embed_batch()` — 一次 API 调用嵌入多条文本。
- `inject_memory.py` 默认 15/batch，实测 145 文件 2807 chunk 全量重建 **99.8s**（逐条 ~8 分钟）。
- 注入完成后 `ollama stop` 自动释放 GPU。
- 结构化 log（`inject.log`），50 chunk 进度打点 + 时间戳。

## 增量更新 — content hash 比对
- `inject_memory.py` 比较 SHA256 content hash：同 hash 跳过，不同 hash → 软删旧版 + 插入新版。
- 145 文件无变化时 **1.9s** 全跳过。

## Dedup LLM 裁决链路
- `chunks_meta.pending_review` + 自动迁移。
- 注入后批量向量相似度扫描 → 待裁决标记。
- MCP 工具：`get_pending_reviews()` + `resolve_dedup_review()`。
- `memory_stats()` 含 `pending_reviews` 计数。

## 重排模型预留
- `EmbeddingReranker`（余弦相似度），默认关闭。S1+S2 已足够。
- `rerank_model` 字段预留 cross-encoder 接入。

## 性能基准
- `BENCHMARK.md` 记录完整性能数据（145 文件, 2807 chunks, 99.8s）。
- README 运维笔记：DB 清空命令 + 性能基准表。

## 测试
- 122/122 tests。新增：`embed_batch`(11), `chunk_text`(8), `EmbeddingReranker`(7)。

## 已知限制
- Dedup 扫描大批量嵌入超时 → v0.10.79 分批。
- `_blend()` 与 Samsara_Rank 公式重复。
- 智能日记时间注入 → v0.10.79。

---

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

无。v0.10.75 已知问题全部关闭，增量更新已实装。

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
- 本版本按现状发布；后续如有扩展，以社区 fork 或衍生实现为主，虽然不太可能有。

## 安装

见 首次使用_first_time_use.md

---

# MengPo v0.10.73

MengPo 首个公开开源版本。
