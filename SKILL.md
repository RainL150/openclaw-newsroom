---
name: openclaw-newsroom
description: Run or maintain an OpenClaw AI newsroom skill that scans multiple sources, deduplicates candidates, curates a digest with an LLM, and writes archived Markdown and HTML reports. LLM curation is configurable via NEWSROOM_ANALYSIS_EXECUTOR (llm_api, agent) with NEWSROOM_AGENT_KIND naming the helper (openclaw, claude_code, codex, ...) and optional hooks; see references/analysis_execution.zh.md.
---

# OpenClaw Newsroom

Use this skill when the user wants to:

- run the AI news scan pipeline
- install or package the newsroom as a formal OpenClaw skill
- tune feeds, scoring, editorial profile, or cron wiring
- diagnose partial failures such as LLM editor fallback behavior
- **configure whether LLM curation runs as direct API (`llm_api`) or is wrapped by an agent CLI (`agent` + `NEWSROOM_AGENT_KIND` of `openclaw` / `claude_code` / `codex` / `cursor` / `aider` / `hermes` / ...)**

## Analysis execution (configurable)

The pipeline step that classifies, scores, and summarizes candidates is implemented by `scripts/llm_editor.py`. **How** it is invoked is controlled by `NEWSROOM_ANALYSIS_EXECUTOR` in `.env` (see `.env.example`).

| Mode | Intended context | Default behavior | Optional override |
|------|------------------|------------------|-------------------|
| `llm_api` | Cron / unattended / same shell as scan | Run `python3 llm_editor.py` | — |
| `agent` | Any agent CLI host (OpenClaw, Claude Code, Codex, Cursor, Aider, Hermes, ...) | Same as `llm_api` unless hook set | `NEWSROOM_AGENT_HOOK` or `NEWSROOM_AGENT_CMD`; `NEWSROOM_AGENT_KIND` declares which agent |

Legacy values `openclaw_agent` and `claude_code` are still accepted and auto-mapped to `agent` with the corresponding `NEWSROOM_AGENT_KIND`; old `NEWSROOM_OPENCLAW_ANALYSIS_HOOK` / `NEWSROOM_CLAUDE_CODE_ANALYSIS_HOOK` (and `_CMD`) variables continue to work.

**Assistant behavior:** Read the user’s `.env` (or ask) for `NEWSROOM_ANALYSIS_EXECUTOR`, `NEWSROOM_AGENT_KIND`, and any `NEWSROOM_AGENT_HOOK` / `_CMD`. Branch your responsibility-boundary explanation on `NEWSROOM_AGENT_KIND` (e.g. for `codex`, point at `~/.codex/auth.json`; for `openclaw`, point at the OpenClaw config). If hooks are set, remind the user that **stdout must remain JSON lines** compatible with `llm_editor.py` (the shell redirect depends on it). Point implementers to `references/analysis_execution.zh.md` for Chinese detail and `scripts/examples/*.example.sh` for starter hooks.

`news_scan_deduped.sh` calls `scripts/dispatch_llm_editor.sh`, which dispatches by executor and exports `NEWSROOM_SCRIPT_DIR`, `NEWSROOM_ENRICHED_FILE`, `NEWSROOM_GITHUB_FILE`, and `NEWSROOM_AGENT_KIND` for use inside custom commands.

## Default workflow

1. Use the "Base directory for this skill" path shown above as the working directory.
2. Prefer the wrapper entrypoint when the user wants archived file paths:

```bash
bash scripts/news_scan_with_files.sh
```

3. Use the raw pipeline entrypoint when only the digest text is needed:

```bash
bash scripts/news_scan_deduped.sh
```

4. Expect outputs under `outputs/` and persistent state under `memory/` (relative to skill root) unless overridden by env vars.

## Before running

- Check `.env` or environment variables for at least one LLM path: `GEMINI_API_KEY` or `OPENROUTER_API_KEY` (when using default `llm_api` / unhooked modes).
- Check whether `blogwatcher` is installed if RSS coverage matters.
- Ensure `config/editorial_profile_template.md` has been copied to `memory/editorial_profile.md` for stable curation.
- If using `agent` mode (or legacy `openclaw_agent` / `claude_code`) with a custom hook, verify the hook prints valid JSON lines to stdout.

## Operational notes

- The pipeline is best-effort by source. Individual source failures should not abort the full run.
- If `llm_editor.py` fails, the overall run can still succeed via raw top-articles fallback. Treat that as degraded curation, not a total failure.
- For cron or channel delivery, prefer `news_scan_with_files.sh` because it prints the archived `.md` and `.html` paths.

## References

- Read `references/ops.md` for English installation and cron details.
- Read `references/ops.zh.md` for Chinese installation and cron details.
- Read `references/analysis_execution.zh.md` for analysis executor and hook configuration (Chinese).
- Use `README.md` or `README.zh.md` for the short public overview.
- Edit scripts in `scripts/` directly when changing runtime behavior.
