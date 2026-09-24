import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from .keycafe import KeycafeError, normalize_key, parse_link_header, resolve_auth, summarize_keys
from .demo import demo_groups, demo_keys
from keycafe_tableau.env import load_env_file


class KeycafeModelTests(SimpleTestCase):
    def test_parse_link_header(self):
        links = parse_link_header(
            '<https://www.keycafe.com/v0/key?page=2>; rel="next", '
            '<https://www.keycafe.com/v0/key?page=5>; rel="last"'
        )

        self.assertEqual(links["next"], "https://www.keycafe.com/v0/key?page=2")
        self.assertEqual(links["last"], "https://www.keycafe.com/v0/key?page=5")

    def test_checked_in_at_home(self):
        key = normalize_key(
            {
                "id": 1,
                "name": "Office",
                "homeLocation": {"id": 10, "name": "Lobby"},
                "currentLocation": {"id": 10, "name": "Lobby"},
            }
        )

        self.assertEqual(key["status"], "at-home")
        self.assertNotIn("atHome", key)
        self.assertEqual(key["statusLabel"], "Vor Ort")

    def test_unexpected_location_stays_unknown(self):
        for home in ({"id": 10}, None):
            with self.subTest(home=home):
                key = normalize_key({
                    "id": 1,
                    "homeLocation": home,
                    "currentLocation": {"id": 20, "name": "Unexpected location"},
                })
                self.assertEqual(key["status"], "unknown")
                self.assertEqual(key["statusLabel"], "Ungeklärt")
                self.assertEqual(summarize_keys([key]), {
                    "total": 1, "at-home": 0, "checked-out": 0, "unknown": 1,
                })

    def test_holder_takes_precedence_over_location(self):
        key = normalize_key({
            "id": 1,
            "homeLocation": {"id": 10},
            "currentLocation": {"id": 10},
            "currentUser": {"firstName": "Ada"},
        })
        self.assertEqual(key["status"], "checked-out")
        self.assertEqual(key["statusLabel"], "Ausgegeben")

    def test_checked_out_holder(self):
        key = normalize_key(
            {
                "id": 2,
                "name": "Van",
                "currentUser": {
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "email": "ada@example.com",
                },
            }
        )

        self.assertEqual(key["status"], "checked-out")
        self.assertEqual(key["currentUser"]["name"], "Ada Lovelace")

    def test_summary_counts(self):
        summary = summarize_keys(
            [
                normalize_key(
                    {
                        "id": 1,
                        "homeLocation": {"id": 1},
                        "currentLocation": {"id": 1},
                    }
                ),
                normalize_key({"id": 2, "currentUser": {"email": "user@example.com"}}),
                normalize_key({"id": 3}),
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["at-home"], 1)
        self.assertEqual(summary["checked-out"], 1)
        self.assertEqual(summary["unknown"], 1)

    def test_resolve_auth_uses_server_token_env(self):
        with patch.dict(
            os.environ,
            {"KEYCAFE_EMAIL": "user@example.com", "KEYCAFE_TOKEN": "secret-token"},
        ):
            auth = resolve_auth()

        expected = base64.b64encode(
            b"user@example.com/token:secret-token"
        ).decode("ascii")
        self.assertEqual(auth.authorization, f"Basic {expected}")

    def test_resolve_auth_uses_api_key_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "KEYCAFE_EMAIL": "user@example.com",
                "KEYCAFE_TOKEN": "secret-key",
                "KEYCAFE_AUTH_MODE": "key",
            },
        ):
            auth = resolve_auth()

        expected = base64.b64encode(
            b"user@example.com/key:secret-key"
        ).decode("ascii")
        self.assertEqual(auth.authorization, f"Basic {expected}")

    def test_resolve_auth_rejects_unknown_auth_mode(self):
        with patch.dict(
            os.environ,
            {
                "KEYCAFE_EMAIL": "user@example.com",
                "KEYCAFE_TOKEN": "secret",
                "KEYCAFE_AUTH_MODE": "password",
            },
        ):
            with self.assertRaises(KeycafeError) as raised:
                resolve_auth()

        self.assertEqual(raised.exception.status, 500)

    def test_resolve_auth_requires_server_token_env(self):
        with patch.dict(os.environ, {"KEYCAFE_EMAIL": "", "KEYCAFE_TOKEN": ""}):
            with self.assertRaises(KeycafeError) as raised:
                resolve_auth()

        self.assertEqual(raised.exception.status, 503)

    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "KEYCAFE_EMAIL='user@example.com'\n"
                'KEYCAFE_TOKEN="token-value"\n'
                "KEYCAFE_USER_AGENT=KeycafeTableau/0.1 # local app\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                load_env_file(env_path)
                self.assertEqual(os.environ["KEYCAFE_EMAIL"], "user@example.com")
                self.assertEqual(os.environ["KEYCAFE_TOKEN"], "token-value")
                self.assertEqual(
                    os.environ["KEYCAFE_USER_AGENT"], "KeycafeTableau/0.1"
                )

    def test_load_env_file_replaces_empty_process_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("KEYCAFE_TOKEN=token-value\n", encoding="utf-8")

            with patch.dict(os.environ, {"KEYCAFE_TOKEN": ""}, clear=True):
                load_env_file(env_path)
                self.assertEqual(os.environ["KEYCAFE_TOKEN"], "token-value")


class DemoModeTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_demo_groups_include_all_keys(self):
        groups = demo_groups()

        self.assertEqual(groups[0]["id"], "demo-all")
        self.assertEqual(groups[0]["name"], "Alle Schlüssel")
        self.assertGreaterEqual(len(groups), 4)

    def test_demo_keys_cover_all_dashboard_states(self):
        payload = demo_keys("demo-all")

        statuses = {key["status"] for key in payload["keys"]}
        self.assertEqual(
            statuses,
            {"at-home", "checked-out", "unknown"},
        )
        self.assertEqual(set(payload), {"keys", "summary"})
        self.assertEqual(payload["summary"], {
            "total": 9, "at-home": 5, "checked-out": 3, "unknown": 1,
        })

    def test_demo_uses_only_one_smartbox(self):
        keys = demo_keys()["keys"]
        locations = {
            key[field]["name"]
            for key in keys
            for field in ("currentLocation",)
            if key[field]
        }
        self.assertEqual(locations, {"SmartBox am Empfang"})
        self.assertEqual(
            {key["statusLabel"] for key in keys},
            {"Vor Ort", "Ausgegeben", "Ungeklärt"},
        )

    def test_demo_keys_are_filtered_by_group(self):
        payload = demo_keys("demo-fleet")

        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(
            {key["name"] for key in payload["keys"]},
            {"Dienstwagen 01", "Dienstwagen 02", "Transporter"},
        )

    def test_demo_api_does_not_require_credentials(self):
        with patch.dict(
            os.environ,
            {
                "KEYCAFE_DEMO_MODE": "true",
                "KEYCAFE_EMAIL": "",
                "KEYCAFE_TOKEN": "",
            },
        ):
            config_response = self.client.get("/api/config/")
            groups_response = self.client.get("/api/groups/")
            keys_response = self.client.get("/api/keys/?group=demo-it")

        self.assertEqual(config_response.status_code, 200)
        self.assertTrue(config_response.json()["demoMode"])
        self.assertTrue(config_response.json()["ready"])
        self.assertEqual(groups_response.status_code, 200)
        self.assertEqual(set(groups_response.json()), {"groups"})
        self.assertEqual(keys_response.status_code, 200)
        self.assertEqual(keys_response.json()["summary"]["total"], 3)
