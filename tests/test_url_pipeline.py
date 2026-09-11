import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_article_urls import process_entries  # noqa: E402
from parse_bird_output import parse_bird_text  # noqa: E402
from render_newsroom_html import build_html  # noqa: E402
from url_tools import is_safe_remote_url, normalize_url, resolve_and_validate  # noqa: E402
from fetch_web_news import get_domain  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def _respond(self, include_body):
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "/article?utm_source=test&id=7")
            self.end_headers()
            return
        if self.path.startswith("/article"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if include_body:
                self.wfile.write(b"ok")
            return
        if self.path.startswith("/restricted"):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_HEAD(self):
        self._respond(False)

    def do_GET(self):
        self._respond(True)

    def log_message(self, _format, *_args):
        return


class LocalHTTPServerMixin:
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)


class URLToolsTests(LocalHTTPServerMixin, unittest.TestCase):
    def test_normalize_rejects_unsafe_schemes_and_strips_tracking(self):
        self.assertEqual(normalize_url("javascript:alert(1)"), "")
        self.assertEqual(normalize_url("file:///tmp/a"), "")
        self.assertEqual(
            normalize_url("https://Example.com/post?id=2&utm_source=x#part"),
            "https://example.com/post?id=2",
        )

    def test_redirect_is_expanded_and_checked(self):
        result = resolve_and_validate(
            f"{self.base}/redirect",
            timeout=2,
            allow_private=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.url, f"{self.base}/article?id=7")
        self.assertTrue(result.changed)

    def test_missing_link_is_rejected(self):
        result = resolve_and_validate(
            f"{self.base}/missing",
            timeout=2,
            allow_private=True,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 404)

    def test_access_controlled_page_is_kept_as_reachable(self):
        result = resolve_and_validate(
            f"{self.base}/restricted",
            timeout=2,
            allow_private=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "reachable_but_restricted")

    def test_unresolved_public_hostname_is_not_preemptively_rejected(self):
        with patch("url_tools.socket.getaddrinfo", side_effect=OSError("dns down")):
            self.assertTrue(is_safe_remote_url("https://example.com/article"))

    def test_batch_processing_deduplicates_redirect_targets(self):
        entries = [
            {"index": 0, "url": f"{self.base}/redirect", "parts": ["A", "", "RSS"]},
            {"index": 1, "url": f"{self.base}/article?id=7", "parts": ["B", "", "RSS"]},
        ]
        cache = {}
        results = process_entries(
            entries,
            workers=2,
            timeout=2,
            cache=cache,
            allow_private=True,
        )
        self.assertTrue(results[0].ok)
        self.assertTrue(results[1].ok)
        self.assertEqual(results[0].url, results[1].url)


class BirdParserTests(unittest.TestCase):
    def test_multiline_tweet_keeps_permalink_and_context(self):
        raw = """
@AndrewYNg (Andrew Ng):
New course: Build LLM applications that respond quickly on fast hardware.

Fast inference makes lengthy agentic workflows go faster.
https://t.co/P8vchGAr22
VIDEO: https://pbs.twimg.com/video.jpg
date: Fri Jul 17 15:47:30 +0000 2026
url: https://twitter.com/AndrewYNg/status/2078144569594761591
──────────────────────────────────────────────────
"""
        records = parse_bird_text(raw)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["url"],
            "https://x.com/AndrewYNg/status/2078144569594761591",
        )
        self.assertIn("New course", records[0]["title"])
        self.assertIn("agentic workflows", records[0]["fulltext"])
        self.assertNotEqual(records[0]["title"], "https://t.co/P8vchGAr22")

    def test_incomplete_block_without_permalink_is_dropped(self):
        raw = "@OpenAI (OpenAI):\nA launch https://t.co/abc\n"
        self.assertEqual(parse_bird_text(raw), [])


class RenderSafetyTests(unittest.TestCase):
    def test_www_prefix_removal_does_not_damage_wired_domain(self):
        self.assertEqual(get_domain("https://www.wired.com/story/example"), "wired.com")

    def test_renderer_never_emits_dangerous_href(self):
        rows = [
            {
                "rank": 1,
                "title": "Unsafe",
                "url": "javascript:alert(1)",
                "source": "test",
                "section": "应用层面（Application）",
            }
        ]
        rendered = build_html("test", rows)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn("链接未通过安全校验", rendered)

    def test_renderer_escapes_safe_url(self):
        rows = [
            {
                "rank": 1,
                "title": "Safe",
                "url": "https://example.com/a?id=1&utm_source=x",
                "source": "test",
                "section": "应用层面（Application）",
            }
        ]
        rendered = build_html("test", rows)
        self.assertIn('href="https://example.com/a?id=1"', rendered)
        self.assertNotIn("utm_source", rendered)


if __name__ == "__main__":
    unittest.main()
