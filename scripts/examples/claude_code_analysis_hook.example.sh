#!/usr/bin/env bash
# 示例：Claude Code / 本地开发机包装脚本（复制后 chmod +x，并在 .env 设置
# NEWSROOM_ANALYSIS_EXECUTOR=agent
# NEWSROOM_AGENT_KIND=claude_code
# NEWSROOM_AGENT_HOOK=/path/to/claude_code_analysis_hook.sh）
#
# 旧名 NEWSROOM_ANALYSIS_EXECUTOR=claude_code + NEWSROOM_CLAUDE_CODE_ANALYSIS_HOOK
# 仍被 dispatcher 兼容，但新配置推荐使用 agent/KIND/HOOK 三元组。
#
# 典型用途：在运行前 source 额外密钥、或固定 LLM_PROVIDER / 模型环境变量后再调
# llm_editor。

set -euo pipefail
# 可按需取消注释：
# export LLM_PROVIDER=openrouter
# export OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
exec python3 "${NEWSROOM_SCRIPT_DIR:-$(dirname "$0")/..}/llm_editor.py" "$@"
