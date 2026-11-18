"""Transport restrictions for requests carrying Keycafe credentials."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


def trusted_destination(url, base_url):
    try:
        target, base = urlsplit(url), urlsplit(base_url)
        return (
            target.scheme == base.scheme == "https"
            and target.username is None and base.username is None
            and bool(target.hostname) and target.hostname == base.hostname
            and (target.port if target.port is not None else 443)
            == (base.port if base.port is not None else 443)
        )
    except ValueError:
        return False


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_destination(newurl, req.full_url):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


open_authenticated = build_opener(SameOriginRedirectHandler()).open
