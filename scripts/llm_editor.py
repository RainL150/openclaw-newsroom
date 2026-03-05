#!/usr/bin/env python3
"""
llm_editor.py - AI Editor for Automated News Scanning
======================================================
Replaces deterministic keyword filtering with Gemini Flash AI-powered
story selection. Reads candidate articles, an editorial profile, and
recent post history, then calls Gemini to pick the top stories.

Usage:
    python3 llm_editor.py --file candidates.txt [--github github.txt]

Input format (pipe-delimited, one per line):
    TITLE|URL|SOURCE
    TITLE|URL|SOURCE|TIER   (tier is optional, ignored by LLM)

Output (stdout, one JSON object per line):
    {"rank": 1, "title": "...", "url": "...", "source": "...",
     "type": "rss", "summary": "...", "category": "..."}

Logs picked stories to scanner_presented.md (append).
All status/debug messages go to stderr.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── Paths (customize to your workspace) ──────────────────────────────
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE",
                                os.path.expanduser("~/.openclaw/workspace")))
MEMORY = WORKSPACE / "memory"
EDITORIAL_PROFILE = MEMORY / "editorial_profile.md"
SCANNER_PRESENTED = MEMORY / "scanner_presented.md"
NEWS_LOG = MEMORY / "news_log.md"

# ── Configuration ────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto").lower()  # auto|gemini|openrouter
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
TEMPERATURE = 0.3
TIMEOUT_SEC = 120
MAX_ARTICLES = 500
VALID_CATEGORIES = {
    "ai_product", "m_and_a", "model_release", "security", "geopolitics",
    "github_trending", "gaming", "fintech", "hardware", "open_source", "other"
}
VALID_SECTIONS = {
    "模型层面（Model）",
    "应用层面（Application）",
    "基建层面（Infrastructure）",
    "公司层面（Company/Industry）",
}
VALID_CHANNELS = {"RSS", "Reddit", "X/Twitter", "GitHub", "Tavily"}
SECTION_MAX_ITEMS = int(os.environ.get("SECTION_MAX_ITEMS", "40"))
LLM_BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "30"))
MIN_SCORE_THRESHOLD = int(os.environ.get("MIN_SCORE_THRESHOLD", "60"))


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[llm_editor {ts}] {msg}", file=sys.stderr)


def estimate_tokens(text):
    return len(text) // 4


def parse_articles(filepath):
    articles = []
    try:
        with open(filepath, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) < 3:
                    continue
                excerpt = ""
                if len(parts) >= 4:
                    # 合并第 4 个字段及之后的所有内容
                    excerpt = "|".join(parts[3:]).strip()
                    # 如果包含 FULLTEXT: 前缀，提取纯文本内容
                    if "FULLTEXT:" in excerpt:
                        # 找到 FULLTEXT: 的位置并提取后面的内容
                        fulltext_match = re.search(r'FULLTEXT:(.+)', excerpt)
                        if fulltext_match:
                            excerpt = fulltext_match.group(1).strip()
                articles.append({
                    "title": parts[0].strip(),
                    "url": parts[1].strip(),
                    "source": parts[2].strip(),
                    "excerpt": excerpt,
                })
    except FileNotFoundError:
        log(f"ERROR: File not found: {filepath}")
        sys.exit(1)
    return articles


def load_file_safe(path, tail_lines=None):
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        if tail_lines and len(lines) > tail_lines:
            lines = lines[-tail_lines:]
        return "".join(lines)
    except FileNotFoundError:
        return ""
    except Exception as e:
        log(f"  Error reading {path}: {e}")
        return ""


def filter_already_posted(articles):
    """
    Deterministic URL pre-filter: remove candidates whose URL already
    appears in news_log.md or scanner_presented.md.
    """
    full_log = load_file_safe(NEWS_LOG)
    if not full_log:
        return articles

    presented_log = load_file_safe(SCANNER_PRESENTED)

    url_pattern = re.compile(r'https?://[^\s|>\]\)"\']+')
    posted_urls = set()
    for text in [full_log, presented_log]:
        for url in url_pattern.findall(text):
            url = url.rstrip(".,;:)")
            # Skip your own channel links (customize this pattern)
            # if "t.me/yourchannel" in url:
            #     continue
            posted_urls.add(url)

    if not posted_urls:
        return articles

    filtered = []
    removed = 0
    for a in articles:
        candidate_url = a["url"].rstrip(".,;:)")
        if candidate_url in posted_urls:
            log(f"  PRE-FILTERED (already posted): {a['title'][:60]}")
            removed += 1
        else:
            filtered.append(a)

    log(f"Pre-filtered {removed} candidates (already posted)")
    return filtered


def build_prompt(articles, github_articles, editorial_profile, recent_posts):
    article_list = []
    for i, a in enumerate(articles, 1):
        title_line = f"  {i}. [{a['source']}] {a['title']}\n     URL: {a['url']}"
        excerpt = (a.get('excerpt') or '').strip()
        if excerpt:
            # 如果有 excerpt，添加到 prompt 中供 LLM 参考
            title_line += f"\n     摘要: {excerpt[:300]}"
        article_list.append(title_line)
    articles_text = "\n".join(article_list)

    github_text = ""
    if github_articles:
        gh_list = []
        for i, g in enumerate(github_articles, 1):
            title_line = f"  {i}. [{g['source']}] {g['title']}\n     URL: {g['url']}"
            excerpt = (g.get('excerpt') or '').strip()
            if excerpt:
                # GitHub 的 excerpt 是仓库描述，帮助 LLM 理解并生成中文总结
                title_line += f"\n     描述: {excerpt}"
            gh_list.append(title_line)
        github_text = (
            "\n\n## GitHub Trending Repos\n"
            "These are trending GitHub repositories. Include any that are genuinely\n"
            "newsworthy for your audience.\n\n"
            + "\n".join(gh_list)
        )

    prompt = f"""你是自动化 AI 新闻频道的总编。请从候选新闻中挑选最值得推送的新闻。

