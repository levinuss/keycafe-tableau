from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from django.test import override_settings
from .testing import UpstreamIsolatedTestCase
from . import upstream
from .keycafe import KeycafeAuth, KeycafeError, keycafe_fetch


class UpstreamTests(UpstreamIsolatedTestCase):
    def test_cache_reused_and_expires(self):
        loader = Mock(return_value=[{'id': 1}])
        with patch('keycafe_api.upstream.time.time', return_value=100):
            self.assertEqual(upstream.cached('inventory', 60, loader), [{'id': 1}])
            upstream.cached('inventory', 60, loader)
        loader.assert_called_once()
        with patch('keycafe_api.upstream.time.time', return_value=161):
            upstream.cached('inventory', 60, loader)
        self.assertEqual(loader.call_count, 2)

    def test_slow_fill_allows_hits_and_shares_result_with_waiters(self):
        started, release = Event(), Event()

        def slow_loader():
            started.set()
            if not release.wait(5):
                raise TimeoutError()
            return "fresh"

        unexpected = Mock(side_effect=AssertionError("duplicate fill"))
        upstream.cached("warm", 60, lambda: "ready")
        with ThreadPoolExecutor(max_workers=3) as pool:
            fill = pool.submit(upstream.cached, "cold", 60, slow_loader)
            try:
                self.assertTrue(started.wait(2))
                waiter = pool.submit(upstream.cached, "cold", 60, unexpected)
                hit = pool.submit(upstream.cached, "warm", 60, unexpected)
                self.assertEqual(hit.result(timeout=2), "ready")
            finally:
                release.set()
            self.assertEqual(fill.result(), "fresh")
            self.assertEqual(waiter.result(), "fresh")

    @override_settings(KEYCAFE_REQUESTS_PER_MINUTE=2)
    def test_rolling_budget_expires(self):
        with patch('keycafe_api.upstream.time.time', return_value=100):
            upstream.reserve()
            upstream.reserve()
            with self.assertRaises(KeycafeError):
                upstream.reserve()
        with patch('keycafe_api.upstream.time.time', return_value=161):
            upstream.reserve()

    @patch('keycafe_api.keycafe.open_authenticated')
    def test_429_blocks_subsequent_network_calls(self, fetch):
        fetch.side_effect = HTTPError('https://www.keycafe.com/v0/key', 429, 'limit', {'Retry-After': '120'}, None)
        with patch('keycafe_api.upstream.time.time', return_value=100):
            with self.assertRaises(KeycafeError) as error:
                keycafe_fetch('https://www.keycafe.com/v0/key', KeycafeAuth('dummy'))
            self.assertEqual(error.exception.status, 503)
        with patch('keycafe_api.upstream.time.time', return_value=170):
            with self.assertRaises(KeycafeError):
                keycafe_fetch('https://www.keycafe.com/v0/key', KeycafeAuth('dummy'))
        fetch.assert_called_once()

    def test_failures_are_not_cached(self):
        loader = Mock(side_effect=KeycafeError(502, 'failed'))
        for _ in range(2):
            with self.assertRaises(KeycafeError):
                upstream.cached('failure', 60, loader)
        self.assertEqual(loader.call_count, 2)
