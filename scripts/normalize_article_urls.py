#!/usr/bin/env python3
"""Normalize and verify every outbound URL used by Newsroom reports."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from url_tools import LinkCheckResult, normalize_url, resolve_and_validate


def _load_cache(path: Optional[Path]):
    if not path or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            key: LinkCheckResult(**value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }
    except (OSError, ValueError, TypeError):
        return {}


def _save_cache(path: Optional[Path], cache):
    if not path:
        return
    payload = {key: result.to_dict() for key, result in cache.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _parse_pipe(lines):
    entries = []
    for index, line in enumerate(lines):
        raw = line.rstrip("\n")
        if not raw:
            continue
        parts = raw.split("|")
        if len(parts) < 3:
            continue
        entries.append({"index": index, "parts": parts, "url": parts[1].strip()})
    return entries


def _parse_jsonl(lines):
    entries = []
    for index, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        entries.append({"index": index, "item": item, "url": str(item.get("url", "")).strip()})
    return entries


def process_entries(entries, *, workers, timeout, cache, allow_private=False):
    results = {}
    pending = {}
    for entry in entries:
        cleaned = normalize_url(entry["url"])
        cached = cache.get(entry["url"]) or cache.get(cleaned)
        if cached:
            results[entry["index"]] = cached
        else:
            pending.setdefault(entry["url"], []).append(entry["index"])

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                resolve_and_validate,
                url,
                timeout=timeout,
                allow_private=allow_private,
            ): url
            for url in pending
        }
        for future in as_completed(futures):
            original_url = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # defensive: one URL must not abort the batch
                result = LinkCheckResult(original_url, "", False, reason=exc.__class__.__name__)
            cache[original_url] = result
            if result.url:
                cache[result.url] = result
            for index in pending[original_url]:
                results[index] = result
    return results


def main():
    parser = argparse.ArgumentParser(description="Validate and normalize Newsroom links")
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", choices=("pipe", "jsonl"), default="pipe")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument("--cache")
    parser.add_argument("--allow-private", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    input_path = Path(args.input)
    lines = input_path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries = _parse_pipe(lines) if args.format == "pipe" else _parse_jsonl(lines)
    cache_path = Path(args.cache) if args.cache else None
    cache = _load_cache(cache_path)
    results = process_entries(
        entries,
        workers=args.workers,
        timeout=args.timeout,
        cache=cache,
        allow_private=args.allow_private,
    )

    kept = []
    dropped = []
    changed = 0
    seen = set()
    for entry in entries:
        result = results.get(entry["index"])
        if not result or not result.ok or not result.url:
            dropped.append((entry["url"], result.reason if result else "not_checked"))
            continue
        if result.url in seen:
            dropped.append((entry["url"], "duplicate_final_url"))
            continue
        seen.add(result.url)
        if result.url != normalize_url(entry["url"]):
            changed += 1

        if args.format == "pipe":
            parts = entry["parts"]
            parts[1] = result.url
            kept.append("|".join(parts))
        else:
            item = entry["item"]
            item["url"] = result.url
            kept.append(item)

    if args.format == "pipe":
        for line in kept:
            print(line)
    else:
        for rank, item in enumerate(kept, 1):
            item["rank"] = rank
            print(json.dumps(item, ensure_ascii=False))

    _save_cache(cache_path, cache)
    for url, reason in dropped[:20]:
        print(f"  Drop link ({reason}): {url[:180]}", file=sys.stderr)
    if len(dropped) > 20:
        print(f"  ... and {len(dropped) - 20} more dropped links", file=sys.stderr)
    print(
        f"  Link check: {len(entries)} checked -> {len(kept)} valid; "
        f"{changed} normalized; {len(dropped)} dropped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
