---
name: openclaw-newsroom
description: Run or maintain an OpenClaw AI newsroom skill that scans multiple sources, deduplicates candidates, curates a digest with an LLM, and writes archived Markdown and HTML reports.
---

# OpenClaw Newsroom

Use this skill when the user wants to:

- run the AI news scan pipeline
- install or package the newsroom as a formal OpenClaw skill
- tune feeds, scoring, editorial profile, or cron wiring
- diagnose partial failures such as LLM editor fallback behavior

## Default workflow

1. Treat this folder as the skill root, normally at `~/.openclaw/workspace/skills/openclaw-newsroom/`.
2. Prefer the wrapper entrypoint when the user wants archived file paths:

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_with_files.sh
```

3. Use the raw pipeline entrypoint when only the digest text is needed:

```bash
bash ~/.openclaw/workspace/skills/openclaw-newsroom/scripts/news_scan_deduped.sh
```

4. Expect outputs under `outputs/` and persistent state under `memory/` unless overridden by env vars.

## Before running

- Check `.env` or environment variables for at least one LLM path: `GEMINI_API_KEY` or `OPENROUTER_API_KEY`.
- Check whether `blogwatcher` is installed if RSS coverage matters.
- Ensure `config/editorial_profile_template.md` has been copied to `memory/editorial_profile.md` for stable curation.

## Operational notes

- The pipeline is best-effort by source. Individual source failures should not abort the full run.
- If `llm_editor.py` fails, the overall run can still succeed via raw top-articles fallback. Treat that as degraded curation, not a total failure.
- For cron or channel delivery, prefer `news_scan_with_files.sh` because it prints the archived `.md` and `.html` paths.

## References

- Read `references/ops.md` for English installation and cron details.
- Read `references/ops.zh.md` for Chinese installation and cron details.
- Use `README.md` or `README.zh.md` for the short public overview.
- Edit scripts in `scripts/` directly when changing runtime behavior.
