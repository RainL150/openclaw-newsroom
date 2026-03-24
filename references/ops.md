# Operations Guide

## Installation

Recommended skill layout:

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -R openclaw-newsroom ~/.openclaw/workspace/skills/openclaw-newsroom
chmod +x ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/*.sh
```

Legacy copy-to-scripts mode still works:

```bash
cp scripts/*.sh scripts/*.py ~/.openclaw/workspace/scripts/
chmod +x ~/.openclaw/workspace/scripts/news_scan_deduped.sh
chmod +x ~/.openclaw/workspace/scripts/filter_ai_news.sh
chmod +x ~/.openclaw/workspace/scripts/scan_twitter_ai.sh
```

## Editorial Profile

```bash
mkdir -p ~/.openclaw/workspace/skills/openclaw-newsroom/memory
cp ~/.openclaw/workspace/skills/openclaw-newsroom/config/editorial_profile_template.md \
  ~/.openclaw/workspace/skills/openclaw-newsroom/memory/editorial_profile.md
```

Use the profile to define:

- always-pick topics
- skip topics
- source trust preferences
- story selection rules

## Environment Variables

Create `.env` next to the skill root:

```bash
cp ~/.openclaw/workspace/skills/openclaw-newsroom/.env.example \
  ~/.openclaw/workspace/skills/openclaw-newsroom/.env
```

Common settings:

```bash
GEMINI_API_KEY=your-key
GH_TOKEN=your-token
TAVILY_API_KEY=your-key
TWITTERAPI_IO_KEY=your-key

MIN_SCORE_THRESHOLD=60
SECTION_MAX_ITEMS=40
LLM_BATCH_SIZE=30

NEWSROOM_OUTPUT_DIR=/Users/you/.openclaw/workspace/skills/openclaw-newsroom/outputs
NEWSROOM_MEMORY_DIR=/Users/you/.openclaw/workspace/skills/openclaw-newsroom/memory
NEWSROOM_TZ=Asia/Shanghai
NEWSROOM_HTML_ENABLED=1
```

At least one LLM path should be configured:

- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`

## RSS Setup

Install `blogwatcher` and add feeds that match the names in `scripts/filter_ai_news.sh`.

Starter feeds:

```bash
blogwatcher add "Reuters Tech" "https://www.reuters.com/technology/rss"
blogwatcher add "Axios AI" "https://api.axios.com/feed/top/technology"
blogwatcher add "TechCrunch AI" "https://techcrunch.com/category/artificial-intelligence/feed/"
blogwatcher add "The Verge" "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
blogwatcher add "THE DECODER" "https://the-decoder.com/feed/"
blogwatcher add "Ars Technica" "https://feeds.arstechnica.com/arstechnica/technology-lab"
blogwatcher add "VentureBeat AI" "https://venturebeat.com/category/ai/feed/"
blogwatcher add "Wired AI" "https://www.wired.com/feed/tag/ai/latest/rss"
blogwatcher add "MIT Tech Review" "https://www.technologyreview.com/feed/"
blogwatcher add "OpenAI Blog" "https://openai.com/blog/rss.xml"
blogwatcher add "Google AI Blog" "https://blog.google/technology/ai/rss/"
blogwatcher add "Hugging Face Blog" "https://huggingface.co/blog/feed.xml"
blogwatcher add "Simon Willison" "https://simonwillison.net/atom/everything/"
blogwatcher add "Bens Bites" "https://www.bensbites.com/feed"
```

## Manual Run

```bash
cd ~/.openclaw/workspace/skills/openclaw-newsroom
bash scripts/news_scan_with_files.sh
```

## Cron Examples

Raw pipeline:

```bash
openclaw cron add \
  --name "AI News Scan CN" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and archive the original output: bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_deduped.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

Wrapper with file paths:

```bash
openclaw cron add \
  --name "AI News Scan CN With Files" \
  --cron "40 9,11,13,15,17,19,21 * * *" \
  --message "Run the Gen AI news scanner and show archived file paths: bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_with_files.sh" \
  --agent main \
  --announce \
  --channel feishu \
  --tz "Asia/Shanghai"
```

## Behavior and Failure Modes

- Source collection is best-effort.
- Missing `blogwatcher`, `bird`, or optional API keys reduces coverage but should not stop the run.
- `llm_editor.py` may fail independently; if that happens, the pipeline can still succeed using a raw fallback.
- The wrapper prints `file://` links for the archived Markdown and HTML artifacts when available.
