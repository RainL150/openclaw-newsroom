# OpenClaw Newsroom

An OpenClaw skill for scanning AI news from multiple sources, deduplicating and scoring candidates, enriching top stories, and curating a digest with an LLM.

**Sample report:** [newsroom-run-20260317-141349.html](assets/newsroom-run-20260317-141349.html)

## What This Skill Does

- Scans RSS, Reddit, X/Twitter, GitHub, and Tavily web search
- Scores and deduplicates candidates before editorial selection
- Enriches top articles with fuller text for better curation
- Produces archived Markdown and HTML outputs for channel delivery
- Keeps local newsroom memory such as editorial profile and presented items

## Recommended Layout

Install the repository as a skill, not as loose scripts:

```bash
~/.openclaw/workspace/skills/openclaw-newsroom/
```

OpenClaw will only discover it as a formal skill when [`SKILL.md`](/Users/rainless/Desktop/project/claw/openclaw-newsroom/SKILL.md) exists at the skill root.

## Entrypoints

Use the wrapper when you want archived file paths in the output:

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_with_files.sh
```

Use the raw pipeline when you only need the digest text:

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_deduped.sh
```

## Quick Start

1. Install the skill:

```bash
mkdir -p ~/.openclaw/workspace/skills
cp -R openclaw-newsroom ~/.openclaw/workspace/skills/openclaw-newsroom
chmod +x ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/*.sh
```

2. Create the local config:

```bash
cp ~/.openclaw/workspace/skills/openclaw-newsroom/.env.example \
  ~/.openclaw/workspace/skills/openclaw-newsroom/.env
```

3. Create the editorial profile:

```bash
mkdir -p ~/.openclaw/workspace/skills/openclaw-newsroom/memory
cp ~/.openclaw/workspace/skills/openclaw-newsroom/config/editorial_profile_template.md \
  ~/.openclaw/workspace/skills/openclaw-newsroom/memory/editorial_profile.md
```

4. Run a manual scan:

```bash
cd ~/.openclaw/workspace/skills/openclaw-newsroom
bash scripts/news_scan_with_files.sh
```

## Required and Optional Dependencies

Required:

- OpenClaw `v2026.2.23+`
- Python `3.9+`
- One LLM path: `GEMINI_API_KEY` or `OPENROUTER_API_KEY`

Recommended:

- `blogwatcher` for RSS coverage
- `GH_TOKEN` for GitHub API limits

Optional:

- `TAVILY_API_KEY` for web search supplements
- `TWITTERAPI_IO_KEY` for keyword-based X/Twitter search
- `bird` CLI for account-based X/Twitter scanning

## Runtime Conventions

- Default outputs live under `outputs/`
- Default memory lives under `memory/`
- A sibling `.env` file is auto-loaded by the shell entrypoints
- Source failures are best-effort and should not abort the whole run
- If `llm_editor.py` fails, the pipeline can still complete with a raw-top-articles fallback

## Cron Example

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

## Repository Layout

```text
openclaw-newsroom/
├── SKILL.md
├── agents/openai.yaml
├── config/editorial_profile_template.md
├── scripts/
├── assets/
└── references/
```

## Detailed References

- English operations guide: [references/ops.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/references/ops.md)
- Chinese operations guide: [references/ops.zh.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/references/ops.zh.md)
- Skill metadata: [SKILL.md](/Users/rainless/Desktop/project/claw/openclaw-newsroom/SKILL.md)
- UI-facing metadata: [agents/openai.yaml](/Users/rainless/Desktop/project/claw/openclaw-newsroom/agents/openai.yaml)

## Notes

- Legacy copy-to-`workspace/scripts` installs still work, but they are no longer the recommended packaging.
- Runtime state is intentionally ignored via [`.gitignore`](/Users/rainless/Desktop/project/claw/openclaw-newsroom/.gitignore).
