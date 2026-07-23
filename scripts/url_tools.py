#!/usr/bin/env python3
"""Shared URL normalization and reachability checks for Newsroom."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import ssl
from dataclasses import asdict, dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 OpenClaw-Newsroom/1.0"
)

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "mkt_tok",
    "ref_src",
    "ref_url",
    "vero_conv",
    "vero_id",
}
TRACKING_PREFIXES = ("utm_", "ga_", "pk_")
RESTRICTED_BUT_REACHABLE = {401, 403, 406, 416, 429, 451}
KNOWN_SHORTENERS = {
    "t.co",
    "bit.ly",
    "buff.ly",
    "dlvr.it",
    "goo.gl",
    "is.gd",
    "lnkd.in",
    "ow.ly",
    "rebrand.ly",
    "shorturl.at",
    "tiny.cc",
    "tinyurl.com",
}


@dataclass(frozen=True)
class LinkCheckResult:
    original_url: str
    url: str
    ok: bool
    status: Optional[int] = None
    reason: str = ""
    changed: bool = False

    def to_dict(self):
        return asdict(self)


def normalize_url(url: str, *, strip_tracking: bool = True) -> str:
    """Return a canonical HTTP(S) URL or an empty string when unsafe/invalid."""
    if not isinstance(url, str):
        return ""
    value = html.unescape(url).strip().strip("<>\"'")
    value = re.sub(r"[\s\u0000-\u001f\u007f]+$", "", value)
    value = value.rstrip(".,;:!?)]}")
    if value.startswith("//"):
        value = "https:" + value

    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""

    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if not parsed.hostname or parsed.username or parsed.password:
        return ""

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return ""

    try:
        port = parsed.port
    except ValueError:
        return ""
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = f"{hostname}:{port}" if port else hostname

    query = parsed.query
    if strip_tracking and query:
        kept = []
        for key, value_part in parse_qsl(query, keep_blank_values=True):
            key_lower = key.lower()
            if key_lower in TRACKING_KEYS or key_lower.startswith(TRACKING_PREFIXES):
                continue
            kept.append((key, value_part))
        query = urlencode(kept, doseq=True)

    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def is_safe_remote_url(url: str, *, allow_private: bool = False) -> bool:
    """Reject local/private destinations before server-side link checks."""
    normalized = normalize_url(url, strip_tracking=False)
    if not normalized:
        return False
    if allow_private:
        return True

    hostname = urlsplit(normalized).hostname or ""
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return False

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            }
        except (OSError, socket.gaierror):
            return False
        return bool(addresses) and all(_is_public_ip(address) for address in addresses)
    return _is_public_ip(hostname)


class SafeRedirectHandler(HTTPRedirectHandler):
    """Validate every redirect target so feeds cannot turn checks into SSRF."""

    def __init__(self, *, allow_private: bool = False):
        super().__init__()
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urljoin(req.full_url, newurl)
        if not is_safe_remote_url(absolute, allow_private=self.allow_private):
            raise HTTPError(absolute, 403, "unsafe redirect target", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def _request(opener, url: str, method: str, timeout: float):
    hostname = (urlsplit(url).hostname or "").lower()
    request_user_agent = "curl/8.7.1" if hostname in KNOWN_SHORTENERS else USER_AGENT
    headers = {
        "User-Agent": request_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }
    if method == "GET":
        headers["Range"] = "bytes=0-0"
    req = Request(url, headers=headers, method=method)
    return opener.open(req, timeout=timeout)


def resolve_and_validate(
    url: str,
    *,
    timeout: float = 8,
    allow_private: bool = False,
    opener=None,
) -> LinkCheckResult:
    """Follow redirects, remove tracking parameters, and verify reachability."""
    original = url if isinstance(url, str) else ""
    cleaned = normalize_url(original)
    if not cleaned:
        return LinkCheckResult(original, "", False, reason="invalid_or_unsafe_scheme")
    if not is_safe_remote_url(cleaned, allow_private=allow_private):
        return LinkCheckResult(original, cleaned, False, reason="unsafe_or_unresolvable_host")

    active_opener = opener or build_opener(SafeRedirectHandler(allow_private=allow_private))
    last_error = ""
    last_status = None
    original_host = (urlsplit(cleaned).hostname or "").lower()

    for method in ("HEAD", "GET"):
        try:
            with _request(active_opener, cleaned, method, timeout) as response:
                status = getattr(response, "status", None) or response.getcode()
                final_url = normalize_url(response.geturl())
                if not final_url or not is_safe_remote_url(final_url, allow_private=allow_private):
                    return LinkCheckResult(original, final_url, False, status, "unsafe_final_url")
                if 200 <= status < 400:
                    final_host = (urlsplit(final_url).hostname or "").lower()
                    if original_host in KNOWN_SHORTENERS and final_host == original_host:
                        last_status = status
                        last_error = "unexpanded_shortener"
                        continue
                    return LinkCheckResult(
                        original,
                        final_url,
                        True,
                        status,
                        "ok",
                        final_url != cleaned,
                    )
                last_status = status
                last_error = f"http_{status}"
        except HTTPError as exc:
            try:
                last_status = exc.code
                final_url = normalize_url(exc.geturl() or cleaned)
                last_error = f"http_{exc.code}"
                if method == "GET" and exc.code in RESTRICTED_BUT_REACHABLE:
                    final_host = (urlsplit(final_url).hostname or "").lower()
                    if (
                        final_host not in KNOWN_SHORTENERS
                        and is_safe_remote_url(final_url, allow_private=allow_private)
                    ):
                        return LinkCheckResult(
                            original,
                            final_url,
                            True,
                            exc.code,
                            "reachable_but_restricted",
                            final_url != cleaned,
                        )
            finally:
                exc.close()
        except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            last_error = exc.__class__.__name__.lower()

    return LinkCheckResult(original, cleaned, False, last_status, last_error or "unreachable")
