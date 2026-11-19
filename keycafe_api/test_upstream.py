import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from django.test import override_settings
from .testing import UpstreamIsolatedTestCase
from . import upstream
from .keycafe import KeycafeAuth, KeycafeError, fetch_inventory, fetch_key_detail_if_needed, fetch_pickup_time, keycafe_fetch


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

    def test_backoff_is_capped_and_monotonic(self):
        with patch('keycafe_api.upstream.time.time', return_value=1000):
            upstream.backoff(999999)
            with upstream.database() as db:
                until = db.execute('SELECT until FROM cooldown WHERE id = 1').fetchone()[0]
            self.assertEqual(until, 1000 + upstream.MAX_COOLDOWN_SECONDS)
            # A shorter concurrent Retry-After must not shorten an active longer cooldown.
            upstream.backoff(60)
            with upstream.database() as db:
                until_after = db.execute('SELECT until FROM cooldown WHERE id = 1').fetchone()[0]
            self.assertEqual(until_after, 1000 + upstream.MAX_COOLDOWN_SECONDS)

    def test_database_closes_connection_and_uses_wal(self):
        with upstream.database() as db:
            mode = db.execute('PRAGMA journal_mode').fetchone()[0]
            self.assertEqual(mode.lower(), 'wal')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')

    @patch('keycafe_api.upstream.sqlite3.connect', side_effect=sqlite3.OperationalError('disk full'))
    @patch('keycafe_api.views.resolve_auth', return_value=KeycafeAuth('dummy'))
    def test_upstream_store_error_is_not_reported_as_group_store_error(self, _auth, _connect):
        response = self.client.get('/api/inventory/')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Zwischenspeicher', response.json()['error'])
        self.assertNotIn('Gruppenspeicher', response.json()['error'])

    @patch('keycafe_api.keycafe.fetch_all_pages')
    @patch('keycafe_api.keycafe.keycafe_json')
    def test_upstream_cache_minimizes_persisted_pii(self, fetch_json, fetch_pages):
        auth = KeycafeAuth('dummy')
        fetch_pages.return_value = [{
            'id': 7,
            'name': 'Werkstatt',
            'owner': {'email': 'owner-secret@example.com'},
            'notes': 'door-code-1234',
            'currentUser': {'id': 9, 'firstName': 'Ada', 'mobile': '+49-555-0100', 'email': 'ada@example.com'},
        }]
        fetch_inventory(auth)

        fetch_json.return_value = {
            'id': 7,
            'name': 'Werkstatt',
            'serialNumber': 'SER-7',
            'owner': {'email': 'owner-secret@example.com'},
            'currentUser': {'id': 9, 'firstName': 'Ada', 'mobile': '+49-555-0100', 'email': 'ada@example.com'},
        }
        fetch_key_detail_if_needed(auth, {'id': 7, 'currentUser': {'id': 9}})

        fetch_json.return_value = [{
            'dateCreated': '2026-11-13T08:30:00Z',
            'user': {'email': 'historical-user@example.com', 'mobile': '+49-555-0199'},
            'bin': {'secretCode': '9999'},
        }]
        result = fetch_pickup_time(auth, {'id': 7, 'currentUser': {'id': 9, 'email': 'ada@example.com'}})
        self.assertEqual(result['removedAt'], '2026-11-13T08:30:00Z')

        with upstream.database() as db:
            rows = db.execute('SELECT key, value FROM cache').fetchall()
        all_keys = '\n'.join(row[0] for row in rows)
        all_values = '\n'.join(row[1] for row in rows)
        self.assertNotIn('ada@example.com', all_keys)
        for forbidden in ('owner-secret@example.com', 'door-code-1234', '+49-555-0100', 'historical-user@example.com', '+49-555-0199', 'secretCode'):
            self.assertNotIn(forbidden, all_values)

    def test_failures_are_not_cached(self):
        loader = Mock(side_effect=KeycafeError(502, 'failed'))
        for _ in range(2):
            with self.assertRaises(KeycafeError):
                upstream.cached('failure', 60, loader)
        self.assertEqual(loader.call_count, 2)
