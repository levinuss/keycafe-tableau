from unittest import TestCase
from urllib.request import Request

from .transport import SameOriginRedirectHandler, trusted_destination


class TransportTests(TestCase):
    def test_destination_policy(self):
        base = "https://www.keycafe.com"
        self.assertTrue(trusted_destination(base + ":443/v0/key", base))
        for url in ["http://www.keycafe.com", "https://other.example",
                    base + ":444", "https://user@www.keycafe.com", base + ":invalid"]:
            with self.subTest(url=url):
                self.assertFalse(trusted_destination(url, base))

    def test_redirects_apply_origin_check_for_both_request_methods(self):
        base = "https://www.keycafe.com"
        handler = SameOriginRedirectHandler()
        for method in ("GET", "POST"):
            request = Request(base, method=method)
            for target in ("https://other.example", "http://www.keycafe.com", base + ":444"):
                self.assertIsNone(handler.redirect_request(request, None, 302, "", {}, target))
            redirect = handler.redirect_request(request, None, 302, "", {}, base + "/next")
            self.assertEqual(redirect.full_url, base + "/next")
