#!/usr/bin/env python3
"""
Enrich top articles with full text content for better LLM curation.

Reads pipe-delimited articles, fetches full text for the top N articles
using Cloudflare Markdown for Agents (preferred) or HTML extraction (fallback).

Appends full text as a pipe field: TITLE|URL|SOURCE|TIER|FULLTEXT:text

Usage:
    python3 enrich_top_articles.py --input articles.txt [--max 10] [--max-chars 1500]
"""

import re
import sys
import argparse
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

_SSL_CTX = ssl.create_default_context()

TIMEOUT = 8
MAX_WORKERS = 4
USER_AGENT = "NewsScanner/1.0 (article enrichment)"

# Domains to skip enrichment (paywalled, JS-heavy, or not articles)
SKIP_DOMAINS = {
    "twitter.com", "x.com",
    "reddit.com", "old.reddit.com",
    "github.com",
    "youtube.com", "youtu.be",
    "nytimes.com", "bloomberg.com", "wsj.com", "ft.com",
    "arxiv.org",
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._skip_tags = {"script", "style", "nav", "footer", "header", "aside", "noscript"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self._text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        raw = "".join(self._text)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def fetch_full_text(url, max_chars=1500):
    """Fetch article full text via CF Markdown or HTML extraction."""
    domain = urlparse(url).netloc.lower().lstrip("www.")
    if domain in SKIP_DOMAINS:
        return ""

    try:
        req = Request(url, headers={
            "Accept": "text/markdown, text/html;q=0.9",
            "User-Agent": USER_AGENT,
        })
        with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

            if raw[:2] == b"\x1f\x8b":
                import gzip
                raw = gzip.decompress(raw)

            text = raw.decode("utf-8", errors="replace")

            if "text/markdown" in content_type:
                return text[:max_chars]

            article_match = re.search(r"<article[^>]*>(.*?)</article>", text, re.DOTALL | re.IGNORECASE)
            fragment = article_match.group(1) if article_match else text
            extractor = TextExtractor()
            try:
                extractor.feed(fragment)
            except Exception:
                return ""
            extracted = extractor.get_text()
            if len(extracted) < 80:
                return ""
            return extracted[:max_chars]

    except (HTTPError, URLError, OSError):
        return ""
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(description="Enrich top articles with full text")
    parser.add_argument('--input', '-i', required=True, help='Input pipe-delimited file')
    parser.add_argument('--max', type=int, default=10, help='Max articles to enrich (default: 10)')
    parser.add_argument('--max-chars', type=int, default=1500, help='Max chars per article (default: 1500)')
    args = parser.parse_args()

    articles = []
    try:
        with open(args.input, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                articles.append(line)
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1

    if not articles:
        print("No articles to enrich", file=sys.stderr)
        return 0

    to_enrich = articles[:args.max]
    pass_through = articles[args.max:]

    results = {}
    enriched_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for i, line in enumerate(to_enrich):
            parts = line.split('|')
            if len(parts) >= 2:
                url = parts[1]
                futures[pool.submit(fetch_full_text, url, args.max_chars)] = i

        for future in as_completed(futures):
            idx = futures[future]
            text = future.result()
            if text:
                results[idx] = text
                enriched_count += 1

    for i, line in enumerate(to_enrich):
        if i in results:
            clean_text = results[i].replace('|', ' ').replace('\n', ' ').strip()
            clean_text = re.sub(r'\s+', ' ', clean_text)
            print(f"{line}|FULLTEXT:{clean_text[:args.max_chars]}")
        else:
            print(line)

    for line in pass_through:
        print(line)

    print(f"  Done: {enriched_count}/{len(to_enrich)} articles enriched", file=sys.stderr)


if __name__ == "__main__":
    main()
