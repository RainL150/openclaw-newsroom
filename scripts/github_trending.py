#!/usr/bin/env python3
"""GitHub Trending & Emerging Repo Scanner.

Scans GitHub for trending AI/ML repos using three strategies:
  1. Emerging: repos created in the last 7 days with 50+ stars
  2. Velocity: established repos (1000+ stars) gaining traction fast
  3. Releases: new releases from key AI repos (SDKs, models, tools)

Output format:  TITLE|URL|SOURCE|TIER|EXCERPT
  - TITLE: 简洁的标题（仓库名 + 标签）
  - EXCERPT: 仓库描述，供 LLM 生成中文总结
Compatible with the news scan pipeline.

Uses only stdlib — no pip packages. Auth via GH_TOKEN env var if available
(5000 req/h), falls back to unauthenticated (60 req/h).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────
STATE_FILE = Path(os.path.expanduser(
    "~/.openclaw/workspace/memory/github_trending_state.json"
))
API_BASE = "https://api.github.com/search/repositories"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "NewsScanner/1.0",
}
_gh_token = os.environ.get("GH_TOKEN", "")
if _gh_token:
    HEADERS["Authorization"] = f"token {_gh_token}"
REQUEST_TIMEOUT = 30

# Topics to scan (each generates a separate API call)
TOPICS = ["ai", "llm", "agents", "generative-ai", "large-language-model"]

EMERGING_WINDOW_DAYS = 7
EMERGING_MIN_STARS = 50

VELOCITY_MIN_STARS = 1000
VELOCITY_PUSHED_DAYS = 30
VELOCITY_GROWTH_MIN = 50
VELOCITY_ALWAYS_IF = 10000

MAX_OUTPUT = 15
TIER = 3

# Key AI repos to monitor for releases (owner/repo)
# Customize: add repos relevant to your audience
RELEASE_REPOS = [
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "huggingface/transformers",
    "langchain-ai/langchain",
    "ollama/ollama",
    "vllm-project/vllm",
    "run-llama/llama_index",
    "microsoft/autogen",
    "crewAIInc/crewAI",
    "BerriAI/litellm",
    "ggerganov/llama.cpp",
    "mozilla/readability",
    "deepseek-ai/DeepSeek-V3",
    "QwenLM/Qwen",
    "meta-llama/llama",
    "google/gemma.cpp",
]
RELEASE_WINDOW_DAYS = 3


def iso_date(dt):
    return dt.strftime("%Y-%m-%d")


def log(msg):
    print(msg, file=sys.stderr)


_rate_limited = False


def github_search(query, sort="stars", order="desc", per_page=10):
    global _rate_limited
    if _rate_limited:
        return None

    params = urllib.parse.urlencode({
        "q": query, "sort": sort, "order": order, "per_page": per_page,
    })
    url = f"{API_BASE}?{params}"

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            log(f"  API call OK — rate limit remaining: {remaining}")
            if remaining != "?" and int(remaining) <= 1:
                log("WARNING: GitHub API rate limit nearly exhausted.")
                _rate_limited = True
            data = json.loads(resp.read().decode())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log("WARNING: Rate limited (HTTP 403).")
            _rate_limited = True
        else:
            log(f"WARNING: GitHub API error {e.code}: {e.reason}")
        return None
    except urllib.error.URLError as e:
        log(f"WARNING: Network error: {e.reason}")
        return None
    except Exception as e:
        log(f"WARNING: Unexpected error: {e}")
        return None


def detect_language(repo):
    lang = repo.get("language")
    return lang if lang else "Mixed"


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"repos": {}, "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def scan_emerging():
    cutoff = iso_date(datetime.now(timezone.utc) - timedelta(days=EMERGING_WINDOW_DAYS))
    results = []
    for topic in TOPICS:
        if _rate_limited:
            break
        query = f"topic:{topic} created:>{cutoff} stars:>{EMERGING_MIN_STARS}"
        log(f"[Emerging] topic={topic}")
        repos = github_search(query, sort="stars", order="desc", per_page=10)
        if repos is None:
            continue
        for repo in repos:
            full_name = repo["full_name"]
            stars = repo.get("stargazers_count", 0)
            desc = (repo.get("description") or "No description").replace("|", " ").replace("\n", " ")
            url = repo.get("html_url", f"https://github.com/{full_name}")
            lang = detect_language(repo)
            # 标题只包含仓库名和 star 数
            title = f"[GitHub EMERGING] {full_name} (+{stars} stars)"
            # 将描述作为 excerpt 传递，这样 LLM 可以基于描述生成中文总结
            results.append((title, url, f"GitHub/{lang}", stars, full_name, desc))
        time.sleep(0.5)
    return results


def scan_velocity(state):
    pushed_cutoff = iso_date(datetime.now(timezone.utc) - timedelta(days=VELOCITY_PUSHED_DAYS))
    old_repos = state.get("repos", {})
    new_repos = {}
    results = []
    velocity_topics = ["ai", "llm", "large-language-model"]

    for topic in velocity_topics:
        if _rate_limited:
            break
        query = f"topic:{topic} stars:>{VELOCITY_MIN_STARS} pushed:>{pushed_cutoff}"
        log(f"[Velocity] topic={topic}")
        repos = github_search(query, sort="stars", order="desc", per_page=10)
        if repos is None:
            continue
        for repo in repos:
            full_name = repo["full_name"]
            stars = repo.get("stargazers_count", 0)
            desc = (repo.get("description") or "No description").replace("|", " ").replace("\n", " ")
            url = repo.get("html_url", f"https://github.com/{full_name}")
            lang = detect_language(repo)
            new_repos[full_name] = {"stars": stars}
            prev_stars = old_repos.get(full_name, {}).get("stars")
            growth = (stars - prev_stars) if prev_stars is not None else 0

            if growth >= VELOCITY_GROWTH_MIN:
                title = f"[GitHub TRENDING] {full_name} (+{growth} stars)"
                results.append((title, url, f"GitHub/{lang}", growth, full_name, desc))
            elif stars >= VELOCITY_ALWAYS_IF:
                title = f"[GitHub HOT] {full_name} ({stars:,} total stars)"
                results.append((title, url, f"GitHub/{lang}", 0, full_name, desc))
        time.sleep(0.5)

    merged_repos = {**old_repos}
    merged_repos.update(new_repos)
    return results, merged_repos


def scan_releases():
    global _rate_limited
    cutoff = datetime.now(timezone.utc) - timedelta(days=RELEASE_WINDOW_DAYS)
    results = []

    for repo_name in RELEASE_REPOS:
        if _rate_limited:
            break
        url = f"https://api.github.com/repos/{repo_name}/releases?per_page=3"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                if remaining != "?" and int(remaining) <= 2:
                    _rate_limited = True
                    break
                releases = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            continue
        except Exception:
            continue

        for release in releases:
            if release.get("draft", False) or release.get("prerelease", False):
                continue
            published = release.get("published_at", "")
            if not published:
                continue
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub_dt < cutoff:
                break

            tag = release.get("tag_name", "")
            name = release.get("name", tag)
            html_url = release.get("html_url", f"https://github.com/{repo_name}")
            body = (release.get("body") or "")[:200].replace("|", " ").replace("\n", " ")

            title = f"[GitHub RELEASE] {repo_name} {tag}"
            # 将 release name 和 body 作为描述
            desc = f"{name}. {body}" if body else name
            results.append((title, html_url, "GitHub/Releases", 0, repo_name, desc))
            break
        time.sleep(0.3)
    return results


def main():
    log("=" * 60)
    log(f"GitHub Trending Scanner — {datetime.now(timezone.utc).isoformat()}")
    log("=" * 60)

    state = load_state()
    seen_repos = set()
    output_lines = []

    log("\n--- Strategy 1: Emerging repos ---")
    emerging = scan_emerging()
    emerging.sort(key=lambda x: x[3], reverse=True)
    for title, url, source, velocity, full_name, excerpt in emerging:
        if full_name not in seen_repos:
            seen_repos.add(full_name)
            output_lines.append((title, url, source, TIER, excerpt))

    log("\n--- Strategy 2: Velocity ---")
    velocity_results, merged_repos = scan_velocity(state)
    velocity_results.sort(key=lambda x: x[3], reverse=True)
    for title, url, source, velocity, full_name, excerpt in velocity_results:
        if full_name not in seen_repos:
            seen_repos.add(full_name)
            output_lines.append((title, url, source, TIER, excerpt))

    log("\n--- Strategy 3: Releases ---")
    releases = scan_releases()
    for title, url, source, _, full_name, excerpt in releases:
        if full_name not in seen_repos:
            seen_repos.add(full_name)
            output_lines.append((title, url, source, TIER, excerpt))

    output_lines = output_lines[:MAX_OUTPUT]

    if not output_lines:
        log("No trending repos found.")
    else:
        for title, url, source, tier, excerpt in output_lines:
            # 输出格式：TITLE|URL|SOURCE|TIER|EXCERPT
            # excerpt 包含描述信息，供 LLM 生成中文总结
            print(f"{title}|{url}|{source}|{tier}|{excerpt}")

    state["repos"] = merged_repos
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    log("Done.")


if __name__ == "__main__":
    import urllib.parse
    main()
