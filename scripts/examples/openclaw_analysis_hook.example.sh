#!/usr/bin/env bash
# 示例：OpenClaw Agent 侧包装脚本（复制后 chmod +x，并在 .env 设置
# NEWSROOM_ANALYSIS_EXECUTOR=agent
# NEWSROOM_AGENT_KIND=openclaw
# NEWSROOM_AGENT_HOOK=/path/to/openclaw_analysis_hook.sh）
#
# 旧名 NEWSROOM_ANALYSIS_EXECUTOR=openclaw_agent + NEWSROOM_OPENCLAW_ANALYSIS_HOOK
# 仍被 dispatcher 兼容，但新配置推荐使用 agent/KIND/HOOK 三元组。
#
# 将下方 openclaw 调用换成你环境中实际可用的命令；须保证 stdout 与 llm_editor.py
# 一致（JSON 行）。

set -euo pipefail
# 默认仍走本机 API，等价于未使用 Hook；替换为例如：
# exec openclaw run --agent main --message "Run llm_editor with: $*"
exec python3 "${NEWSROOM_SCRIPT_DIR:-$(dirname "$0")/..}/llm_editor.py" "$@"
