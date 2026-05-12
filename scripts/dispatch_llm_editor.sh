#!/usr/bin/env bash
# dispatch_llm_editor.sh — 按 NEWSROOM_ANALYSIS_EXECUTOR 分发「策编/分析」步骤
#
# 默认 (`llm_api`) 与历史行为一致：直接执行 llm_editor.py（Gemini / OpenRouter API）。
# `agent` 模式下转发给外部 Hook / 内联命令，由 OpenClaw / Claude Code / Codex /
# Cursor / Aider 等任意 agent CLI 包装执行。`NEWSROOM_AGENT_KIND` 用于声明当前
# 是哪种 agent，便于 SKILL.md 与 Hook 内部分支。
#
# 约定：无论何种方式，最终须将 llm_editor 同格式的 JSON 行打印到 stdout
# （由 news_scan_deduped.sh 重定向到 picks 文件）。
#
# 用法（由 news_scan_deduped.sh 调用）：
#   bash dispatch_llm_editor.sh --file <enriched.txt> [--github <github.txt>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export NEWSROOM_SCRIPT_DIR="${NEWSROOM_SCRIPT_DIR:-$SCRIPT_DIR}"

MODE="${NEWSROOM_ANALYSIS_EXECUTOR:-llm_api}"

run_default() {
  exec python3 "$SCRIPT_DIR/llm_editor.py" "$@"
}

# 旧名兼容：openclaw_agent / claude_code 自动映射到 agent + 对应 KIND，
# 同时把旧的 *_HOOK / *_CMD 兜底进 NEWSROOM_AGENT_HOOK / _CMD。
case "$MODE" in
  openclaw_agent)
    MODE=agent
    : "${NEWSROOM_AGENT_KIND:=openclaw}"
    : "${NEWSROOM_AGENT_HOOK:=${NEWSROOM_OPENCLAW_ANALYSIS_HOOK:-}}"
    : "${NEWSROOM_AGENT_CMD:=${NEWSROOM_OPENCLAW_ANALYSIS_CMD:-}}"
    ;;
  claude_code)
    MODE=agent
    : "${NEWSROOM_AGENT_KIND:=claude_code}"
    : "${NEWSROOM_AGENT_HOOK:=${NEWSROOM_CLAUDE_CODE_ANALYSIS_HOOK:-}}"
    : "${NEWSROOM_AGENT_CMD:=${NEWSROOM_CLAUDE_CODE_ANALYSIS_CMD:-}}"
    ;;
esac

export NEWSROOM_AGENT_KIND="${NEWSROOM_AGENT_KIND:-}"

case "$MODE" in
  agent)
    if [ -n "${NEWSROOM_AGENT_HOOK:-}" ] && [ -f "${NEWSROOM_AGENT_HOOK}" ]; then
      exec bash "$NEWSROOM_AGENT_HOOK" "$@"
    elif [ -n "${NEWSROOM_AGENT_CMD:-}" ]; then
      eval "$NEWSROOM_AGENT_CMD"
    else
      run_default "$@"
    fi
    ;;
  llm_api|*)
    run_default "$@"
    ;;
esac
