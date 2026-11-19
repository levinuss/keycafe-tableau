import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class ProxyAuthenticationBoundaryTests(SimpleTestCase):
    def test_static_assets_are_served_with_debug_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app-test.js").write_text("console.log('ok');", encoding="utf-8")
            (root / "app-test.css").write_text("body { color: black; }", encoding="utf-8")
            with self.settings(STATIC_ROOT=root):
                from django.test import Client
                client = Client()
                for filename, content_type in [("app-test.js", "javascript"), ("app-test.css", "text/css")]:
                    response = client.get(f"/assets/{filename}")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(content_type, response["Content-Type"])
                    response.close()
                self.assertEqual(client.get("/assets/missing.js").status_code, 404)

    def test_api_needs_no_app_session_or_identity_headers(self):
        with patch.dict(os.environ, {"KEYCAFE_DEMO_MODE": "true", "OIDC_ENABLED": "true"}):
            for path in ("/api/config/", "/api/groups/", "/api/keys/?group=demo-all"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(set(response.cookies), {"csrftoken"} if path == "/api/config/" else set())
                    self.assertFalse(hasattr(response.wsgi_request, "session"))
                    self.assertFalse(hasattr(response.wsgi_request, "user"))
                    forwarded = self.client.get(
                        path,
                        HTTP_X_AUTHENTIK_USERNAME="example-user",
                        HTTP_X_AUTHENTIK_GROUPS="example-group",
                    )
                    original, with_headers = response.json(), forwarded.json()
                    original.pop("csrfToken", None)
                    with_headers.pop("csrfToken", None)
                    self.assertEqual(original, with_headers)
            self.assertNotIn("oidcEnabled", self.client.get("/api/config/").json())

    def test_frontend_needs_no_app_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "frontend" / "dist" / "index.html"
            index.parent.mkdir(parents=True)
            index.write_text('<html lang="de">Tableau</html>', encoding="utf-8")
            with self.settings(BASE_DIR=root):
                response = self.client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Tableau", b"".join(response.streaming_content))
                self.assertFalse(response.cookies)

    def test_former_auth_routes_are_gone(self):
        for path in ("/oidc/login/", "/oidc/callback/", "/oidc/logout/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_security_headers_and_csrf_cookie_flags(self):
        with self.settings(CSRF_COOKIE_SECURE=True, CSRF_COOKIE_HTTPONLY=True):
            response = self.client.get("/api/config/")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        cookie = response.cookies["csrftoken"]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])

    def test_secret_key_enforcement_and_env_parsing(self):
        from django.core.exceptions import ImproperlyConfigured
        from keycafe_tableau.settings import _env_bool, _env_int, _parse_csv, _resolve_secret_key

        for bad in ("", "local-development-keycafe-tableau", "replace-with-a-random-secret"):
            with self.subTest(secret=bad), patch.dict(os.environ, {"DJANGO_SECRET_KEY": bad}):
                with self.assertRaises(ImproperlyConfigured):
                    _resolve_secret_key(debug=False, running_tests=False)
                self.assertTrue(_resolve_secret_key(debug=True, running_tests=False))
                self.assertTrue(_resolve_secret_key(debug=False, running_tests=True))

        with patch.dict(os.environ, {"DJANGO_SECRET_KEY": "custom-production-secret"}):
            self.assertEqual(_resolve_secret_key(debug=False, running_tests=False), "custom-production-secret")

        self.assertEqual(_parse_csv(" tableau.example.org , , 127.0.0.1 "), ["tableau.example.org", "127.0.0.1"])
        with patch.dict(os.environ, {"KEYCAFE_CACHE_SECONDS": "", "DJANGO_CSRF_COOKIE_SECURE": ""}):
            self.assertEqual(_env_int("KEYCAFE_CACHE_SECONDS", 60), 60)
            self.assertTrue(_env_bool("DJANGO_CSRF_COOKIE_SECURE", True))
            self.assertFalse(_env_bool("DJANGO_CSRF_COOKIE_SECURE", False))
