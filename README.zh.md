# MengPo (M.E.N.G.P.O.)

**燃尽冗余，方得共鸣。**
*Burn the redundant, find the resonant.*

## 概览

**Memory Evolution & Next-Gen Preference Orchestrator.**

一个基于 MCP 协议的认知代谢系统，采用 $\tau = 24/\sqrt{5}$ 的拉面努金衰减常数，实现从"海量存档"到"动态共鸣"的进化。

### 核心原理：认知代谢管线 (Cognitive Pipeline)

本系统不进行简单的 CRUD，所有记忆片段必须经历以下代谢闭环：

**奈何桥 (Naihe Bridge / S1)**：基于语义向量执行候选门控，筛选前 45 条相关记忆。

**轮回 (Samsara Rank / S2)**：应用拉面努金衰减进行时空重排，决定哪些记忆值得在当前上下文"转世"。

$$Score = (1 - \text{Distance}) \cdot e^{-\frac{\Delta t}{\tau}}$$

**三生石 (Sansheng Stone / S3)**：对高频或重要锚点执行写回提权，刻下时间深度的"缘分"。

**忘川 (Wang Chuan / Decay)**：所有冗余与陈旧信息终将随时间沉底，眠于九幽。

> "燃尽冗余，方得共鸣。"

---

## 项目说明
- English README: `README.md`
- 许可证：MIT

## 当前状态
- 原子 `store_memory`
- 软删除可见性控制
- 忘忧衰减 (WangYou Decay)：基于 $\tau = 24/\sqrt{5}$ 的新鲜值评分系统。
- 带 symlink 保护的 Markdown 目录扫描
- 检索 JSONL 事件记录
- Ollama embedding 调用策略：`timeout=10s`, `retry=0`
- 检索排序策略：语义 top45、按新鲜值重排、固定返回 5 条
- S1/S2/S3 回忆闭环与 `expand` 排重
- S3 写回强化
- 夺舍注入 (DuoShe Injection)：可配置新会话首轮强制同步"最新人格"，实现跨会话的认知连续性。
- 忘川审计：通过 check_consistency.py 辅助处理遗忘边缘的去重与裁决。

## 已通过集成验证
- 真正的 `sqlite-vec` vec0 接线与 SQL 检索已跑通。
- 写入 -> 入库 -> 检索 -> 返回的端到端链路已跑通。
- chunker、去重裁决运行时、LLM 回调分支处理已跑通。

## 待继续扩展
- 当前 helper 的完整 MCP tool surface 集成。

当前 MCP 说明：
- `memory_mcp/server.py` 提供可工作的本地 MCP 入口。
- 该入口已在 qwenpaw 实际集成中验证通过。

## 开发
```bash
python3 -m unittest discover -v
python3 scripts/manual_qa.py
PYTHONPATH=. python3 scripts/manual_qa.py
python3 scripts/check_consistency.py <db_path>
```

## 配置说明 — 唯一配置源

所有参数由仓库根目录下的 **`bowl.yaml`**（孟婆汤碗）承载。`memory_mcp/config.py` 在启动时读取 YAML，为每个模块提供类型化的参数值。

### 优先级链

```
环境变量  >  bowl.yaml 中的值  >  代码默认值
```

临时设置 `MENGPO_DB_PATH` 等环境变量可在不修改 bowl.yaml 的前提下覆盖 `storage.db_path`。

### bowl.yaml 中的关键路径

```yaml
storage:
  db_path: ./mengpo_memory.db      # SQLite 数据库文件
  log_path: ./mcp_access.log       # MCP server 访问日志

injection:
  memory_dir: ./memory              # 待扫描的 Markdown 日记目录
  batch_size: 15                    # 批量嵌入大小

server:
  ollama_base_url: http://127.0.0.1:11434
  mcp_port: 18081
  mcp_name: MengPo Memory Server
  rerank_model: qwen3-reranker-0.6b
```

### 部署到其他盘（例如 E 盘）

