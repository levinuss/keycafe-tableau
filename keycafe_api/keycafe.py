import base64
import hashlib
import http.client
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request

from django.conf import settings

from . import upstream
from .transport import open_authenticated, trusted_destination


KEYCAFE_BASE_URL = os.environ.get("KEYCAFE_BASE_URL", "https://www.keycafe.com")
KEYCAFE_MAX_PAGES = int(os.environ.get("KEYCAFE_MAX_PAGES") or "25")
KEYCAFE_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
KEYCAFE_ENRICH_WORKERS = 4
PICKUP_CACHE_SECONDS = 900
KEYCAFE_USER_AGENT = os.environ.get(
    "KEYCAFE_USER_AGENT",
    "KeycafeTableau/0.1 (+https://docs.keycafe.com/reference/api-overview)",
)
LINK_HEADER_RE = re.compile(r"<([^>]+)>\s*;\s*([^,]*)")
LINK_REL_RE = re.compile(r'(?:^|;)\s*rel\s*=\s*(?:"([^"]+)"|([^;\s]+))', re.IGNORECASE)


class KeycafeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class KeycafeAuth:
    authorization: str


def has_server_credentials() -> bool:
    return bool(_server_credentials())


def resolve_auth() -> KeycafeAuth:
    server_credentials = _server_credentials()

    if not server_credentials:
        raise KeycafeError(
            503,
            "Keycafe ist nicht eingerichtet. Bitte KEYCAFE_EMAIL und KEYCAFE_TOKEN auf dem Server setzen.",
        )

    auth_mode = os.environ.get("KEYCAFE_AUTH_MODE", "token").strip().lower()
    if auth_mode not in {"token", "key"}:
        raise KeycafeError(
            500,
            "Ungültige Keycafe-Authentifizierung. KEYCAFE_AUTH_MODE muss 'token' oder 'key' sein.",
        )

    username = f"{server_credentials['email']}/{auth_mode}"
    encoded = base64.b64encode(
        f"{username}:{server_credentials['token']}".encode("utf-8")
    ).decode("ascii")
    return KeycafeAuth(authorization=f"Basic {encoded}")


def _minimize_location(location) -> dict | None:
    if not isinstance(location, dict):
        return None
    return {"id": location.get("id"), "name": location.get("name")}


def _minimize_user(user) -> dict | None:
    if not isinstance(user, dict):
        return None
    return {
        field: user[field]
        for field in ("id", "firstName", "lastName", "email", "contactEmail")
        if field in user
    }


def _minimize_key(key: dict) -> dict:
    minimized = {
        "id": key.get("id"),
        "name": key.get("name"),
        "homeLocation": _minimize_location(key.get("homeLocation")),
        "currentLocation": _minimize_location(key.get("currentLocation")),
        "currentUser": _minimize_user(key.get("currentUser")),
    }
    if "serialNumber" in key:
        minimized["serialNumber"] = key.get("serialNumber")
    return minimized


def fetch_inventory(auth: KeycafeAuth):
    return upstream.cached(
        f"inventory:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}",
        settings.KEYCAFE_CACHE_SECONDS,
        lambda: [_minimize_key(row) for row in fetch_all_pages("/v0/key", auth)],
    )


def _pickup_ttl(pickup: dict) -> int:
    if isinstance(pickup, dict) and pickup.get("removedAt"):
        return max(settings.KEYCAFE_CACHE_SECONDS, PICKUP_CACHE_SECONDS)
    return settings.KEYCAFE_CACHE_SECONDS


def _enrich_key(auth: KeycafeAuth, key: dict, rate_limited: Event) -> dict:
    enriched = fetch_key_detail_if_needed(auth, key, rate_limited=rate_limited)
    return normalize_key(fetch_pickup_time(auth, enriched, rate_limited=rate_limited))


def fetch_keys(auth: KeycafeAuth, key_ids=None):
    if key_ids is not None and not key_ids:
        return {
            "missingKeyIds": [],
            "keys": [],
            "summary": summarize_keys([]),
        }

    shallow_keys = fetch_inventory(auth)
    missing_ids = []
    if key_ids is not None:
        wanted = set(map(str, key_ids))
        shallow_keys = [key for key in shallow_keys if str(key.get("id")) in wanted]
        missing_ids = sorted(wanted - {str(key.get("id")) for key in shallow_keys})

    rate_limited = Event()
    if len(shallow_keys) <= 1:
        normalized_keys = [_enrich_key(auth, key, rate_limited) for key in shallow_keys]
    else:
        with ThreadPoolExecutor(max_workers=min(KEYCAFE_ENRICH_WORKERS, len(shallow_keys))) as pool:
            normalized_keys = list(pool.map(lambda key: _enrich_key(auth, key, rate_limited), shallow_keys))

    return {
        "missingKeyIds": missing_ids,
        "keys": normalized_keys,
        "summary": summarize_keys(normalized_keys),
    }


