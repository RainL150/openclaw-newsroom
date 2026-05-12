#!/usr/bin/env bash
# 示例：OpenAI Codex CLI 包装脚本（复制后 chmod +x，并在 .env 设置
# NEWSROOM_ANALYSIS_EXECUTOR=agent
# NEWSROOM_AGENT_KIND=codex
# NEWSROOM_AGENT_HOOK=/path/to/codex_analysis_hook.sh）
#
# 思路：把 llm_editor 的调用外包给 codex CLI，让它在自己的 sandbox 里跑。
# 由 codex 内部决定使用哪个模型 / API Key；本脚本只需要把 JSONL 原样
# 透传到 stdout（news_scan_deduped.sh 会把 stdout 重定向到 picks 文件）。

set -euo pipefail

# 默认回落：直接调 llm_editor.py，相当于未启用 Codex Hook。
# 替换为类似下面的 codex 调用（具体子命令以本机 codex 版本为准）：
#
#   exec codex exec --json \
#     --instruction "Run llm_editor.py with args: $*, print JSONL to stdout only."
#
# 或者先让 codex 干一些前置工作（选 API Key / 模型），再回落到本机 llm_editor：
#
#   codex exec --instruction "Ensure OPENROUTER_API_KEY is exported from keychain."
#   exec python3 "${NEWSROOM_SCRIPT_DIR:-$(dirname "$0")/..}/llm_editor.py" "$@"

exec python3 "${NEWSROOM_SCRIPT_DIR:-$(dirname "$0")/..}/llm_editor.py" "$@"