## 编辑偏好（仅偏好参考，硬规则以本 Prompt 为准）
{editorial_profile}

## 最近已发（严禁重复同一事件）
{recent_posts if recent_posts else '(暂无最近已发记录)'}

## 候选新闻
{articles_text}
{github_text}

## 任务
对候选新闻做“全量四板块分类 + 去重 + 打分”。
必须返回全部候选（去重后）的结果，不做精选、不截断。

## 四个板块定义
1) 模型层面（Model）：算法、架构、训练、推理能力、基准测试、模型开源/微调等。
2) 应用层面（Application）：Agent、产品工具、工作流落地、终端/本地部署体验等。
3) 基建层面（Infrastructure）：网关、部署、性能优化、资源与成本、带宽/存储等底层支撑。
4) 公司层面（Company/Industry）：公司战略、融资并购、生态合作、市场与产业动态。

## 规则
1. 必须返回全部候选（去重后）新闻，按 section + score 组织。
2. 不得选择与最近已发重复的同一事件（即使标题或来源不同）。
3. 同一来源不设上限（由分数与板块相关性自然决定）。
4. 每条必须给出"中文标题"（title_zh，10-20字）和"中文总结"（summary），都必须是中文。
5. 每条必须给出 score（0-100 的整数），用于排序；每个板块内按 score 从高到低。
6. 每条必须归到 section（四选一）。
7. 不做补齐、不做二次精选、不做人为条数限制；返回全部候选（去重后）结果。
8. category 仅可从以下集合中选择：
   ai_product, m_and_a, model_release, security, geopolitics,
   github_trending, gaming, fintech, hardware, open_source, other
9. 每个板块需提供“结构化板块总结”（中文，<=10句），严格按以下格式输出到 section_summary：
   一句话总趋势：...
   关键词：
   - 词1
   - 词2
   - 词3
   最大主题：...
   核心问题：...
   典型方向：
   - 方向1
   - 方向2

## 输出格式（必须是 JSON）
仅返回 JSON 数组（长度应覆盖全部候选去重结果）：
[
  {{
    "rank": 1,
    "title": "原始英文标题（保持原文）",
    "title_zh": "中文标题（必须中文，简洁准确，10-20字）",
    "url": "https://...",
    "source": "来源名称",
    "type": "rss 或 twitter 或 github（X/Twitter 必须写 twitter）",
    "summary": "中文一句话总结（必须中文，说明为什么重要）",
    "category": "上述枚举之一",
    "section": "模型层面（Model）/应用层面（Application）/基建层面（Infrastructure）/公司层面（Company/Industry）",
    "score": 0,
    "section_summary": "结构化板块总结（严格使用：一句话总趋势/关键词/最大主题/核心问题/典型方向）",
    "channel": "RSS/Reddit/X/Twitter/GitHub/Tavily"
  }}
]

