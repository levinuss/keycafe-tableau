import base64
import json
import os
from django.conf import settings
from . import upstream
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request

from .transport import open_authenticated, trusted_destination


KEYCAFE_BASE_URL = os.environ.get("KEYCAFE_BASE_URL", "https://www.keycafe.com")
KEYCAFE_MAX_PAGES = int(os.environ.get("KEYCAFE_MAX_PAGES", "25"))
KEYCAFE_USER_AGENT = os.environ.get(
    "KEYCAFE_USER_AGENT",
    "KeycafeTableau/0.1 (+https://docs.keycafe.com/reference/api-overview)",
)


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


def fetch_groups(auth: KeycafeAuth, organization: str | None = None) -> list[dict]:
    groups = fetch_all_pages("/v0/group", auth, {"organization": organization})
    key_groups = [group for group in groups if group.get("type") in {None, "KEY"}]
    return [{"id": group.get("id"), "name": group.get("name") or ""}
            for group in sorted(key_groups, key=group_sort_key)]


def fetch_inventory(auth, organization=None):
    params = {"organization": organization}

    return upstream.cached(
        f"inventory:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}:{organization}",
        settings.KEYCAFE_CACHE_SECONDS,
        lambda: fetch_all_pages("/v0/key", auth, params),
    )


def fetch_keys(auth: KeycafeAuth, group: str | None = None, organization: str | None = None, key_ids=None):
    shallow_keys = fetch_inventory(auth, organization)
    missing_ids = []
    if key_ids is not None:
        wanted = set(map(str, key_ids))
        shallow_keys = [key for key in shallow_keys if str(key.get("id")) in wanted]
        missing_ids = sorted(wanted - {str(key.get("id")) for key in shallow_keys})
    enriched_keys = [fetch_key_detail_if_needed(auth, key) for key in shallow_keys]
    normalized_keys = [normalize_key(fetch_pickup_time(auth, key)) for key in enriched_keys]

    return {
        "missingKeyIds": missing_ids,
        "keys": normalized_keys,
        "summary": summarize_keys(normalized_keys),
    }


def fetch_pickup_time(auth: KeycafeAuth, key: dict) -> dict:
    if not key.get("currentUser") or not key.get("id"):
        return key
    try:
        # Events describe completed pickups; exchange timestamps describe authorization.
        # Search Events returns newest first, so only the first page is needed.
        events = upstream.cached(
            f"pickup:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}:{key['id']}:{json.dumps(key['currentUser'], sort_keys=True)}",
            settings.KEYCAFE_CACHE_SECONDS,
            lambda: keycafe_json(keycafe_url("/v0/event", {"key": key["id"], "type": "PICKUP"}), auth),
            validate=lambda events: isinstance(events, list) and all(isinstance(event, dict) for event in events),
        )
        if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
            raise KeycafeError(502, "Keycafe hat ungültige Entnahmeereignisse zurückgegeben.")
        return {**key, "removedAt": events[0].get("dateCreated") if events else None}
    except KeycafeError:
        # Missing history must not hide the live inventory or holder.
        return {**key, "removedAt": None}


def fetch_key_detail_if_needed(auth: KeycafeAuth, key: dict) -> dict:
    user = key.get("currentUser") or {}
    location = key.get("currentLocation") or {}
    home = key.get("homeLocation") or {}
    has_holder = any(user.get(field) for field in ("firstName", "lastName", "email", "contactEmail"))
    has_location = location.get("id") is not None and bool(location.get("name")) and home.get("id") is not None
    if not key.get("id") or ("serialNumber" in key and (has_holder or (not user and has_location))):
        return key

    try:
        detail = upstream.cached(
            f"detail:{KEYCAFE_BASE_URL}:{upstream.scope(auth)}:{key['id']}",
            settings.KEYCAFE_CACHE_SECONDS,
            lambda: keycafe_json(f"/v0/key/{key['id']}", auth),
            validate=lambda detail: isinstance(detail, dict) and str(detail.get("id")) == str(key["id"]),
        )
        if not isinstance(detail, dict) or str(detail.get("id")) != str(key["id"]):
            raise KeycafeError(502, "Keycafe hat ungültige Schlüsseldetails zurückgegeben.")
        # Preserve only descriptive fields, never stale location/holder state.
        return {**{field: key.get(field) for field in ("name", "serialNumber")}, **detail}
    except KeycafeError as error:
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
        links = parse_link_header(headers.get("Link"))
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
            body = response.read().decode("utf-8")
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
    except (URLError, TimeoutError):
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
    for part in header.split(","):
        section = part.strip()
        if not section.startswith("<") or ">;" not in section:
            continue
        url, rest = section[1:].split(">;", 1)
        rel_prefix = 'rel="'
        if rel_prefix in rest:
            rel = rest.split(rel_prefix, 1)[1].split('"', 1)[0]
            links[rel] = url
    return links


def normalize_key(key: dict) -> dict:
    home_location = key.get("homeLocation")
    current_location = key.get("currentLocation")
    current_user = key.get("currentUser")
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
    if not location:
        return None

    return {
        "name": location.get("name") or "",
    }


def normalize_user(user: dict | None) -> dict | None:
    if not user:
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


def group_sort_key(group: dict):
    name = group.get("name") or ""
    return (0 if name.lower() == "all keys" else 1, name.lower())


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
