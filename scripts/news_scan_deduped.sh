#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# news_scan_deduped.sh — Automated News Scan Pipeline v2
# ═══════════════════════════════════════════════════════════════════
#
# Orchestrates six data sources and pipes them through quality scoring,
# enrichment, and Gemini Flash (llm_editor.py) for AI-powered curation.
#
# Flow:
#   1. RSS via blogwatcher (25 feeds)
#   2. Reddit via JSON API (13 subreddits, score-filtered)
#   3. Twitter via bird CLI + twitterapi.io
#   4. GitHub trending + releases
#   5. Tavily web search (breaking news supplement)
#   6. All → quality_score.py → enrich_top_articles.py → llm_editor.py
#   7. blogwatcher read-all
#
# Usage:
#   ./news_scan_deduped.sh              # default: top 7 picks
#   ./news_scan_deduped.sh --top 5      # top 5 picks
# ═══════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ── Parse arguments ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --top)
      echo "Info: --top 已废弃（当前使用按板块输出，不做全局 Top N 截断）"
      shift 2 ;;
    -h|--help)
      echo "Usage: $0"
      echo "当前版本：按四板块分类并排序输出，不再使用全局 --top。"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Temp files (cleaned up on exit) ─────────────────────────────────
ARTICLES_FILE=$(mktemp /tmp/newscan_articles.XXXXXX)
REDDIT_FILE=$(mktemp /tmp/newscan_reddit.XXXXXX)
TAVILY_FILE=$(mktemp /tmp/newscan_tavily.XXXXXX)
TWITTER_API_FILE=$(mktemp /tmp/newscan_twitterapi.XXXXXX)
SCORED_FILE=$(mktemp /tmp/newscan_scored.XXXXXX)
ENRICHED_FILE=$(mktemp /tmp/newscan_enriched.XXXXXX)
PERSISTENT_CANDIDATES="$SCRIPT_DIR/../memory/last_scan_candidates.txt"
PERSISTENT_GITHUB="$SCRIPT_DIR/../memory/last_scan_github.txt"
GITHUB_FILE=$(mktemp /tmp/newscan_github.XXXXXX)
TWITTER_RAW=$(mktemp /tmp/newscan_twitter.XXXXXX)
PICKS_FILE=$(mktemp /tmp/newscan_picks.XXXXXX)
HTML_ENABLED="${NEWSROOM_HTML_ENABLED:-1}"
HTML_OUTPUT="${NEWSROOM_HTML_OUTPUT:-$SCRIPT_DIR/../outputs/newsroom-latest.html}"

cleanup() {
  rm -f "$ARTICLES_FILE" "$REDDIT_FILE" "$TAVILY_FILE" "$TWITTER_API_FILE" \
        "$SCORED_FILE" "$ENRICHED_FILE" "$GITHUB_FILE" "$TWITTER_RAW" "$PICKS_FILE"
}
trap cleanup EXIT

# ── Counters for stats ───────────────────────────────────────────────
RSS_COUNT=0
REDDIT_COUNT=0
TWITTER_COUNT=0
TWITTER_API_COUNT=0
GITHUB_COUNT=0
TAVILY_COUNT=0
PICKS_COUNT=0

echo "═══════════════════════════════════════════════════════════"
echo "  News Scanner v2 (四板块模式)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ═════════════════════════════════════════════════════════════════════
# SOURCE 1: RSS via blogwatcher (25 feeds)
# ═════════════════════════════════════════════════════════════════════
echo "[1/5] Scanning RSS feeds..."

/usr/local/bin/timeout 90s /usr/local/bin/blogwatcher scan > /dev/null 2>&1 || echo "  Warning: RSS scan timed out (continuing)"

python3 -c '
import sys, subprocess, re

outpath = sys.argv[1]

try:
    result = subprocess.run(
        ["/usr/local/bin/blogwatcher", "articles"],
        capture_output=True, text=True, timeout=30
    )
    raw = result.stdout
except Exception as e:
    print(f"  Warning: Could not run blogwatcher articles: {e}", file=sys.stderr)
    raw = ""

lines = raw.split("\n")
articles = []
i = 0

