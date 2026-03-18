#!/bin/bash
# news_scan_with_files.sh
# 包装脚本：运行新闻扫描，并在结束后提示本次归档文件路径

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 显式加载 .env（保证 cron / 非交互 shell 下也能获取环境变量）
set -a
[ -f "$SCRIPT_DIR/../.env" ] && source "$SCRIPT_DIR/../.env"
set +a

OUTPUT_DIR="${NEWSROOM_OUTPUT_DIR:-$SCRIPT_DIR/../outputs}"
RUN_TIMESTAMP="${NEWSROOM_RUN_TIMESTAMP:-$(TZ="${NEWSROOM_TZ:-Asia/Shanghai}" date '+%Y%m%d-%H%M%S')}"
RAW_MD_OUTPUT="${NEWSROOM_RUN_MD_OUTPUT:-$OUTPUT_DIR/newsroom-run-${RUN_TIMESTAMP}.md}"
HTML_OUTPUT="${NEWSROOM_HTML_OUTPUT:-$OUTPUT_DIR/newsroom-run-${RUN_TIMESTAMP}.html}"
PREVIEW_LINES="${NEWSROOM_FILE_PREVIEW_LINES:-30}"
export NEWSROOM_RUN_TIMESTAMP="$RUN_TIMESTAMP"

# 运行主扫描脚本
echo "开始新闻扫描..."
"$SCRIPT_DIR/news_scan_deduped.sh" "$@"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📎 本次运行归档文件"
echo "═══════════════════════════════════════════════════════════"
echo "时间戳：$RUN_TIMESTAMP"

if [ -f "$RAW_MD_OUTPUT" ]; then
    echo "原始输出：file://$RAW_MD_OUTPUT"
else
    echo "原始输出：未找到 $RAW_MD_OUTPUT"
fi

if [ -f "$HTML_OUTPUT" ]; then
    echo "HTML 报告：file://$HTML_OUTPUT"
else
    echo "HTML 报告：未生成（可能关闭了 NEWSROOM_HTML_ENABLED 或渲染失败）"
fi

if [ -f "$HTML_OUTPUT" ]; then
    echo ""
    echo "HTML 内容预览："
    echo "---"
    sed -n "1,${PREVIEW_LINES}p" "$HTML_OUTPUT" || true
    echo "---"
fi

echo ""
echo "💡 如果通道支持 file:// 文件发送，可直接发送以上路径。"
echo "═══════════════════════════════════════════════════════════"