def fetch_pickup_time(auth: KeycafeAuth, key: dict, rate_limited: Event | None = None) -> dict:
    user = key.get("currentUser")
    if not isinstance(user, dict) or not user or not key.get("id"):
        return key
    user_digest = hashlib.sha256(json.dumps(user, sort_keys=True).encode("utf-8")).hexdigest()
    cache_key = f"pickup:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}:{key['id']}:{user_digest}"

    def load_pickup():
        events = keycafe_json(keycafe_url("/v0/event", {"key": key["id"], "type": "PICKUP"}), auth)
        if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
            return None
        return {"removedAt": events[0].get("dateCreated") if events else None}

    try:
        if rate_limited and rate_limited.is_set():
            row = upstream.cache_row(cache_key)
            pickup = json.loads(row[0]) if row else None
            return {**key, "removedAt": pickup.get("removedAt") if isinstance(pickup, dict) else None}
        # Events describe completed pickups; exchange timestamps describe authorization.
        # Search Events returns newest first, so only the first page is needed.
        pickup = upstream.cached(
            cache_key,
            _pickup_ttl,
            load_pickup,
            validate=lambda value: isinstance(value, dict),
        )
        if not isinstance(pickup, dict):
            raise KeycafeError(502, "Keycafe hat ungültige Entnahmeereignisse zurückgegeben.")
        return {**key, "removedAt": pickup.get("removedAt")}
    except KeycafeError as error:
        if rate_limited and error.status == 503:
            rate_limited.set()
        # Missing history must not hide the live inventory or holder.
        return {**key, "removedAt": None}


def fetch_key_detail_if_needed(auth: KeycafeAuth, key: dict, rate_limited: Event | None = None) -> dict:
    user = key.get("currentUser") if isinstance(key.get("currentUser"), dict) else {}
    location = key.get("currentLocation") if isinstance(key.get("currentLocation"), dict) else {}
    home = key.get("homeLocation") if isinstance(key.get("homeLocation"), dict) else {}
    has_holder = any(user.get(field) for field in ("firstName", "lastName", "email", "contactEmail"))
    has_location = location.get("id") is not None and bool(location.get("name")) and home.get("id") is not None
    if not key.get("id") or ("serialNumber" in key and (has_holder or (not user and has_location))):
        return key

    key_id = quote(str(key["id"]), safe="")
    cache_key = f"detail:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}:{key['id']}"

    def load_detail():
        detail = keycafe_json(f"/v0/key/{key_id}", auth)
        if not isinstance(detail, dict) or str(detail.get("id")) != str(key["id"]):
            return None
        return _minimize_key(detail)

    try:
        if rate_limited and rate_limited.is_set():
            row = upstream.cache_row(cache_key)
            if not row:
                return {**key, "detailError": "Keycafe pausiert wegen des Anfragelimits. Bitte später erneut versuchen."}
            detail = json.loads(row[0])
        else:
            detail = upstream.cached(
                cache_key,
                settings.KEYCAFE_CACHE_SECONDS,
                load_detail,
                validate=lambda detail: isinstance(detail, dict) and str(detail.get("id")) == str(key["id"]),
            )
        if not isinstance(detail, dict) or str(detail.get("id")) != str(key["id"]):
            raise KeycafeError(502, "Keycafe hat ungültige Schlüsseldetails zurückgegeben.")
        # Preserve only descriptive fields, never stale location/holder state.
        return {**{field: key.get(field) for field in ("name", "serialNumber")}, **detail}
    except KeycafeError as error:
        if rate_limited and error.status == 503:
            rate_limited.set()
        return {**key, "detailError": str(error)}


def fetch_all_pages(path: str, auth: KeycafeAuth, params: dict | None = None) -> list[dict]:
    url = keycafe_url(path, params)
    rows = []
    page_count = 0

    while url:
        page_count += 1
        if page_count > KEYCAFE_MAX_PAGES:
            raise KeycafeError(
                502,
                f"Die Keycafe-Antwort überschreitet die Grenze von {KEYCAFE_MAX_PAGES} Seiten.",
            )

        data, headers = keycafe_fetch(url, auth)
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise KeycafeError(502, "Keycafe hat ein unerwartetes Antwortformat zurückgegeben.")

        rows.extend(data)
        links = {}
        raw_links = headers.get_all("Link") if hasattr(headers, "get_all") else ([headers.get("Link")] if headers.get("Link") else [])
        for raw_header in raw_links or []:
            links.update(parse_link_header(raw_header))
        url = keycafe_url(links["next"]) if links.get("next") else None

    return rows


