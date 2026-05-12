# 新闻室「分析 / 策编」执行方式配置

流水线里「LLM 策编」一步默认由 `scripts/llm_editor.py` 直接调用 Gemini / OpenRouter。可通过环境变量改为 **任意 agent CLI 托管**（OpenClaw / Claude Code / Codex / Cursor / Aider / Hermes / …），由 agent 间接执行分析。

## 设计

只有 **两档执行模式**：

- `llm_api`（默认）：`dispatch_llm_editor.sh` 直接 `exec python3 llm_editor.py ...`，与历史行为一致。适合 Cron、本机一键跑通。
- `agent`：把 llm_editor 的调用外包给一个 Hook 脚本或内联命令，由 agent CLI 包装执行。具体是哪种 agent，用 `NEWSROOM_AGENT_KIND` 声明（仅作语义标签，供 SKILL.md 与 Hook 内部分支判断责任边界）。

**契约**：无论哪种方式，**stdout 必须是 `llm_editor.py` 同格式的 JSON 行**，因为 `news_scan_deduped.sh` 会把 stdout 重定向到 picks 文件。

## 环境变量

| 变量 | 说明 |
|------|------|
| `NEWSROOM_ANALYSIS_EXECUTOR` | `llm_api`（默认）\| `agent` |
| `NEWSROOM_AGENT_KIND` | `agent` 模式下声明 agent 类型：`openclaw` \| `claude_code` \| `codex` \| `cursor` \| `aider` \| `hermes` \| 自定义 |
| `NEWSROOM_AGENT_HOOK` | `agent` 模式下可选：可执行脚本路径，接收与 `llm_editor.py` 相同的参数 |
| `NEWSROOM_AGENT_CMD` | `agent` 模式下可选：内联 shell（`eval`），须将 JSON 行输出到 stdout |

执行 Hook/CMD 时，父脚本会导出：

- `NEWSROOM_SCRIPT_DIR`
- `NEWSROOM_ENRICHED_FILE`
- `NEWSROOM_GITHUB_FILE`
- `NEWSROOM_AGENT_KIND`

便于在内联命令或 Hook 中引用。

`agent` 模式未配置 Hook/CMD 时回落到 `llm_api`。

## 参考模板

| `NEWSROOM_AGENT_KIND` | 模板路径 |
|---|---|
| `openclaw` | `scripts/examples/openclaw_analysis_hook.example.sh` |
| `claude_code` | `scripts/examples/claude_code_analysis_hook.example.sh` |
| `codex` | `scripts/examples/codex_analysis_hook.example.sh` |

复制为可写路径、`chmod +x`、改 `exec` 调用为你环境中实际的 CLI 命令即可。

## 旧名兼容

为了不破坏已有 `.env`，dispatcher 自动映射旧的 mode 名称：

| 旧配置 | 等价新配置 |
|---|---|
| `NEWSROOM_ANALYSIS_EXECUTOR=openclaw_agent` + `NEWSROOM_OPENCLAW_ANALYSIS_HOOK` | `EXECUTOR=agent` + `KIND=openclaw` + `AGENT_HOOK=...` |
| `NEWSROOM_ANALYSIS_EXECUTOR=claude_code` + `NEWSROOM_CLAUDE_CODE_ANALYSIS_HOOK` | `EXECUTOR=agent` + `KIND=claude_code` + `AGENT_HOOK=...` |
| `..._OPENCLAW_ANALYSIS_CMD` / `..._CLAUDE_CODE_ANALYSIS_CMD` | `NEWSROOM_AGENT_CMD` |

旧 `.env` 无需迁移即可继续工作；新配置推荐统一使用 `agent` + `NEWSROOM_AGENT_KIND` 三元组。

## 与 SKILL.md 的关系

助手在 OpenClaw / Claude Code / Codex 等环境中应读取 `NEWSROOM_ANALYSIS_EXECUTOR`、`NEWSROOM_AGENT_KIND` 与 Hook 配置，向用户说明当前分析链路的责任边界（谁提供 API Key、谁触发子进程、JSONL 由谁产出）。
