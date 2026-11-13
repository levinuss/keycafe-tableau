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
