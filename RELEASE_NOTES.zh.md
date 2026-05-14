# MengPo v0.10.73

MengPo 首个公开开源版本。
---

# MengPo v0.10.74

## 修复

- **三生石（S3写回）现在真正影响排序了** -- _rank() 此前仅使用创建时间戳计算新鲜度，完全忽略三生石写入的 last_effective_recall_at。字段虽然持久化到数据库，但搜索排序不受影响。现在 _rank() 优先使用 last_effective_recall_at（若无则回退创建时间戳）。
- get_relevant_memories 输出现在包含 rowid 字段，使三生石能够锚定具体的记忆碎片。
- 修复三生石调用时 tuple indices must be integers, not str 崩溃（缺少 conn.row_factory）。
- 修复三生石写回后查询时 naive/aware 时区不匹配导致的崩溃。
- memory_stats() 现在正确加载 sqlite_vec 扩展（此前缺少 vec0 模块导入）。

## 迁移

- S3 列（effective_recall_count, last_effective_recall_at）在首次调用三生石时自动创建 -- 无需手动 DDL。


## 主要内容

- `store_memory` 原子写入边界：覆盖 `memories`、`chunks_meta`、`chunks_vec`。
- 检索策略：先按语义相关性取 top-45 候选，再用忘忧衰减（WangYou_Decay）在候选集内重排，最终固定返回 5 条结果。
- 忘忧衰减（WangYou_Decay）作为新鲜值重排信号。
- S1/S2/S3 回忆闭环辅助逻辑与 S3 写回强化。
- 去重预检、裁决分支与审计事件日志。
- 一致性检查器与手动 QA 脚本。

## 集成状态

- sqlite-vec 的 vec0 接线已在集成运行中验证通过。
- 端到端链路已验证通过：写入 -> 入库 -> 检索 -> 返回。
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
