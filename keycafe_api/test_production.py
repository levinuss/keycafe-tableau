import os
from urllib.error import URLError
from unittest.mock import patch

from django.test import SimpleTestCase

from .keycafe import KeycafeAuth, KeycafeError, fetch_key_detail_if_needed, fetch_groups, keycafe_fetch, normalize_key


class DetailTests(SimpleTestCase):
    auth = KeycafeAuth("Basic dummy")

    @patch("keycafe_api.keycafe.keycafe_json")
    def test_partial_home_information_fetches_details(self, fetch):
        fetch.return_value = {"id": 1, "currentUser": {"firstName": "Ada"}}
        result = fetch_key_detail_if_needed(self.auth, {"id": 1, "homeLocation": {"id": 2}})
        fetch.assert_called_once()
        self.assertEqual(normalize_key(result)["status"], "checked-out")

    @patch("keycafe_api.keycafe.keycafe_json")
    def test_complete_states_need_no_detail_fetch(self, fetch):
        for state in [
            {"currentUser": {"email": "ada@example.org"}},
            {"homeLocation": {"id": 2}, "currentLocation": {"id": 2, "name": "Box"}},
        ]:
            key = {"id": 1, "serialNumber": "ABC", **state}
            self.assertEqual(fetch_key_detail_if_needed(self.auth, key), key)
        fetch.assert_not_called()

    @patch("keycafe_api.keycafe.keycafe_json")
    def test_detail_does_not_preserve_stale_holder(self, fetch):
        fetch.return_value = {"id": 1, "homeLocation": {"id": 2}, "currentLocation": {"id": 2}}
        result = fetch_key_detail_if_needed(self.auth, {"id": 1, "currentUser": {"id": 3}})
        self.assertEqual(normalize_key(result)["status"], "at-home")
        self.assertIsNone(normalize_key(result)["currentUser"])

    @patch("keycafe_api.keycafe.keycafe_json")
    def test_invalid_details_and_failures_are_visible(self, fetch):
        for payload in [None, [], "error", {"id": 999}]:
            fetch.return_value = payload
            self.assertTrue(fetch_key_detail_if_needed(self.auth, {"id": 1})["detailError"])
        fetch.side_effect = KeycafeError(502, "Nicht erreichbar")
        self.assertEqual(fetch_key_detail_if_needed(self.auth, {"id": 1})["detailError"], "Nicht erreichbar")

    @patch("keycafe_api.keycafe.urlopen", side_effect=URLError("private upstream details"))
    def test_network_failure_is_sanitized(self, _fetch):
        with self.assertRaises(KeycafeError) as raised:
            keycafe_fetch("https://www.keycafe.com/v0/key", self.auth)
        self.assertEqual(raised.exception.status, 502)
        self.assertNotIn("private", str(raised.exception))

    @patch("keycafe_api.keycafe.fetch_all_pages")
    def test_groups_drop_unused_fields(self, fetch):
        fetch.return_value = [{"id": 1, "name": "Keys", "type": "KEY", "owner": {"email": "private"}}]
        self.assertEqual(fetch_groups(self.auth), [{"id": 1, "name": "Keys"}])

    def test_keys_drop_unused_personal_and_location_data(self):
        result = normalize_key({"id": 1, "owner": {"email": "private"}, "currentUser": {"firstName": "Ada", "mobile": "private"}})
        self.assertEqual(set(result), {"id", "name", "serialNumber", "currentLocation", "currentUser", "status", "statusLabel", "detailError"})
        self.assertEqual(set(result["currentUser"]), {"name", "email"})

    def test_health_is_local_and_api_is_not_cacheable(self):
        self.assertEqual(self.client.get("/healthz/").json(), {"status": "ok"})
        with patch.dict(os.environ, {"KEYCAFE_DEMO_MODE": "true"}):
            self.assertIn("no-store", self.client.get("/api/keys/")["Cache-Control"])
