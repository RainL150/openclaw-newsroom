# OpenClaw Automated News Scanner

<img width="1103" height="820" alt="image" src="https://github.com/user-attachments/assets/a39fe3a3-0468-4f67-ac08-0080b4ebbd4a" />

An automated AI news pipeline that runs as an OpenClaw cron job — scanning 5 sources, scoring + deduplicating, enriching with full text, and curating via Gemini Flash into a sectioned daily digest.

**Sample output:** [newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

---

## How It Fits Into OpenClaw

```
OpenClaw Gateway
├── Cron scheduler (e.g. every 2 hours)
│   └── Runs news_scan_deduped.sh
│       ├── Fetches from 5 sources (RSS, Reddit, Twitter, GitHub, Tavily)
│       ├── Scores + deduplicates via quality_score.py
│       ├── Enriches top articles via enrich_top_articles.py
│       └── Curates via llm_editor.py (Gemini Flash API)
│
├── Agent formats and delivers to your channel (Feishu, Telegram, Slack, etc.)
│
├── Nightly cron (optional)
│   └── Runs update_editorial_profile.py to learn from approvals/rejections
│
└── memory/ directory
    ├── editorial_profile.md        ← LLM editor reads this for guidance
    ├── editorial_decisions.md      ← Your approval/rejection log
    ├── scanner_presented.md        ← Auto-logged: what was presented
    ├── news_log.md                 ← Your posted stories (for dedup)
    ├── last_scan_candidates.txt    ← Persistent for "next 10" requests
    └── github_trending_state.json  ← Star velocity tracking
```

**Key integration points:**

1. Scripts live in `~/.openclaw/workspace/scripts/` — OpenClaw's standard location
2. Memory files live in `~/.openclaw/workspace/memory/` — persistent across sessions
3. The cron job uses `sessionTarget: "isolated"` for a clean session per scan
4. The agent orchestrates the pipeline; actual AI curation uses Gemini Flash directly
5. Delivery is handled by OpenClaw's channel system

> **Not using OpenClaw?** The scripts work standalone too — just run `./news_scan_deduped.sh` from a regular cron job or shell.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    news_scan_deduped.sh                          │
│                    (Main Orchestrator)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [1] RSS Feeds          ──→  filter_ai_news.sh  (25 feeds)      │
│  [2] Reddit JSON API    ──→  fetch_reddit_news.py (13 subs)     │
│  [3] Twitter/X (bird)   ──→  scan_twitter_ai.sh                 │
│      Twitter/X (API)    ──→  fetch_twitter_api.py               │
│  [4] GitHub             ──→  github_trending.py                 │
│  [5] Tavily Web Search  ──→  fetch_web_news.py  (5 queries)     │
│                                                                  │
│  All sources are best-effort — failures don't kill the pipeline  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  quality_score.py       → Score + dedup (80% title similarity)  │
│                           Output: up to 500 scored candidates   │
│                                                                  │
│  enrich_top_articles.py → Fetch full text (CF Markdown / HTML)  │
│                                                                  │
│  llm_editor.py          → Gemini Flash editorial curation       │
│                           Reads editorial_profile.md            │
│                           Checks news_log.md to avoid repeats   │
│                           Output: sectioned JSON picks          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required
- **OpenClaw** v2026.2.23+
- **Python 3.9+** — all scripts use stdlib only (no pip packages needed)
- **blogwatcher** — RSS feed scanner. Install via `brew install blogwatcher` or follow the guided setup: [openclaw-skill-blogwatcher](https://github.com/RainL150/openclaw-skill-blogwatcher)

### API Keys

| Key | Required? | Purpose | Free Tier |
|-----|-----------|---------|-----------|
| `GEMINI_API_KEY` | Yes | Gemini Flash for LLM curation | Google AI Studio — generous free tier |
| `OPENROUTER_API_KEY` | Alt to Gemini | 200+ model fallback via OpenRouter | Free credits on sign-up |
| `GH_TOKEN` | Recommended | GitHub API (5000 req/h vs 60/h) | GitHub personal access token |
| `TAVILY_API_KEY` | Optional | Tavily web search for breaking news | 1000 queries/month free |
| `TWITTERAPI_IO_KEY` | Optional | twitterapi.io keyword search | Paid (~$10/month) |

### Optional Tools
- **bird** — Twitter/X CLI for `scan_twitter_ai.sh`. Install: `npm install -g @steipete/bird` or `brew install steipete/tap/bird`. If not installed, the Twitter bird CLI source is gracefully skipped. bird auto-reads Chrome cookies for auth — no manual token setup required.

---

## Installation

### Step 1: Copy Scripts

```bash
cp scripts/*.sh scripts/*.py ~/.openclaw/workspace/scripts/
chmod +x ~/.openclaw/workspace/scripts/news_scan_deduped.sh
chmod +x ~/.openclaw/workspace/scripts/filter_ai_news.sh
chmod +x ~/.openclaw/workspace/scripts/scan_twitter_ai.sh
```

### Step 2: Set Up RSS Feeds

Install blogwatcher and add your feeds. Recommended starter set:

```bash
# Wire services (Tier 1)
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

Then update the `SOURCE_TIERS` dictionary in `filter_ai_news.sh` to match your feed names.

### Step 3: Set Up Editorial Profile

```bash
mkdir -p ~/.openclaw/workspace/memory
cp config/editorial_profile_template.md ~/.openclaw/workspace/memory/editorial_profile.md
```

Edit `editorial_profile.md` to reflect your channel's voice: topics to always pick, topics to skip, source trust ranking, and story selection rules. This is read by the LLM editor on every scan.

### Step 4: Set Environment Variables

**Recommended: `.env` file** (works for both manual runs and cron jobs)

`news_scan_deduped.sh` automatically loads `~/.openclaw/workspace/.env` on startup, so cron jobs and interactive shells behave identically.

```bash
# ~/.openclaw/workspace/.env
GEMINI_API_KEY=your-key
GH_TOKEN=your-token
TAVILY_API_KEY=your-key
TWITTERAPI_IO_KEY=your-key

# LLM editor tuning (optional)
MIN_SCORE_THRESHOLD=60      # Filter articles below this score (default: 60)
SECTION_MAX_ITEMS=40        # Max articles per section (default: 40)
LLM_BATCH_SIZE=30           # LLM batch size (default: 30)

# Output settings (optional)
NEWSROOM_OUTPUT_DIR=/Users/you/.openclaw/workspace/outputs
NEWSROOM_TZ=Asia/Shanghai   # Timezone for output file timestamps
NEWSROOM_HTML_ENABLED=1     # Generate HTML report (default: 1)
```

> `.env` is listed in `.gitignore` and will not be committed.

**Default output files:**
- Raw archive: `$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.md`
- HTML report: `$NEWSROOM_OUTPUT_DIR/newsroom-run-YYYYMMDD-HHMMSS.html`

### Step 5: Create the Cron Job

Basic setup (Feishu, China timezone):

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

To also surface the archived `.md`/`.html` file paths in the output, use the wrapper script instead:

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

The cron above runs at **09:40 / 11:40 / 13:40 / 15:40 / 17:40 / 19:40 / 21:40 CST** and:
- Sends pipeline text output to Feishu
- Archives two files per run: `.md` (raw stdout) and `.html` (full report)
- Prints `file://` paths in the output for easy forwarding

> **Note:** Whether the `.md`/`.html` files are auto-attached in Feishu depends on your OpenClaw channel configuration. At minimum, the file paths and text summary will be posted.

To adjust frequency: `openclaw cron edit <job-id> --cron "0 */3 * * *"`

**Model:** Omit `--model` to use the agent's default. The actual AI curation always uses Gemini Flash via API directly (`llm_editor.py`), so the orchestration model is not critical.

### Step 6: Test the Pipeline

```bash
cd ~/.openclaw/workspace/scripts
./news_scan_deduped.sh
```

Expected output:
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

## Scripts Reference

| Script | Role |
|--------|------|
| `news_scan_deduped.sh` | Main orchestrator — calls all sources, pipes through scoring/enrichment/LLM |
| `filter_ai_news.sh` | RSS keyword filter with word-boundary matching; assigns source tiers |
| `fetch_reddit_news.py` | Reddit public JSON API; 13 subs, score thresholds, flair filtering, 3 concurrent workers |
| `scan_twitter_ai.sh` | bird CLI; 3-tier account system (official accounts, reporters, CEOs); bird auto-auths via Chrome cookies |
| `fetch_twitter_api.py` | twitterapi.io keyword search; engagement filtering (50+ likes or 5000+ followers) |
| `github_trending.py` | GitHub emerging repos (7d, 50+ stars), velocity tracking, releases from 16 key AI repos |
| `fetch_web_news.py` | Tavily web search; 5 queries, 2-day freshness, skips RSS-covered domains |
| `quality_score.py` | Scores by source tier, keywords, breaking signals; deduplicates at 80% title similarity |
| `enrich_top_articles.py` | Full text fetch (CF Markdown preferred, HTML fallback); skips paywalled sites |
| `llm_editor.py` | Gemini Flash curation; 4-section output (Model / Application / Infrastructure / Company) |
| `update_editorial_profile.py` | Nightly; analyzes approval/rejection patterns and updates editorial profile |
| `news_scan_with_files.sh` | Wrapper around main orchestrator — prints archived file paths after run |

---

## File Structure

```
openclaw-newsroom/
├── README.md
├── scripts/
│   ├── news_scan_deduped.sh
│   ├── news_scan_with_files.sh
│   ├── filter_ai_news.sh
│   ├── fetch_reddit_news.py
│   ├── scan_twitter_ai.sh
│   ├── fetch_twitter_api.py
│   ├── github_trending.py
│   ├── fetch_web_news.py
│   ├── quality_score.py
│   ├── enrich_top_articles.py
│   ├── llm_editor.py
│   └── update_editorial_profile.py
├── outputs/
│   ├── newsroom-run-YYYYMMDD-HHMMSS.md
│   └── newsroom-run-YYYYMMDD-HHMMSS.html
└── config/
    └── editorial_profile_template.md
```

---

## Pipeline Flow

```
RSS (25 feeds) ─────────┐
Reddit (13 subs) ───────┤
Twitter (bird + API) ───┼──→ quality_score.py ──→ enrich_top_articles.py ──→ llm_editor.py ──→ Output
GitHub (trending+rel) ──┤       (max 500)              (max 500)            (Gemini Flash)
Tavily (5 queries) ─────┘
```

Typical run: ~100 raw articles → hundreds scored candidates → 4-section LLM picks → `.md` + `.html` archive

---

## Cost

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Gemini Flash API | ~$2–3 | ~7 calls/day, ~30K tokens each |
| Tavily API | Free | 1000 queries/month covers typical usage |
| GitHub API | Free | Personal access token |
| twitterapi.io | ~$10 | Optional — bird CLI is free |
| OpenClaw cron model | Varies | Depends on your model choice |
| **Total** | **~$5/month** | Without twitterapi.io |

---

## Customization

**RSS:** Add to blogwatcher, then add the name to `SOURCE_TIERS` in `filter_ai_news.sh`.

**Reddit:** Edit `SUBREDDITS` in `fetch_reddit_news.py`:
```python
{"sub": "YourSubreddit", "sort": "hot", "limit": 25, "min_score": 30, "flairs": ["News"]},
```

**Twitter accounts:** Edit `OFFICIAL_ACCOUNTS`, `REPORTER_ACCOUNTS`, or `CEO_ACCOUNTS` in `scan_twitter_ai.sh`.

**GitHub releases:** Add to `RELEASE_REPOS` in `github_trending.py`:
```python
"owner/repo-name",
```

**LLM model:** Edit `GEMINI_MODEL` in `llm_editor.py` (Flash recommended for cost).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `GEMINI_API_KEY not set` | Add to LaunchAgent plist or export in shell |
| Reddit 429 (rate limit) | Normal with short intervals — reduce subreddits or increase `--hours` |
| Reddit 404 on a sub | Sub is private/quarantined — remove from config |
| `bird` CLI not found | Install bird or remove `scan_twitter_ai.sh` from orchestrator |
| Twitter returns 0 tweets | Make sure you are logged into x.com in Chrome — bird reads cookies automatically, no manual token setup needed |
| No new stories found | RSS feeds are up to date — wait for new articles |
| LLM editor timeout | Increase `TIMEOUT_SEC` in `llm_editor.py` |
| Pipeline too slow | Increase cron timeout: `openclaw cron edit <id> --timeout 120` |
| GitHub rate limit | Set `GH_TOKEN` for 5000 req/h (vs 60/h unauthenticated) |
| Duplicate stories | Adjust `--dedup-threshold` in `quality_score.py` (default: 0.80) |

---

## Learning & Feedback Loop

1. **During the day:** Scanner presents picks. You approve or skip.
2. **Nightly:** `update_editorial_profile.py` analyzes your patterns.
3. **Next scan:** LLM editor reads the updated profile and adjusts.

To log decisions, create `~/.openclaw/workspace/memory/editorial_decisions.md`:
```
[2026-03-01T10:00:00+08:00] APPROVED | Story Title | https://url | category
[2026-03-01T10:00:00+08:00] SKIPPED  | Another Story | https://url | category
[2026-03-01T14:00:00+08:00] MANUAL_DRAFT | Story I Found Myself | https://url | category
```

---

## Credits

Built with [OpenClaw](https://github.com/openclaw/openclaw), Gemini Flash, and a collection of free/low-cost APIs.
Inspired by the `tech-news-digest` ClawHub skill (v3.14.0 by dinstein).

## License

MIT — use it however you want.
