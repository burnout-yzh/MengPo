# 首次使用 / First Time Use

> 本文件面向**终端用户**：如果你不是在维护 MengPo，这就是你唯一需要读的文件。

---

## 前置要求

- **Python 3.10 或更高版本**（运行 `python --version` 确认）
- **可选：Ollama**（用于本地语义搜索，见下方）
- 网络连接（仅首次安装依赖）

---

## 三步启动

```bash
# 1. 克隆仓库
git clone https://github.com/burnout-yzh/MengPo.git
cd MengPo

# 2. 运行自动安装（自动选择国内镜像）
setup.bat

# 3. 启动服务
python -m memory_mcp.server
```

**如果你使用 `uv`（更快）：**

```bash
uv sync                        # 替代 setup.bat，自动安装依赖
python -m memory_mcp.server
```

---

## 可选：安装 Ollama 嵌入服务

如果你想让孟婆使用**本地语义搜索**（无需联网，隐私安全），需要安装 Ollama：

### 安装 Ollama

```powershell
# PowerShell（管理员），一条命令，零依赖
winget install Ollama.Ollama
```

如果 `winget` 不可用：

```powershell
# 下载官方安装包（国内可能出现网络问题）
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile "$env:TEMP\OllamaSetup.exe"
Start-Process "$env:TEMP\OllamaSetup.exe"
```

### 拉取嵌入模型

```bash
ollama serve          # 启动 Ollama 服务（后台保持运行）
ollama pull qwen3-embedding:0.6b    # 约 600MB，首次下载
```

模型下载完成后，孟婆会自动检测并使用本地嵌入服务。

---

## 首次运行说明

> **"本产品开箱即用，首次运行可能需要自展开，首次嵌入可能需要 2-3 分钟。"**

这是什么意思？

- **自展开**：首次 `python -m memory_mcp.server` 会检测 `bowl.yaml` 配置，自动创建数据库文件（`mengpo_memory.db`）
- **首次嵌入**：如果你配置了 `memory_dir`（记忆文档目录），首次检索时会自动扫描并嵌入所有 `.md` 文件。文件越多，耗时越长
- 以上过程**只发生一次**，后续启动秒开

---

## MCP 配置指引

孟婆是一个 **MCP (Model Context Protocol) Server**。配置到你的 AI 客户端（如 QwenPaw、Claude Desktop、Cursor 等）后即可使用。

### QwenPaw Desktop 配置

编辑 `agent.json`，在 `mcp_servers` 中添加：

```json
{
  "mcp_servers": {
    "MengPo": {
      "name": "MengPo",
      "enabled": true,
      "transport": "stdio",
      "command": "cmd",
      "args": [
        "/c",
        "cd /d D:\\MengPo && python -m memory_mcp.server"
      ],
      "env": {},
      "cwd": ""
    }
  }
}
```

如果你的 Python 不在 PATH 中，替换 `python` 为完整路径（如 `C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python311\\python.exe`）。

### Claude Desktop 配置

编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "MengPo": {
      "command": "cmd",
      "args": ["/c", "cd /d D:\\MengPo && python -m memory_mcp.server"]
    }
  }
}
```

### 验证 MCP 连接

重启 AI 客户端后，你应该能看到以下工具：

| 工具 | 用途 |
|:-----|:-----|
| `get_relevant_memories` | 语义搜索记忆（S1+S2） |
| `Sansheng_Stone` | 标记有效记忆（S3 写回） |
| `memory_stats` | 查看数据库统计 |

---

## 常见问题

**Q: `ModuleNotFoundError: No module named 'memory_mcp'`**

A: 确保你在 MengPo 仓库根目录下运行，不是子目录。

**Q: `No module named 'sqlite_vec'`**

A: 运行 `setup.bat` 或 `pip install sqlite-vec==0.1.9`。

**Q: pip install 超时**

A: `setup.bat` 会自动尝试阿里云镜像 → 清华镜像 → 官方 PyPI。如果全部失败，手动指定：`pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/`