1. 将仓库复制到 `E:\MengPo\`
2. 编辑 `bowl.yaml`：

   ```yaml
   storage:
     db_path: E:\MengPo\mengpo_memory.db
   injection:
     memory_dir: E:\MengPo\memory
   ```
3. 正常运行 — 无需设置环境变量或修改代码。

### 完整参数对照表

| bowl.yaml 路径 | Config 属性 | 类型 | 默认值 |
|---|---|---|---|
| `embedding.model` | `embedding.model` | str | `qwen3-embedding-0.6b` |
| `embedding.dim` | `embedding.dim` | int | 1024 |
| `decay.tau` | `decay.tau` | float | 10.71 |
| `decay.initial_strength` | `decay.initial_strength` | float | 1.0 |
| `decay.floor` | `decay.floor` | float | 0.01 |
| `retrieval.candidate_limit` | `retrieval.candidate_limit` | int | 45 |
| `retrieval.result_limit` | `retrieval.result_limit` | int | 5 |
| `retrieval.freshness_weight` | `retrieval.freshness_weight` | float | 0.368 |
| `sansheng_stone.shrink_factor` | `sansheng_stone.shrink_factor` | float | 0.368 |
| `dedup.threshold` | `dedup.threshold` | float | 0.95 |
| `chunk.size_min` | `chunk.size_min` | int | 160 |
| `chunk.size_max` | `chunk.size_max` | int | 500 |
| `server.ollama_base_url` | `server.ollama_base_url` | str | `http://127.0.0.1:11434` |
| `server.mcp_port` | `server.mcp_port` | int | 18081 |
| `server.mcp_name` | `server.mcp_name` | str | `MengPo Memory Server` |
| `server.rerank_model` | `server.rerank_model` | str | `qwen3-reranker-0.6b` |
| `storage.db_path` | `storage.db_path` | str | `./mengpo_memory.db` |
| `storage.log_path` | `storage.log_path` | str | `./mcp_access.log` |
| `injection.memory_dir` | `injection.memory_dir` | str | `./memory` |
| `injection.batch_size` | `injection.batch_size` | int | 15 |
| `rebuild.warn_max_files` | `rebuild.warn_max_files` | int | 250000 |
| `rebuild.hard_max_files` | `rebuild.hard_max_files` | int | 500000 |
| `rebuild.warn_max_bytes` | `rebuild.warn_max_bytes` | int | 26843545600 |
| `rebuild.hard_max_bytes` | `rebuild.hard_max_bytes` | int | 53687091200 |

### 向后兼容

所有旧环境变量（`MENGPO_DB_PATH`、`MENGPO_MEMORY_DIR`、`MENGPO_OLLAMA_URL` 等）继续生效，**优先级高于** `bowl.yaml`。

## 运维笔记

### DB 清空（保留 schema，清数据）

当 DB 被 MCP server 锁住无法 `del` 时，用 SQL 清表：

```bash
python -c "
import sqlite3, sqlite_vec
c=sqlite3.connect('mengpo_memory.db')
c.enable_load_extension(True); sqlite_vec.load(c)
c.execute('DELETE FROM chunks_vec')
c.execute('DELETE FROM chunks_meta')
c.execute('DELETE FROM memories')
c.commit(); c.execute('VACUUM'); c.close()
print('DB cleared')
"
```

> 注意：`chunks_vec` 是 vec0 虚拟表，必须加载 `sqlite_vec` 扩展后才能 DELETE。重建索引需要重新运行 `inject_memory.py`。

### v0.10.78 性能基准（Windows + RTX 3070 Laptop 8GB）

| 场景 | 文件 | 注入 | 耗时 | GPU 退出 |
|------|:--:|------|------|:--:|
| 全量重建 (DB 已清) | 145 | 2807 chunks | **99.8s** | ✅ ollama stop |
| 增量 (无变化) | 145 | 0 chunks | **1.9s** | ✅ |
| 单文件增量 (估计) | 1 | ~43 chunks | ~1-2s | ✅ |

配置：`chunk: size_min=160, size_max=500`，`batch_size=15`，`qwen3-embedding-0.6b`。详见 `BENCHMARK.md`。

（测试数据约为 1 MB 尺寸的纯粹 md 文件 在空数据库 进行全量重注入，耗时<100秒。）

## 重建扫描限制（T15 预检）

后续 `.md` 语料重建前，扫描预检限制定义在：

- `memory_mcp/rebuild_limits.py`

默认值：

- `warn_max_files = 250000 (WARNING_CHUNKS)`
- `hard_max_files = 500000 (MAX_CHUNKS)`
- `warn_max_bytes = 25 GiB`
- `hard_max_bytes = 50 GiB`

限制覆盖规则：

- 任意限制项设为 `-1` 表示该项不设上限。

相关可调检索阈值：

- 语义候选上限可通过 `memory_mcp/retrieval.py` 中的 `candidate_limit` 调整（`Samsara_Rank` / `Naihe_Bridge`）。

## 路线图

当前路线图以仓库的 issue 与提交历史为准。

## 项目状态
本项目按现状提供。我目前不会持续维护，也许会持续改进，issue 或 pull request 可能不会得到回复。

欢迎 fork、重写和继续开发；如果你觉得它有用，也欢迎点个 Star。

## 许可证
MIT，详见 `LICENSE`。

---

*献给这个鲜活世界的三十周年礼物*