只返回 JSON 数组本体，不要 markdown、不要解释、不要代码块。"""
    return prompt


def _parse_llm_json_text(text):
    try:
        picks = json.loads(text)
        if isinstance(picks, list):
            return picks
        if isinstance(picks, dict) and "stories" in picks:
            return picks["stories"]
        return None
    except json.JSONDecodeError:
        match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
        if match:
            try:
                picks = json.loads(match.group())
                if isinstance(picks, list):
                    return picks
            except json.JSONDecodeError:
                pass
        log(f"Could not parse LLM response. First 500 chars: {text[:500]}")
        return None


def call_gemini(prompt, api_key):
    url = f"{GEMINI_URL}?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": TEMPERATURE,
            "responseMimeType": "application/json",
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    token_est = estimate_tokens(prompt)
    log(f"Sending prompt to Gemini Flash (~{token_est} tokens)")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "(no body)"
        log(f"Gemini HTTP error {e.code}: {error_body[:500]}")
        return None
    except urllib.error.URLError as e:
        log(f"Gemini connection error: {e.reason}")
        return None
    except Exception as e:
        log(f"Gemini call failed: {e}")
        return None

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        log(f"Unexpected Gemini response structure: {e}")
        return None

    return _parse_llm_json_text(text)


def call_openrouter(prompt, api_key):
    payload = {
        "model": OPENROUTER_MODEL,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    token_est = estimate_tokens(prompt)
    log(f"Sending prompt to OpenRouter ({OPENROUTER_MODEL}) (~{token_est} tokens)")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "(no body)"
        log(f"OpenRouter HTTP error {e.code}: {error_body[:500]}")
        return None
    except urllib.error.URLError as e:
        log(f"OpenRouter connection error: {e.reason}")
        return None
    except Exception as e:
        log(f"OpenRouter call failed: {e}")
        return None

    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        log(f"Unexpected OpenRouter response structure: {e}")
        return None

    return _parse_llm_json_text(text)


def _infer_channel(url, source, story_type):
    s = (source or "").lower()
    u = (url or "").lower()
    if story_type == "github" or "github" in s or "github.com" in u:
        return "GitHub"
    if story_type == "twitter" or "x/twitter" in s or "twitter" in s or "x.com" in u or "twitter.com" in u:
        return "X/Twitter"
    if "reddit" in s or "reddit.com" in u or s.startswith("r/"):
        return "Reddit"
    if "tavily" in s:
        return "Tavily"
    return "RSS"


def _infer_section(title, source, story_type):
    text = f"{title} {source}".lower()
    if any(k in text for k in ["model", "benchmark", "llm", "gpt", "claude", "llama", "推理", "训练", "权重"]):
        return "模型层面（Model）"
    if any(k in text for k in ["gateway", "infra", "infrastructure", "部署", "latency", "cost", "gpu", "带宽", "存储"]):
        return "基建层面（Infrastructure）"
    if any(k in text for k in ["acquire", "fund", "融资", "并购", "company", "战略", "market", "industry"]):
        return "公司层面（Company/Industry）"
    if story_type == "github":
        return "应用层面（Application）"
    return "应用层面（Application）"


def fallback_picks(articles, github_articles):
    log("FALLBACK: Using raw article order (no LLM judgment)")
    all_candidates = articles.copy()
    if github_articles:
        all_candidates.extend(github_articles)

    picks = []
    section_counts = {}
    for a in all_candidates:
        if "github.com" in a["url"]:
            article_type = "github"
        elif "x.com/" in a.get("url", "") or "twitter.com/" in a.get("url", "") or "X/" in a.get("source", ""):
            article_type = "twitter"
        else:
            article_type = "rss"
        section = _infer_section(a["title"], a["source"], article_type)
        if section_counts.get(section, 0) >= SECTION_MAX_ITEMS:
            continue
        section_counts[section] = section_counts.get(section, 0) + 1
        picks.append({
            "rank": len(picks) + 1,
            "title": a["title"],
            "title_zh": "（降级模式）",
            "url": a["url"],
            "source": a["source"],
            "type": article_type,
            "summary": "（Fallback）当前为降级模式，建议检查 LLM 配置以恢复高质量总结。",
            "category": "other",
            "section": section,
            "score": max(1, 100 - len(picks) * 3),
            "section_summary": "一句话总趋势：从概念验证走向工程化落地。\n关键词：\n- 降本\n- 稳定性\n- 自动化\n最大主题：可复用能力沉淀\n核心问题：如何在成本可控下稳定规模化\n典型方向：\n- 智能路由与缓存\n- Prompt/上下文治理",
            "channel": _infer_channel(a["url"], a["source"], article_type),
        })
        # 不做全局 Top N 截断
    return picks


def validate_picks(picks):
    validated = []
    for i, pick in enumerate(picks):
        if not isinstance(pick, dict):
            continue
        entry = {
            "rank": pick.get("rank", i + 1),
            "title": pick.get("title", "(no title)"),
            "title_zh": pick.get("title_zh", ""),
            "url": pick.get("url", ""),
            "source": pick.get("source", "unknown"),
            "type": pick.get("type", "rss"),
            "summary": pick.get("summary", ""),
            "category": pick.get("category", "other"),
            "section": pick.get("section", "应用层面（Application）"),
            "score": pick.get("score", 0),
            "section_summary": pick.get("section_summary", ""),
            "channel": pick.get("channel", ""),
        }
        if entry["category"] not in VALID_CATEGORIES:
            entry["category"] = "other"
        if entry["type"] not in ("rss", "twitter", "github"):
            entry["type"] = "rss"
        if entry["section"] not in VALID_SECTIONS:
            entry["section"] = _infer_section(entry["title"], entry["source"], entry["type"])
        if entry["channel"] not in VALID_CHANNELS:
            entry["channel"] = _infer_channel(entry["url"], entry["source"], entry["type"])
        try:
            entry["score"] = int(entry.get("score", 0))
        except Exception:
            entry["score"] = 0
        validated.append(entry)

    validated.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, v in enumerate(validated):
        v["rank"] = i + 1

    return validated


def merge_all_candidates_with_llm_annotations(articles, github_articles, llm_picks):
    """全量输出：保留全部候选，仅用LLM结果做分类/总结标注。"""
    ann_by_url = {}
    for p in (llm_picks or []):
        url = (p.get("url") or "").strip()
        if url:
            ann_by_url[url] = p

    merged = []
    missing_summary_items = []  # 收集缺少 summary 的文章
    all_candidates = list(articles or []) + list(github_articles or [])
    seen = set()
    for i, c in enumerate(all_candidates, 1):
        url = (c.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)

        story_type = "github" if "github.com" in url else ("twitter" if ("x.com/" in url or "twitter.com/" in url) else "rss")
        base = {
            "rank": i,
            "title": c.get("title", "(no title)"),
            "title_zh": "",
            "url": url,
            "source": c.get("source", "unknown"),
            "type": story_type,
            "summary": "",
            "category": "other",
            "section": _infer_section(c.get("title", ""), c.get("source", ""), story_type),
            "score": 0,
            "section_summary": "",
            "channel": _infer_channel(url, c.get("source", ""), story_type),
        }

        ann = ann_by_url.get(url)
        if ann:
            summary = ann.get("summary", "") or ""
            title_zh = ann.get("title_zh", "") or ""
            base.update({
                "title_zh": title_zh,
                "summary": summary,
                "category": ann.get("category", "other") or "other",
                "section": ann.get("section", base["section"]) or base["section"],
                "score": int(ann.get("score", 0) or 0),
                "section_summary": ann.get("section_summary", "") or "",
                "channel": ann.get("channel", base["channel"]) or base["channel"],
            })
            # 如果 LLM 返回了这个 URL 但 summary 或 title_zh 为空，标记为需要重试
            if not summary or not title_zh:
                missing_summary_items.append((len(merged), c))
        else:
            # LLM 完全没有返回这个 URL 的标注，也标记为需要重试
            missing_summary_items.append((len(merged), c))
            excerpt = (c.get("excerpt") or "").strip()
            if excerpt:
                base["summary"] = excerpt[:180]

        merged.append(base)

    # 板块内按分数排序，再统一重排 rank
    merged.sort(key=lambda x: (x.get("section", ""), int(x.get("score", 0)) * -1))
    for i, m in enumerate(merged, 1):
        m["rank"] = i
    return merged, missing_summary_items


def annotate_in_batches(articles, editorial_profile, recent_posts, selected_provider, gemini_api_key, openrouter_api_key):
    all_picks = []
    total = len(articles)
    if total == 0:
        return all_picks

    for i in range(0, total, LLM_BATCH_SIZE):
        batch = articles[i:i + LLM_BATCH_SIZE]
        log(f"LLM batch {i//LLM_BATCH_SIZE + 1}: size={len(batch)}")
        prompt = build_prompt(batch, [], editorial_profile, recent_posts)
        
        # 最多尝试 2 次
        picks = None
        max_retries = 2
        for attempt in range(max_retries):
            if selected_provider == "gemini":
                picks = call_gemini(prompt, gemini_api_key)
            else:
                picks = call_openrouter(prompt, openrouter_api_key)
            
            if picks is not None:
                break
            
            if attempt < max_retries - 1:
                log(f"  batch annotation failed, retrying... (attempt {attempt + 2}/{max_retries})")
            else:
                log(f"  batch annotation failed after {max_retries} attempts, skip this batch")

        if picks is None:
            continue
        picks = validate_picks(picks)
        all_picks.extend(picks)

    log(f"Batched annotations: {len(all_picks)} / {total}")
    return all_picks


def retry_missing_summaries(merged_items, missing_items, editorial_profile, recent_posts, selected_provider, gemini_api_key, openrouter_api_key):
    """对缺少 summary 的文章进行重试，最多 2 次。"""
    if not missing_items:
        return merged_items
    
    log(f"Found {len(missing_items)} items with missing summaries, retrying...")
    
    # 提取需要重试的文章
    retry_articles = [item[1] for item in missing_items]
    
    # 重试标注，最多 2 次
    max_retries = 2
    retry_picks = None
    
    for attempt in range(max_retries):
        log(f"  Retry attempt {attempt + 1}/{max_retries} for {len(retry_articles)} items")
        retry_picks = annotate_in_batches(
            retry_articles,
            editorial_profile,
            recent_posts,
            selected_provider,
            gemini_api_key,
            openrouter_api_key,
        )
        
        if retry_picks:
            # 检查有多少文章获得了有效的 summary
            valid_summaries = sum(1 for p in retry_picks if (p.get("summary") or "").strip())
            log(f"  Retry got {valid_summaries}/{len(retry_picks)} valid summaries")
            
            if valid_summaries > 0:
                break
        
        if attempt < max_retries - 1:
            log(f"  Retry failed, attempting again...")
    
    if not retry_picks:
        log("  All retry attempts failed, keeping original fallback summaries")
        return merged_items
    
    # 更新 merged_items 中缺少 summary 的项
    retry_by_url = {p.get("url", ""): p for p in retry_picks if p.get("url")}
    
    updated_count = 0
    for idx, orig_article in missing_items:
        url = orig_article.get("url", "")
        retry_ann = retry_by_url.get(url)
        if retry_ann and (retry_ann.get("summary") or "").strip():
            # 找到对应的 merged item 并更新
            for m in merged_items:
                if m.get("url") == url:
                    m["title_zh"] = retry_ann.get("title_zh", "")
                    m["summary"] = retry_ann.get("summary", "")
                    m["category"] = retry_ann.get("category", m["category"])
                    m["section"] = retry_ann.get("section", m["section"])
                    m["score"] = int(retry_ann.get("score", m["score"]))
                    m["section_summary"] = retry_ann.get("section_summary", m["section_summary"])
                    m["channel"] = retry_ann.get("channel", m["channel"])
                    updated_count += 1
                    break
    
    log(f"  Successfully updated {updated_count} items with retry summaries")
    return merged_items


def log_to_scanner_presented(picks):
    today = datetime.now().strftime("%Y-%m-%d")
    today_header = f"## {today}"
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        existing = ""
        if SCANNER_PRESENTED.exists():
            existing = SCANNER_PRESENTED.read_text()

        with open(SCANNER_PRESENTED, "a") as f:
            if today_header not in existing:
                f.write(f"\n{today_header}\n\n")
            for pick in picks:
                f.write(f"[{ts}] {pick['title']} | {pick['url']}\n")

        log(f"Logged {len(picks)} picks to scanner_presented.md")
    except Exception as e:
        log(f"Warning: could not log to scanner_presented.md: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Editor — selects top stories using Gemini Flash"
    )
    parser.add_argument("--file", "-f", required=True,
                       help="Path to article candidates file")
    parser.add_argument("--github", "-g",
                       help="Path to GitHub trending repos file")
    parser.add_argument("--dry-run", action="store_true",
                       help="Build prompt and print to stderr, but don't call API")
    args = parser.parse_args()

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")

    selected_provider = LLM_PROVIDER
    if selected_provider == "auto":
        if gemini_api_key:
            selected_provider = "gemini"
        elif openrouter_api_key:
            selected_provider = "openrouter"
        else:
            log("ERROR: neither GEMINI_API_KEY nor OPENROUTER_API_KEY is set")
            sys.exit(1)

    if selected_provider == "gemini" and not gemini_api_key:
        log("ERROR: LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        sys.exit(1)
    if selected_provider == "openrouter" and not openrouter_api_key:
        log("ERROR: LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set")
        sys.exit(1)

    active_model = GEMINI_MODEL if selected_provider == "gemini" else OPENROUTER_MODEL
    log(f"Configuration: provider={selected_provider}, model={active_model}, section_max={SECTION_MAX_ITEMS}, min_score={MIN_SCORE_THRESHOLD}")

    log(f"Loading articles from {args.file}")
    articles = parse_articles(args.file)
    log(f"  Loaded {len(articles)} candidates")
    if len(articles) > MAX_ARTICLES:
        articles = articles[:MAX_ARTICLES]

    if not articles:
        log("ERROR: No articles found in input file")
        sys.exit(1)

    github_articles = []
    if args.github:
        github_articles = parse_articles(args.github)
        log(f"  Loaded {len(github_articles)} GitHub repos")

    log("Running deterministic URL pre-filter")
    articles = filter_already_posted(articles)
    if github_articles:
        github_articles = filter_already_posted(github_articles)

    total_candidates = len(articles) + len(github_articles)

    log("Loading editorial profile")
    editorial_profile = load_file_safe(EDITORIAL_PROFILE)
    if not editorial_profile:
        editorial_profile = (
            "Select stories about AI, LLMs, tech deals, and security.\n"
            "Prefer breaking news and concrete announcements over opinion."
        )

    log("Loading recent post history for dedup")
    recent_presented = load_file_safe(SCANNER_PRESENTED, tail_lines=60)
    recent_news_log = load_file_safe(NEWS_LOG, tail_lines=150)
    recent_posts = ""
    if recent_presented:
        recent_posts += "### scanner_presented.md (recent)\n" + recent_presented + "\n"
    if recent_news_log:
        recent_posts += "### news_log.md (recent)\n" + recent_news_log + "\n"

    if args.dry_run:
        sample = build_prompt(articles[:min(len(articles), LLM_BATCH_SIZE)], [], editorial_profile, recent_posts)
        log("DRY RUN — printing one batch prompt to stderr")
        print(sample, file=sys.stderr)
        return

    # 分批进行“分类+总结+打分”标注，保证单批质量
    llm_picks = annotate_in_batches(
        articles,
        editorial_profile,
        recent_posts,
        selected_provider,
        gemini_api_key,
        openrouter_api_key,
    )

    # GitHub 候选也单独分批标注（通常条数较少）
    if github_articles:
        llm_picks.extend(
            annotate_in_batches(
                github_articles,
                editorial_profile,
                recent_posts,
                selected_provider,
                gemini_api_key,
                openrouter_api_key,
            )
        )

    if not llm_picks:
        log("Warning: no LLM annotations, using fallback summaries.")
        llm_picks = validate_picks(fallback_picks(articles, github_articles))

    # 关键：全量输出候选，仅做分类与总结标注
    picks, missing_items = merge_all_candidates_with_llm_annotations(articles, github_articles, llm_picks)
    
    # 对缺少 summary 的文章进行重试（最多 2 次）
    if missing_items:
        picks = retry_missing_summaries(
            picks,
            missing_items,
            editorial_profile,
            recent_posts,
            selected_provider,
            gemini_api_key,
            openrouter_api_key,
        )
    
    # 精选过滤：筛掉低于阈值分数的文章
    original_count = len(picks)
    picks = [p for p in picks if int(p.get("score", 0)) >= MIN_SCORE_THRESHOLD]
    filtered_count = original_count - len(picks)
    if filtered_count > 0:
        log(f"Filtered out {filtered_count} low-score articles (score < {MIN_SCORE_THRESHOLD})")
    
    # 重新排序并更新 rank
    picks.sort(key=lambda x: (x.get("section", ""), int(x.get("score", 0)) * -1))
    for i, p in enumerate(picks, 1):
        p["rank"] = i

    for pick in picks:
        print(json.dumps(pick, ensure_ascii=False))

    log_to_scanner_presented(picks)
    log(f"Done. {len(picks)} stories classified (filtered from {original_count}).")


if __name__ == "__main__":
    main()
