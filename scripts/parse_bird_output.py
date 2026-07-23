#!/usr/bin/env python3
"""Convert bird CLI's multi-line tweet blocks into Newsroom candidates."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


HEADER_RE = re.compile(r"^@(\w+)\s+\(.+\):\s*$")
STATUS_RE = re.compile(r"^url:\s*(https?://(?:x|twitter)\.com/[^\s]+/status/\d+)", re.I)
METADATA_RE = re.compile(r"^(date|VIDEO|PHOTO):", re.I)
SEPARATOR_RE = re.compile(r"^─{8,}$")
URL_RE = re.compile(r"https?://\S+")


def _clean_text(lines, max_chars):
    body = "\n".join(lines).strip()
    body = re.sub(r"(?m)^\s*(?:VIDEO|PHOTO):\s*https?://\S+\s*$", "", body)
    body = re.sub(r"[\t ]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    title = URL_RE.sub("", body)
    title = re.sub(r"\s+", " ", title).strip(" -")
    if len(title) > 240:
        title = title[:237].rstrip() + "..."
    fulltext = re.sub(r"\s+", " ", body).strip()
    if len(fulltext) > max_chars:
        fulltext = fulltext[: max_chars - 3].rstrip() + "..."
    return title, fulltext


def parse_bird_text(text, *, max_chars=1200):
    records = []
    current = None

    def flush():
        nonlocal current
        if not current:
            return
        title, fulltext = _clean_text(current["body"], max_chars)
        if current.get("url") and len(title) >= 10:
            records.append(
                {
                    "title": title,
                    "url": current["url"].replace("twitter.com/", "x.com/"),
                    "source": f"X/Twitter (@{current['handle']})",
                    "fulltext": fulltext,
                }
            )
        current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        header = HEADER_RE.match(line)
        if header:
            flush()
            current = {"handle": header.group(1), "body": [], "url": ""}
            continue
        if SEPARATOR_RE.match(line):
            flush()
            continue
        if not current or not line:
            continue
        status = STATUS_RE.match(line)
        if status:
            current["url"] = status.group(1).rstrip(".,;:!?)]}")
            continue
        if METADATA_RE.match(line):
            continue
        current["body"].append(line.replace("|", " -"))
    flush()

    seen = set()
    unique = []
    for record in records:
        if record["url"] in seen:
            continue
        seen.add(record["url"])
        unique.append(record)
    return unique


def main():
    parser = argparse.ArgumentParser(description="Parse bird --plain output")
    parser.add_argument("--input", required=True)
    parser.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()

    records = parse_bird_text(
        Path(args.input).read_text(encoding="utf-8", errors="replace"),
        max_chars=args.max_chars,
    )
    for record in records:
        fulltext = record["fulltext"].replace("|", " -")
        print(
            f"{record['title']}|{record['url']}|{record['source']}|"
            f"FULLTEXT:{fulltext}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