def keycafe_json(path: str, auth: KeycafeAuth):
    data, _headers = keycafe_fetch(keycafe_url(path), auth)
    return data


def keycafe_fetch(url: str, auth: KeycafeAuth):
    if not trusted_destination(url, KEYCAFE_BASE_URL):
        raise KeycafeError(502, "Die Anfrage erfordert HTTPS und den konfigurierten Keycafe-Server.")

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "de-DE",
            "Authorization": auth.authorization,
            "User-Agent": KEYCAFE_USER_AGENT,
        },
    )

    upstream.reserve()
    try:
        with open_authenticated(request, timeout=20) as response:
            raw = response.read(KEYCAFE_MAX_RESPONSE_BYTES + 1)
            if len(raw) > KEYCAFE_MAX_RESPONSE_BYTES:
                raise KeycafeError(502, "Keycafe hat ein unerwartetes Antwortformat zurückgegeben.")
            body = raw.decode("utf-8")
            return parse_json(body), response.headers
    except HTTPError as error:
        if error.code == 429:
            retry_after = error.headers.get("Retry-After", "60") if error.headers else "60"
            try:
                seconds = int(retry_after)
            except ValueError:
                seconds = 60
            upstream.backoff(seconds)
            raise KeycafeError(503, "Keycafe hat das Anfragelimit erreicht. Bitte später erneut versuchen.") from None
        message = f"Die Anfrage an Keycafe ist fehlgeschlagen (HTTP {error.code})."
        raise KeycafeError(502, message) from None
    except UnicodeDecodeError:
        raise KeycafeError(502, "Keycafe hat ein unerwartetes Antwortformat zurückgegeben.") from None
    except (URLError, TimeoutError, http.client.HTTPException, OSError):
        raise KeycafeError(502, "Keycafe ist derzeit nicht erreichbar.") from None


def keycafe_url(path_or_url: str, params: dict | None = None) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url

    url = urljoin(KEYCAFE_BASE_URL, path_or_url)
    query = urlencode(
        {
            key: value
            for key, value in (params or {}).items()
            if value not in {None, ""}
        }
    )
    return f"{url}?{query}" if query else url


def parse_json(body: str):
    if not body:
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def parse_link_header(header: str | None) -> dict[str, str]:
    if not header:
        return {}

    links = {}
    for url, params in LINK_HEADER_RE.findall(header):
        match = LINK_REL_RE.search(params)
        if match:
            links[match.group(1) or match.group(2)] = url.strip()
    return links


def normalize_key(key: dict) -> dict:
    home_location = key.get("homeLocation") if isinstance(key.get("homeLocation"), dict) else None
    current_location = key.get("currentLocation") if isinstance(key.get("currentLocation"), dict) else None
    current_user = key.get("currentUser") if isinstance(key.get("currentUser"), dict) else None
    at_home = bool(
        home_location
        and current_location
        and home_location.get("id") is not None
        and str(home_location.get("id")) == str(current_location.get("id"))
    )

    if current_user:
        status = "checked-out"
    elif at_home:
        status = "at-home"
    else:
        status = "unknown"

    return {
        "id": key.get("id"),
        "name": key.get("name") or f"Schlüssel {key.get('id') or ''}".strip(),
        "serialNumber": key.get("serialNumber") or "",
        "currentLocation": normalize_location(current_location),
        "currentUser": normalize_user(current_user),
        "removedAt": key.get("removedAt") if status == "checked-out" else None,
        "status": status,
        "statusLabel": status_label(status),
        "detailError": key.get("detailError") or "",
    }


def normalize_location(location: dict | None) -> dict | None:
    if not isinstance(location, dict) or not location:
        return None

    return {
        "name": location.get("name") or "",
    }


def normalize_user(user: dict | None) -> dict | None:
    if not isinstance(user, dict) or not user:
        return None

    name = " ".join(filter(None, [user.get("firstName"), user.get("lastName")]))
    email = user.get("email") or user.get("contactEmail") or ""
    return {
        "name": name or email,
        "email": email,
    }


def summarize_keys(keys: list[dict]) -> dict:
    summary = {
        "total": 0,
        "at-home": 0,
        "checked-out": 0,
        "unknown": 0,
    }

    for key in keys:
        summary["total"] += 1
        summary[key["status"]] = summary.get(key["status"], 0) + 1

    return summary


def status_label(status: str) -> str:
    return {
        "at-home": "Vor Ort",
        "checked-out": "Ausgegeben",
    }.get(status, "Ungeklärt")


def _server_credentials():
    email = os.environ.get("KEYCAFE_EMAIL")
    token = os.environ.get("KEYCAFE_TOKEN")

    if not email or not token:
        return None

    return {"email": email, "token": token}