while i < len(lines):
    line = lines[i].strip()
    m = re.match(r"^\[\d+\]\s+\[new\]\s+(.+)$", line)
    if m:
        title = m.group(1).strip()
        title = title.replace("|", " -")
        source = ""
        url = ""
        for j in range(i + 1, min(i + 5, len(lines))):
            next_line = lines[j].strip()
            if next_line.startswith("Blog:"):
                source = next_line[5:].strip().replace("|", " -")
            elif next_line.startswith("URL:"):
                url = next_line[4:].strip()
        if title and url:
            articles.append(f"{title}|{url}|{source}")
    i += 1

with open(outpath, "w") as f:
    for a in articles:
        f.write(a + "\n")

print(f"  Extracted {len(articles)} new RSS articles", file=sys.stderr)
' "$ARTICLES_FILE"

RSS_COUNT=$(wc -l < "$ARTICLES_FILE" | tr -d ' ')
echo "     Found $RSS_COUNT articles from RSS feeds"

# ═════════════════════════════════════════════════════════════════════
# SOURCE 2: Reddit via JSON API (score-filtered)
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "[2/5] Scanning Reddit (JSON API)..."

if /usr/local/bin/timeout 60s python3 "$SCRIPT_DIR/fetch_reddit_news.py" --hours 24 > "$REDDIT_FILE" 2>/dev/null; then
  REDDIT_COUNT=$(wc -l < "$REDDIT_FILE" | tr -d ' ')
  echo "  Found $REDDIT_COUNT Reddit posts (score-filtered)"
  cat "$REDDIT_FILE" >> "$ARTICLES_FILE"
else
  echo "  Warning: Reddit scan failed (continuing without)"
  REDDIT_COUNT=0
fi

# ═════════════════════════════════════════════════════════════════════
# SOURCE 3: Twitter/X (bird CLI + twitterapi.io)
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "[3/5] Scanning X/Twitter..."

# 3a: bird CLI (primary — account-based)
if /usr/local/bin/timeout 90s "$SCRIPT_DIR/scan_twitter_ai.sh" > "$TWITTER_RAW" 2>&1; then
  echo "  bird CLI scan completed"
else
  echo "  Warning: bird CLI scan timed out or failed (continuing)"
fi

