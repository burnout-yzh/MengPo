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

## 配置说明

算法的核心参数（包括衰减常数、阈值等）均由 `bowl.yaml`（孟婆汤碗）承载，开发者可根据自身认知主频 $R$ 进行微调。

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
本项目按现状提供。我目前不会持续维护，issue 或 pull request 可能不会得到回复。

欢迎 fork、重写和继续开发；如果你觉得它有用，也欢迎点个 Star。

## 许可证
MIT，详见 `LICENSE`。

---

*献给这个鲜活世界的三十周年礼物*