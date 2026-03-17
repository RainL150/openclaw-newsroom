# OpenClaw Automated News Scanner

<a href="https://t.me/genaispot"><img src="assets/gen-ai-spotlight-logo.jpg" width="120" align="left" style="margin-right: 16px;" /></a>

**See it in action:** This pipeline powers [Gen AI Spotlight](https://t.me/genaispot) on Telegram — a fully automated AI news channel. Join to see what the output looks like in production.

<br clear="left"/>

### Video Walkthroughs

<table>
<tr>
<td width="50%">
<a href="https://youtu.be/2nk5CqrXX9E"><img src="assets/video-thumbnail-1.jpg" width="100%" /></a>
<br/><a href="https://youtu.be/2nk5CqrXX9E">Building the News Scan Pipeline</a>
</td>
<td width="50%">
<a href="https://youtu.be/cvdAqCM1wGs"><img src="assets/video-thumbnail-2.jpg" width="100%" /></a>
<br/><a href="https://youtu.be/cvdAqCM1wGs">Pipeline Deep Dive & Demo</a>
</td>
</tr>
</table>

---

A complete, automated AI news scanning pipeline for [OpenClaw](https://github.com/openclaw/openclaw). Scans 5 data sources every 2 hours, scores and deduplicates results, enriches top articles with full text, and uses Gemini Flash as an AI editor to curate the best stories for your channel.

**Pipeline cost:** ~$5/month (Gemini Flash API + Tavily free tier)

---

## How This Fits Into OpenClaw

This pipeline is designed to run as an **OpenClaw cron job**. Here's how it integrates:

```
OpenClaw Gateway
├── Cron scheduler fires every 2 hours
│   └── Runs news_scan_deduped.sh (the orchestrator)
│       ├── Calls 5 data source scripts (RSS, Reddit, Twitter, GitHub, Tavily)
│       ├── Scores + deduplicates via quality_score.py
│       ├── Enriches top articles via enrich_top_articles.py
│       └── Curates via llm_editor.py (Gemini Flash API)
│
├── Agent receives the pipeline output
│   └── Formats and delivers to your channel (Feishu, Telegram, Slack, etc.)
│
├── Nightly cron (optional)
│   └── Runs update_editorial_profile.py to learn from your approvals/rejections
│
└── memory/ directory
    ├── editorial_profile.md      ← LLM editor reads this for guidance
    ├── editorial_decisions.md    ← Your approval/rejection log
    ├── scanner_presented.md      ← Auto-logged: what was presented
    ├── news_log.md               ← Your posted stories (for dedup)
    ├── last_scan_candidates.txt  ← Persistent for "next 10" requests
    └── github_trending_state.json ← Star velocity tracking
```

**Key integration points:**

1. **Scripts live in** `~/.openclaw/workspace/scripts/` — OpenClaw's standard location for agent-callable scripts
2. **Memory files live in** `~/.openclaw/workspace/memory/` — persistent across sessions
3. **The cron job** uses `sessionTarget: "isolated"` so each scan gets a clean session (no context contamination)
4. **The agent model** orchestrates the pipeline. You can use the agent's default model because the actual AI curation uses Gemini Flash directly via API
5. **Delivery** is handled by OpenClaw's channel system (Feishu, Telegram, Slack, etc.)

**Not using OpenClaw?** The scripts work standalone too — just run `./news_scan_deduped.sh` from a regular cron job or shell. The only OpenClaw-specific parts are the cron job setup and channel delivery.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    news_scan_deduped.sh                          │
│                    (Main Orchestrator)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [1] RSS Feeds          ──→  filter_ai_news.sh (25 feeds)       │
│  [2] Reddit JSON API    ──→  fetch_reddit_news.py (13 subs)     │
│  [3] Twitter/X          ──→  scan_twitter_ai.sh (bird CLI)      │
│                          ──→  fetch_twitter_api.py (API search)  │
│  [4] GitHub             ──→  github_trending.py (trending+rel)  │
│  [5] Tavily Web Search  ──→  fetch_web_news.py (5 queries)      │
│                                                                 │
│  All sources are best-effort — failures don't kill the pipeline │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  quality_score.py   → Score + dedup (80% title similarity)      │
│                       Output: up to 500 scored candidates       │
│                                                                 │
│  enrich_top_articles.py → Fetch full text for scored articles   │
│                           CF Markdown preferred, HTML fallback  │
│                                                                 │
│  llm_editor.py      → Gemini Flash editorial curation           │
│                       Reads editorial_profile.md for guidance   │
│                       Checks news_log.md to avoid repeats       │
│                       Output: sectioned ranked picks (JSON)     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required
- **OpenClaw** (v2026.2.23+) — the AI agent platform that runs the cron job
- **Python 3.9+** — all scripts use stdlib only (no pip packages)
- **blogwatcher** — RSS feed scanner (`brew install blogwatcher` or equivalent). For guided installation, use the OpenClaw skill: [openclaw-skill-blogwatcher](https://github.com/RainL150/openclaw-skill-blogwatcher)

### API Keys (set as environment variables)
| Key | Required? | Purpose | Free Tier |
|-----|-----------|---------|-----------|
| `GEMINI_API_KEY` | Yes | Gemini Flash for LLM editorial curation | Google AI Studio — generous free tier |
| `GH_TOKEN` | Recommended | GitHub API (5000 req/h vs 60/h unauthenticated) | GitHub personal access token (free) |
| `TAVILY_API_KEY` | Optional | Tavily web search for breaking news | 1000 queries/month free |
| `TWITTERAPI_IO_KEY` | Optional | twitterapi.io keyword search supplement | Paid (small monthly fee) |
| `OPENROUTER_API_KEY` | Optional | OpenRouter — access to 200+ LLM models as Gemini fallback | Free credits on sign-up |

### Optional Tools
- **bird** — Twitter/X CLI tool (for `scan_twitter_ai.sh`). Install: `npm install -g @steipete/bird` or `brew install steipete/tap/bird` — see [bird.fast](https://bird.fast). If not installed, the Twitter bird CLI source is skipped gracefully.

---

## Installation

### Step 1: Copy Scripts

Copy all scripts from the `scripts/` directory to your OpenClaw workspace:

```bash
cp scripts/*.sh scripts/*.py ~/.openclaw/workspace/scripts/
chmod +x ~/.openclaw/workspace/scripts/news_scan_deduped.sh
chmod +x ~/.openclaw/workspace/scripts/filter_ai_news.sh
chmod +x ~/.openclaw/workspace/scripts/scan_twitter_ai.sh
```

### Step 2: Set Up RSS Feeds (blogwatcher)

Install blogwatcher and add your RSS feeds. Here's a recommended starter set:

```bash
# Wire services (Tier 1 — highest trust)
blogwatcher add "Reuters Tech" "https://www.reuters.com/technology/rss"
blogwatcher add "Axios AI" "https://api.axios.com/feed/top/technology"

# Tech press (Tier 2)
blogwatcher add "TechCrunch AI" "https://techcrunch.com/category/artificial-intelligence/feed/"
blogwatcher add "The Verge" "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
blogwatcher add "THE DECODER" "https://the-decoder.com/feed/"
blogwatcher add "Ars Technica" "https://feeds.arstechnica.com/arstechnica/technology-lab"
blogwatcher add "VentureBeat AI" "https://venturebeat.com/category/ai/feed/"
blogwatcher add "Wired AI" "https://www.wired.com/feed/tag/ai/latest/rss"
blogwatcher add "MIT Tech Review" "https://www.technologyreview.com/feed/"

# AI company blogs (Tier 1-2)
blogwatcher add "OpenAI Blog" "https://openai.com/blog/rss.xml"
blogwatcher add "Google AI Blog" "https://blog.google/technology/ai/rss/"
blogwatcher add "Hugging Face Blog" "https://huggingface.co/blog/feed.xml"

# Bloggers & newsletters (Tier 2-3)
blogwatcher add "Simon Willison" "https://simonwillison.net/atom/everything/"
blogwatcher add "Bens Bites" "https://www.bensbites.com/feed"
```

Adjust the `SOURCE_TIERS` dictionary in `filter_ai_news.sh` to match your feed names exactly.

### Step 3: Set Up Editorial Profile

Copy and customize the editorial profile template:

```bash
mkdir -p ~/.openclaw/workspace/memory
cp config/editorial_profile_template.md ~/.openclaw/workspace/memory/editorial_profile.md
```

Edit `~/.openclaw/workspace/memory/editorial_profile.md` to reflect your channel's editorial voice:
- What topics you always pick
- What you usually skip
- Your source trust ranking
- Story selection rules

This profile is read by the LLM editor on every scan and directly influences story selection.

### Step 4: Set Environment Variables

Add API keys to your OpenClaw LaunchAgent plist (macOS):

```bash
# Add to ~/Library/LaunchAgents/ai.openclaw.gateway.plist under EnvironmentVariables:
# <key>GEMINI_API_KEY</key>
# <string>your-gemini-api-key</string>
# <key>GH_TOKEN</key>
# <string>your-github-token</string>
# <key>TAVILY_API_KEY</key>
# <string>your-tavily-key</string>
# <key>TWITTERAPI_IO_KEY</key>
# <string>your-twitterapi-key</string>

# Then restart the gateway:
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

Or export them in your shell for testing:

```bash
export GEMINI_API_KEY="your-key"
export GH_TOKEN="your-token"
export TAVILY_API_KEY="your-key"
export TWITTERAPI_IO_KEY="your-key"

# Optional: 配置 LLM 编辑器参数
export MIN_SCORE_THRESHOLD=60      # 最低分数阈值（默认 60，低于此分数的文章会被过滤）
export SECTION_MAX_ITEMS=40        # 每个板块最多文章数（默认 40）
export LLM_BATCH_SIZE=30           # LLM 批次大小（默认 30）

# Optional: 配置输出文件
export NEWSROOM_OUTPUT_DIR="$HOME/.openclaw/workspace/outputs"
export NEWSROOM_TZ="Asia/Shanghai"  # 影响输出文件时间戳
export NEWSROOM_HTML_ENABLED=1      # 是否生成 HTML 报告（默认 1）

# Optional: 手动覆盖输出文件名（通常不需要）
export NEWSROOM_RUN_MD_OUTPUT="$HOME/.openclaw/workspace/outputs/newsroom-run-custom.md"
export NEWSROOM_HTML_OUTPUT="$HOME/.openclaw/workspace/outputs/newsroom-run-custom.html"
export NEWSROOM_RUN_TIMESTAMP="20260305-192427"
```

**输出文件默认规则：**
- 原始输出归档：`$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.md`
- HTML 报告：`$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.html`
- 时间戳默认按 `NEWSROOM_TZ` 生成；若未设置，则默认使用 `Asia/Shanghai`

### Step 5: Create the Cron Job

Add the news scan as an OpenClaw cron job.

**中国时间 + 飞书群示例：**
```bash
openclaw cron add \
  --name "AI News Scan CN" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and archive the original output: bash ~/.openclaw/workspace/scripts/news_scan_deduped.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

**如果你希望在任务结束后额外提示本次 `.md/.html` 归档文件，可以改用包装脚本：**
```bash
openclaw cron add \
  --name "AI News Scan CN With Files" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and show archived file paths: bash ~/.openclaw/workspace/scripts/news_scan_with_files.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

**这条 cron 会做什么：**
- 把脚本标准输出发送到飞书群
- 额外生成 2 份文件：
  - `outputs/newsroom-run-YYYYMMDD-HHMMSS.md`：本次运行的原始输出归档（带时间戳）
  - `outputs/newsroom-run-YYYYMMDD-HHMMSS.html`：本次运行的 HTML 完整报告（带时间戳）
- 在输出里打印这 2 个文件的 `file://` 路径，便于 Agent/人工二次发送

> **注意**：cron 本身稳定保证的是“文本输出会发到飞书群”。`md/html` 文件是否会作为附件自动发到飞书，取决于你的 OpenClaw Agent / 飞书通道是否支持文件发送。如果通道支持识别 `file://` 路径或文件附件发送，就可以一并发出；否则至少会把文件路径和文本摘要发到群里。

**时间说明：**
- `--tz "Asia/Shanghai"` 表示按中国时间执行
- 当前 cron 表达式表示每天北京时间 `09:40 / 11:40 / 13:40 / 15:40 / 17:40 / 19:40 / 21:40`
- 如果你希望输出文件名里的时间戳也使用中国时间，请确保环境变量里设置了 `NEWSROOM_TZ="Asia/Shanghai"`

**Model choice:** You can omit `--model` and let OpenClaw use the default model for the selected agent. The actual AI curation still happens via Gemini Flash API directly (called by `llm_editor.py`), so the cron-side orchestration model is not critical.

### Step 6: Test the Pipeline

Run a manual test:

```bash
cd ~/.openclaw/workspace/scripts
./news_scan_deduped.sh
```

You should see output like:
```
═══════════════════════════════════════════════════════════
  News Scanner v2 (四板块模式)
═══════════════════════════════════════════════════════════

📰 [1/5] Scanning RSS feeds...
  ✅ Extracted 12 new RSS articles
🔴 [2/5] Scanning Reddit (JSON API)...
  ✅ Found 45 Reddit posts (score-filtered)
...
```

---

## How Each Script Works

### 1. `news_scan_deduped.sh` — Main Orchestrator
The master script that calls everything else in sequence. Collects articles from all 5 sources, pipes through scoring/enrichment/LLM, and formats output. All sources are best-effort — if one fails, the pipeline continues with what it has.

### 2. `filter_ai_news.sh` — RSS Keyword Filter
Reads articles from blogwatcher, filters by AI-related keywords (with word-boundary matching for short keywords like "AI" to avoid false positives), assigns source tiers, and filters out Reddit noise (questions, rants, memes).

### 3. `fetch_reddit_news.py` — Reddit JSON API Scanner
Fetches posts from 13 AI-related subreddits using Reddit's public JSON API (no auth needed). Features:
- Per-subreddit score thresholds (30-50 upvotes minimum)
- Flair filtering for noisy subs (e.g., only "News" flair from r/technology)
- Noise filter (skips questions, rants, short titles)
- Concurrent fetching (3 workers)

### 4. `scan_twitter_ai.sh` — Twitter/X bird CLI Scanner
Scans official AI company accounts, tech reporters/leakers, and CEO accounts using the `bird` CLI tool. Three-tier account system:
- Tier 1: Official accounts (OpenAI, Anthropic, Google, etc.)
- Tier 2: Reporters and leakers (break news first)
- Tier 3: CEOs (context, not breaking news)

### 5. `fetch_twitter_api.py` — twitterapi.io Keyword Search
Supplements bird CLI with keyword-based search. Uses engagement filtering (50+ likes or 5000+ followers) to cut noise. Properly tags tweet-only stories (no external article URL).

### 6. `github_trending.py` — GitHub Trending + Releases
Three strategies:
- **Emerging:** Repos created in the last 7 days with 50+ stars
- **Velocity:** Established repos (1000+ stars) gaining traction fast
- **Releases:** New releases from 16 key AI repos (Anthropic SDK, OpenAI SDK, Ollama, etc.)

Maintains state between runs to calculate star velocity.

### 7. `fetch_web_news.py` — Tavily Web Search
Catches breaking news that RSS feeds miss. 5 focused queries, 2-day freshness filter. Skips domains already covered by RSS (Reddit, Twitter, GitHub, YouTube, arxiv). Filters out homepage URLs.

### 8. `quality_score.py` — Scoring + Deduplication
Scores every article based on:
- Source tier (wire services get +5, tech press +3, etc.)
- High-value keywords (acquisitions, billion, launch, security, etc.)
- Breaking news signals (exclusive, confirmed, first look, etc.)
- Title quality (length heuristic)

Deduplicates by title similarity (80% threshold using SequenceMatcher). In the main pipeline it outputs up to 500 scored candidates.

### 9. `enrich_top_articles.py` — Full Text Fetcher
Fetches full article text for scored candidates in the pipeline (currently invoked with `--max 500 --max-chars 1200`). Tries Cloudflare Markdown for Agents first (clean markdown), falls back to HTML extraction. Skips paywalled sites.

### 10. `llm_editor.py` — LLM Editorial Curation
The AI brain of the pipeline. Sends scored candidates + GitHub candidates + editorial profile + recent post history to Gemini Flash. The LLM classifies stories into four sections, assigns scores, writes Chinese summaries, and returns structured JSON.

Features:
- Deterministic URL pre-filter (skips already-posted URLs before calling the LLM)
- Editorial profile integration (learns your preferences over time)
- Four-section output: Model / Application / Infrastructure / Company
- Section summaries for each board
- Section-level dedup is currently disabled to preserve candidate coverage
- Final filtering by `MIN_SCORE_THRESHOLD`
- Structured JSON output with validation
- Graceful fallback to raw scoring if LLM fails
- Logs all presented stories to `scanner_presented.md`

### 11. `update_editorial_profile.py` — Profile Updater
Runs nightly. Analyzes your approval/rejection patterns and updates the editorial profile's stats section. Also identifies "blind spots" — topics you manually seek out but the scanner doesn't catch.

---

## Customization Guide

### Adding RSS Feeds
1. Add the feed to blogwatcher: `blogwatcher add "Feed Name" "https://feed-url/rss"`
2. Add the feed name to `SOURCE_TIERS` in `filter_ai_news.sh` with the appropriate tier (1-3)
3. Add any new keywords to the `LONG_KEYWORDS` list if needed

### Adding Reddit Subreddits
Edit the `SUBREDDITS` list in `fetch_reddit_news.py`:
```python
{"sub": "YourSubreddit", "sort": "hot", "limit": 25, "min_score": 30,
 "flairs": ["News", "Discussion"]},  # flairs are optional
```

### Adding Twitter Accounts to Monitor
Edit the account arrays in `scan_twitter_ai.sh`:
- `OFFICIAL_ACCOUNTS` — for company accounts
- `REPORTER_ACCOUNTS` — for journalists and leakers
- `CEO_ACCOUNTS` — for thought leaders

### Adding GitHub Release Repos
Add to the `RELEASE_REPOS` list in `github_trending.py`:
```python
"owner/repo-name",
```

### Changing the LLM Model
Edit `GEMINI_MODEL` in `llm_editor.py`. Any Gemini model works. Flash is recommended for cost.

### Adjusting Scan Frequency
Edit the cron expression:
```bash
openclaw cron edit <job-id> --cron "0 */3 * * *"  # every 3 hours
```

---

## File Structure

```
openclaw-news-scan/
├── README.md                              # This file
├── scripts/
│   ├── news_scan_deduped.sh              # Main orchestrator
│   ├── news_scan_with_files.sh           # Wrapper that prints archived file paths
│   ├── filter_ai_news.sh                 # RSS keyword filter
│   ├── fetch_reddit_news.py              # Reddit JSON API
│   ├── scan_twitter_ai.sh               # Twitter bird CLI
│   ├── fetch_twitter_api.py              # twitterapi.io search
│   ├── github_trending.py               # GitHub trending + releases
│   ├── fetch_web_news.py                # Tavily web search
│   ├── quality_score.py                 # Scoring + dedup
│   ├── enrich_top_articles.py           # Full text fetcher
│   ├── llm_editor.py                    # LLM editorial curation
│   └── update_editorial_profile.py      # Editorial profile updater
├── outputs/
│   ├── newsroom-run-YYYYMMDD-HHMMSS.md  # Archived raw stdout for each run
│   └── newsroom-run-YYYYMMDD-HHMMSS.html # Archived HTML report for each run
└── config/
    └── editorial_profile_template.md     # Template — customize for your channel
```

---

## Pipeline Flow Summary

```
RSS (25 feeds) ─────────┐
Reddit (13 subs) ───────┤
Twitter (bird + API) ───┤──→ quality_score.py ──→ enrich_top_articles.py ──→ llm_editor.py ──→ Output
GitHub (trending+rel) ──┤       (max 500)             (max 500)            (Gemini Flash)
Tavily (5 queries) ─────┘
```

**Typical run:** ~100 raw articles → dozens/hundreds scored → sectioned LLM picks → raw stdout archive + html output

---

## Cost Breakdown

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Gemini Flash API | ~$2-3/month | ~7 calls/day, ~30K tokens each |
| Tavily API | Free | 1000 queries/month free tier covers it |
| GitHub API | Free | Personal access token, 5000 req/h |
| twitterapi.io | ~$10/month | Optional — bird CLI is free |
| OpenClaw cron model | Varies | Depends on your model choice |
| **Total** | **~$5/month** | Without twitterapi.io |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "GEMINI_API_KEY not set" | Add to LaunchAgent plist or export in shell |
| Reddit 429 (rate limit) | Normal with 2h spacing. Reduce subreddits or increase --hours |
| Reddit 404 on a sub | Sub may be private/quarantined. Remove from config. |
| bird CLI not found | Install bird or remove scan_twitter_ai.sh call |
| "No new stories found" | RSS feeds may all be read. Wait for new articles. |
| LLM editor timeout | Increase TIMEOUT_SEC in llm_editor.py |
| Pipeline takes too long | Increase cron timeout: `openclaw cron edit <id> --timeout 120` |
| GitHub rate limit | Set GH_TOKEN env var for 5000 req/h (vs 60/h) |
| Duplicate stories | Adjust --dedup-threshold in quality_score.py (default 0.80) |

---

## Learning & Feedback Loop

The system learns from your editorial decisions:

1. **During the day:** The scanner presents picks. You approve or skip them.
2. **At night:** `update_editorial_profile.py` analyzes your patterns.
3. **Next scan:** The LLM editor reads the updated profile and adjusts.

To log decisions, create `~/.openclaw/workspace/memory/editorial_decisions.md`:
```
[2026-03-01T10:00:00-05:00] APPROVED | Story Title Here | https://url | category
[2026-03-01T10:00:00-05:00] SKIPPED | Another Story | https://url | category
[2026-03-01T14:00:00-05:00] MANUAL_DRAFT | Story I Found Myself | https://url | category
```

---

## Credits

Built by [Jacob Ben David](https://github.com/jacob-bd) with [OpenClaw](https://github.com/openclaw/openclaw), Gemini Flash, and a collection of free/low-cost APIs.
Inspired by the `tech-news-digest` ClawHub skill (v3.14.0 by dinstein).

## License

MIT — use it however you want. If you build something cool with it, let me know!