if [ -s "$TWITTER_RAW" ]; then
  TWITTER_COUNT=$(python3 -c '
import sys, re

twitter_file = sys.argv[1]
articles_file = sys.argv[2]
count = 0

with open(twitter_file, "r") as f:
    lines = f.readlines()

with open(articles_file, "a") as out:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(("===", "---", "Scanning", "Tier", "Breaking", "Product", "CEO")):
            continue
        text = line.replace("|", " -")
        urls = re.findall(r"(https?://\S+)", line)
        external_url = ""
        tweet_url = ""
        for u in urls:
            if "x.com/" in u or "twitter.com/" in u or "t.co/" in u:
                if not tweet_url:
                    tweet_url = u
            else:
                if not external_url:
                    external_url = u
        if external_url:
            out.write(f"{text}|{external_url}|X/Twitter\n")
        else:
            url = tweet_url
            out.write(f"{text}|{url}|X/Twitter (tweet)\n")
        count += 1

print(count)
' "$TWITTER_RAW" "$ARTICLES_FILE")
  echo "     bird CLI: $TWITTER_COUNT tweets"
else
  TWITTER_COUNT=0
fi

# 3b: twitterapi.io (supplement — keyword search)
if /usr/local/bin/timeout 30s python3 "$SCRIPT_DIR/fetch_twitter_api.py" --max-queries 2 > "$TWITTER_API_FILE" 2>/dev/null; then
  TWITTER_API_COUNT=$(wc -l < "$TWITTER_API_FILE" | tr -d ' ')
  echo "     twitterapi.io: $TWITTER_API_COUNT tweets"
  cat "$TWITTER_API_FILE" >> "$ARTICLES_FILE"
else
  echo "  Warning: twitterapi.io scan failed (continuing)"
  TWITTER_API_COUNT=0
fi

# ═════════════════════════════════════════════════════════════════════
# SOURCE 4: GitHub Trending + Releases
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "[4/5] Scanning GitHub trending + releases..."

if /usr/local/bin/timeout 45s python3 "$SCRIPT_DIR/github_trending.py" > "$GITHUB_FILE" 2>/dev/null; then
  GITHUB_COUNT=$(wc -l < "$GITHUB_FILE" | tr -d ' ')
  echo "  Found $GITHUB_COUNT trending/release repos"
else
  echo "  Warning: GitHub scan timed out or failed (continuing)"
  GITHUB_COUNT=0
fi

# ═════════════════════════════════════════════════════════════════════
# SOURCE 5: Tavily Web Search (breaking news supplement)
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "[5/5] Tavily web search..."

if /usr/local/bin/timeout 30s python3 "$SCRIPT_DIR/fetch_web_news.py" --max-queries 3 --max-results 5 > "$TAVILY_FILE" 2>/dev/null; then
  TAVILY_COUNT=$(wc -l < "$TAVILY_FILE" | tr -d ' ')
  echo "  Found $TAVILY_COUNT web articles"
  cat "$TAVILY_FILE" >> "$ARTICLES_FILE"
else
  echo "  Warning: Tavily scan failed (continuing)"
  TAVILY_COUNT=0
fi

# ═════════════════════════════════════════════════════════════════════
# QUALITY SCORING PRE-FILTER
# ═════════════════════════════════════════════════════════════════════
echo ""
TOTAL_RAW=$((RSS_COUNT + REDDIT_COUNT + TWITTER_COUNT + TWITTER_API_COUNT + TAVILY_COUNT))
echo "Quality scoring ($TOTAL_RAW candidates)..."

if [ "$TOTAL_RAW" -gt 0 ]; then
  python3 "$SCRIPT_DIR/quality_score.py" --input "$ARTICLES_FILE" --max 500 > "$SCORED_FILE" 2>/dev/null
  SCORED_COUNT=$(wc -l < "$SCORED_FILE" | tr -d ' ')
  echo "  Top $SCORED_COUNT articles after scoring + dedup"
else
  cp "$ARTICLES_FILE" "$SCORED_FILE"
  SCORED_COUNT=0
fi

# ═════════════════════════════════════════════════════════════════════
# ARTICLE ENRICHMENT (full text for top articles)
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "Enriching top articles with full text..."

if [ "$SCORED_COUNT" -gt 0 ]; then
  if /usr/local/bin/timeout 60s python3 "$SCRIPT_DIR/enrich_top_articles.py" --input "$SCORED_FILE" --max 500 --max-chars 1200 > "$ENRICHED_FILE" 2>/dev/null; then
    echo "  Enrichment complete"
  else
    echo "  Warning: Enrichment failed (using scored articles without full text)"
    cp "$SCORED_FILE" "$ENRICHED_FILE"
  fi
else
  cp "$SCORED_FILE" "$ENRICHED_FILE"
fi

# ═════════════════════════════════════════════════════════════════════
# LLM EDITORIAL FILTER (Gemini Flash via llm_editor.py)
# ═════════════════════════════════════════════════════════════════════
echo ""
echo "Running LLM editorial filter (Gemini Flash)..."

TOTAL_CANDIDATES=$((TOTAL_RAW + GITHUB_COUNT))
echo "   Pipeline: ${TOTAL_RAW} raw -> ${SCORED_COUNT:-$TOTAL_RAW} scored -> LLM"

if [ "$TOTAL_CANDIDATES" -eq 0 ]; then
  echo ""
  echo "No new stories found from any source. Nothing to curate."
  exit 0
fi

LLM_CMD="python3 $SCRIPT_DIR/llm_editor.py --file $ENRICHED_FILE"
if [ -s "$GITHUB_FILE" ]; then
  LLM_CMD="$LLM_CMD --github $GITHUB_FILE"
fi

LLM_SUCCESS=true
if eval "$LLM_CMD" > "$PICKS_FILE" 2>/tmp/llm_editor.log; then
  PICKS_COUNT=$(wc -l < "$PICKS_FILE" | tr -d ' ')
  echo "  LLM 已完成分板块排序输出（共 $PICKS_COUNT 条）"
else
  echo "  Warning: LLM editor failed (see /tmp/llm_editor.log)"
  LLM_SUCCESS=false
fi

# ═════════════════════════════════════════════════════════════════════
# FORMAT & DISPLAY OUTPUT
# ═════════════════════════════════════════════════════════════════════
echo ""
cp "$ENRICHED_FILE" "$PERSISTENT_CANDIDATES" 2>/dev/null
cp "$GITHUB_FILE" "$PERSISTENT_GITHUB" 2>/dev/null

echo "═══════════════════════════════════════════════════════════"
echo "  TOP PICKS"
echo "═══════════════════════════════════════════════════════════"
echo ""

if [ "$LLM_SUCCESS" = false ] || [ ! -s "$PICKS_FILE" ]; then
  echo "Warning: LLM curation unavailable — showing raw top articles:"
  echo ""

  # 生成 fallback 的结构化 picks，供后续 HTML 渲染使用
  python3 - << 'PY' "$ENRICHED_FILE" "$PICKS_FILE" "${RAW_FALLBACK_MAX:-20}"
import sys, json
from pathlib import Path

infile = Path(sys.argv[1])
outfile = Path(sys.argv[2])
max_items = int(sys.argv[3])

def infer_section(title, source):
    t = f"{title} {source}".lower()
    if any(k in t for k in ["model", "benchmark", "llm", "gpt", "claude", "llama", "推理", "训练", "权重"]):
        return "模型层面（Model）"
    if any(k in t for k in ["gateway", "infra", "infrastructure", "部署", "latency", "cost", "gpu", "带宽", "存储"]):
        return "基建层面（Infrastructure）"
    if any(k in t for k in ["acquire", "fund", "融资", "并购", "company", "战略", "market", "industry"]):
        return "公司层面（Company/Industry）"
    return "应用层面（Application）"

summary_map = {
    "模型层面（Model）": "一句话总趋势：模型能力竞争转向效率与可控性并重。\n关键词：\n- 降本\n- 推理结构控制\n- Benchmark化\n最大主题：以更低成本获得可用智能\n核心问题：高性能与可部署性的平衡\n典型方向：\n- 小模型高效化\n- 评测标准强化",
    "应用层面（Application）": "一句话总趋势：AI 应用从演示型进入真实工作流闭环。\n关键词：\n- Agent工具化\n- 工作流自动化\n- 端侧落地\n最大主题：提升业务端到端效率\n核心问题：可靠执行与可观测性\n典型方向：\n- 多步骤任务编排\n- 人机协同界面优化",
    "基建层面（Infrastructure）": "一句话总趋势：基建重点从堆算力转向控成本与稳质量。\n关键词：\n- 智能路由\n- Token优化\n- 语义缓存\n最大主题：降低 LLM 总拥有成本\n核心问题：高并发下的性能与费用平衡\n典型方向：\n- 请求分层调度\n- Prompt外部化管理",
    "公司层面（Company/Industry）": "一句话总趋势：产业进入并购整合与生态卡位阶段。\n关键词：\n- 融资并购\n- 战略联盟\n- 行业分化\n最大主题：头部公司重塑价值链\n核心问题：规模扩张与利润模型\n典型方向：\n- 垂直整合\n- 出海与区域化布局",
}

rows = []
if infile.exists():
    for line in infile.read_text(encoding='utf-8', errors='ignore').splitlines():
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 3:
            continue
        title, url, source = parts[0].strip(), parts[1].strip(), parts[2].strip()
        rows.append((title, url, source))

out = []
for i, (title, url, source) in enumerate(rows[:max_items], 1):
    story_type = "github" if "github.com" in url else ("twitter" if ("x.com/" in url or "twitter.com/" in url) else "rss")
    section = infer_section(title, source)
    out.append({
        "rank": i,
        "title": title,
        "url": url,
        "source": source,
        "type": story_type,
        "summary": "（Fallback）当前为降级模式，建议检查 LLM 配置以恢复高质量总结。",
        "category": "other",
        "section": section,
        "score": max(1, 100 - i),
        "section_summary": summary_map[section],
    })

with outfile.open('w', encoding='utf-8') as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
PY

  head -"${RAW_FALLBACK_MAX:-20}" "$ENRICHED_FILE" | while IFS='|' read -r title url source rest; do
    is_tweet=""
    if echo "$source" | grep -q "(tweet)"; then
      is_tweet="yes"
    fi
    if [ -n "$is_tweet" ]; then
      echo "  [推文] $title"
    else
      echo "  * $title"
    fi
    if [ -n "$url" ]; then
      if [ -n "$is_tweet" ]; then
        echo "    推文链接：$url"
      else
        echo "    链接：$url"
      fi
    fi
    source_clean=$(echo "$source" | sed 's/ (tweet)//')
    if [ -n "$source_clean" ]; then
      echo "    来源：$source_clean"
    fi
    echo ""
    echo "---"
    echo ""
  done
else
  python3 -c '
import sys, json
from collections import OrderedDict

picks_file = sys.argv[1]

EMOJI_MAP = {
    "rss": "[article]",
    "twitter": "[tweet]",
    "github": "[github]",
}
SECTION_ORDER = [
    "模型层面（Model）",
    "应用层面（Application）",
    "基建层面（Infrastructure）",
    "公司层面（Company/Industry）",
]

rows = []
with open(picks_file, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

# 全局按分数降序，再按 rank
rows.sort(key=lambda x: (int(x.get("score", 0)), -int(x.get("rank", 0))), reverse=True)

grouped = OrderedDict((k, []) for k in SECTION_ORDER)
for r in rows:
    sec = r.get("section", "应用层面（Application）")
    if sec not in grouped:
        grouped[sec] = []
    grouped[sec].append(r)

for sec in SECTION_ORDER:
    items = grouped.get(sec, [])
    if not items:
        continue
    print(f"## {sec}")
    sec_summary = ""
    for it in items:
        s = it.get("section_summary", "").strip()
        if s:
            sec_summary = s
            break
    if sec_summary:
        print(f"板块总结：{sec_summary}")
    print()

    for idx, pick in enumerate(items):
        rank = pick.get("rank", "?")
        score = pick.get("score", 0)
        title = pick.get("title", "(no title)")
        summary = pick.get("summary", "")
        url = pick.get("url", "")
        source = pick.get("source", "unknown")
        category = pick.get("category", "other")
        story_type = pick.get("type", "rss")
        channel = pick.get("channel", "")

        is_tweet = "(tweet)" in source
        tag = "[tweet]" if is_tweet else EMOJI_MAP.get(story_type, "[article]")

        print(f"{rank}. {tag} {title}（score={score}）")
        if summary:
            print(f"   总结：{summary}")
        if url:
            if is_tweet:
                print(f"   推文链接：{url}")
            else:
                print(f"   链接：{url}")
        source_display = source.replace(" (tweet)", "")
        if channel:
            print(f"   来源：{source_display} [{category}] · 渠道：{channel}")
        else:
            print(f"   来源：{source_display} [{category}]")
        print()
        if idx < len(items) - 1:
            print("---")
            print()

    print("==============================")
    print()
' "$PICKS_FILE"
fi

# ═════════════════════════════════════════════════════════════════════
# OPTIONAL: Render fixed-template HTML report
# Controlled by NEWSROOM_HTML_ENABLED=1
# ═════════════════════════════════════════════════════════════════════
if [ "$HTML_ENABLED" = "1" ] || [ "$HTML_ENABLED" = "true" ]; then
  if [ -s "$PICKS_FILE" ]; then
    if python3 "$SCRIPT_DIR/render_newsroom_html.py" \
      --input "$PICKS_FILE" \
      --output "$HTML_OUTPUT" \
      --title "OpenClaw Newsroom 四板块简报" >/tmp/newsroom_html_path.log 2>/tmp/newsroom_html_err.log; then
      HTML_PATH=$(cat /tmp/newsroom_html_path.log)
      echo "HTML 报告已生成：$HTML_PATH"
    else
      echo "  Warning: HTML 渲染失败（详见 /tmp/newsroom_html_err.log）"
    fi
  else
    echo "跳过 HTML 渲染：当前无 LLM picks（PICKS_FILE 为空）"
  fi
fi

# ═════════════════════════════════════════════════════════════════════
# CLEANUP: Mark articles as read in blogwatcher
# ═════════════════════════════════════════════════════════════════════
echo "Marking RSS articles as read..."
echo "y" | /usr/local/bin/blogwatcher read-all > /dev/null 2>&1 || echo "  Warning: Could not mark articles as read"

# ═════════════════════════════════════════════════════════════════════
# STATS
# ═════════════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════"
echo "Sources: $RSS_COUNT RSS + $REDDIT_COUNT Reddit + $((TWITTER_COUNT + TWITTER_API_COUNT)) Twitter + $GITHUB_COUNT GitHub + $TAVILY_COUNT Tavily"
echo "Pipeline: $TOTAL_CANDIDATES raw -> ${SCORED_COUNT:-N/A} scored -> $PICKS_COUNT curated picks"
echo "═══════════════════════════════════════════════════════════"
