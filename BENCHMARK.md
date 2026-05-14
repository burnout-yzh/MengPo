# BENCHMARK.md — MengPo 性能基准

> v0.10.78, 实测日期: 2026-05-14

## 硬件环境

| 项目 | 值 |
|------|-----|
| CPU | AMD Ryzen 7 5800H (8C/16T, 3.2GHz) |
| GPU | RTX 3070 Laptop 8GB |
| RAM | 16GB DDR4-3200 |
| 存储 | NVMe SSD (ZHITAI Ti600 1TB) |
| OS | Windows 11 |

## 软件版本

| 组件 | 版本 |
|------|------|
| Python | 3.11 |
| Ollama | latest (2026-Q2) |
| sqlite-vec | 0.1.9 |
| 嵌入模型 | qwen3-embedding-0.6b (Q8_0, ~600MB) |

## 汤碗配置 (bowl.yaml 关键参数)

```yaml
embedding:
  model: qwen3-embedding-0.6b
  dim: 1024

decay:
  tau: 10.71         # 拉面努金半衰期

retrieval:
  candidate_limit: 45
  result_limit: 5
  freshness_weight: 0.368

chunk:
  size_min: 160       # 短段累积合并到 160 chars
  size_max: 500       # 长段在句边界切断

injection:
  batch_size: 15      # 每批嵌入 15 个 chunk
```

## 测试数据集

| 指标 | 值 |
|------|-----|
| Markdown 文件 | 145 个 |
| 文件总大小 | ~1.2 MB |
| 来源 | 记忆日记 (memory/) + 附录 (memory/appendix/) |
| 语言 | 中文为主 |
| 内容类型 | 日记、技术记录、配置文件说明 |

## Chunk 特征

| 指标 | 值 |
|------|-----|
| Chunk 策略 | min=160, max=500, 句子边界优先切 |
| 平均 chunk 大小 | ~247 chars |
| 最大 chunk | ~520 chars |
| 最小 chunk | ~16 chars（尾部残片） |
| 单文件 chunk 数 | ~19 avg（10KB 文件） |

## 性能结果

### 全量重建 (145 文件, DB 为空)

| 指标 | 值 |
|------|-----|
| **总耗时** | **99.8s** |
| 注入 chunk 数 | 2,807 |
| chunk 吞吐 | ~150 chunks / 5s (30/s) |
| GPU 释放 | ✅ `ollama stop` 自动执行 |
| Dedup 扫描 | ⚠️ 批量嵌入超时（2807 条单批过大）— 待分批 |

### 增量注入 (3 个新增文件, ~335 chunks)

| 指标 | 值 |
|------|-----|
| **增量耗时** | **纳入全量**（DB 已清，无对比） |
| 增量识别 | ✅ content-hash 比对 |
| 无变化文件 | **1.9s** (2,807 chunks 全跳过) |

### 内存占用

| 阶段 | 观测 |
|------|------|
| 注入中 (Ollama) | GPU ~100%, VRAM ~2.2GB |
| 注入后 | `ollama stop` → GPU 0% |
| 空闲 | ~0% GPU |

## 已知问题

- **Dedup 扫描批量超时**：2807 条候选单批嵌入 → Ollama timeout。需分页（如 100/批）。
- **SSH 长耗时不稳定**：>60s 的注入建议本地直接运行，不在 SSH 中执行。
- **DB 文件锁**：MCP server 运行时 DB 被锁，无法 `del`，需用 SQL `DELETE` 清表。

## 复现命令

```powershell
cd D:\MengPo
del inject.log 2>$null

# 清空 DB（如果被 MCP 锁住）
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

# 注入
$env:MENGPO_MEMORY_DIR="D:\MengPo\memory_test_files\memory"
$env:MENGPO_CHUNK_SIZE="500"
$env:MENGPO_CHUNK_MIN_SIZE="160"
$env:MENGPO_BATCH_SIZE="15"
python inject_memory.py

# 查看结果
type inject.log
```

## 调参建议

| 目标 | 改法 |
|------|------|
| 更少 chunk（更快） | 调大 `chunk.size_min` → 200，`chunk.size_max` → 600 |
| 更细粒度 | 调小 `chunk.size_min` → 80，`chunk.size_max` → 400 |
| 更快注入 | 调大 `injection.batch_size` → 25-30 |
| 更低显存 | 换更小的嵌入模型（如 nomic-embed-text, 768d） |
