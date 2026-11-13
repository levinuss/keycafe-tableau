# Keycafe Tableau

A Svelte dashboard with Bootstrap 5.3 styling and a Django API proxy for Keycafe.

The German-only app manages local dashboard groups of Keycafe key IDs and is designed for one SmartBox. Keys are shown as **Vor Ort**, **Ausgegeben**, or **Ungeklärt**. The SmartBox name is shown for keys confirmed at home; checked-out keys show their holder. Unexpected location mismatches remain **Ungeklärt**, never falsely marked as available or handed out. Names supplied by the live API are kept as entered in Keycafe.

## Install

```bash
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run In Development

### Demo mode

To develop without Keycafe credentials, add this to the repo-root `.env`:

```bash
KEYCAFE_DEMO_MODE=true
```

Restart Django after changing `.env`. Demo mode returns deterministic German groups and keys through the same `/api/groups/` and `/api/keys/` endpoints used with the live service. All keys share one SmartBox: five keys are at home, three are handed out to named users, and one has unknown status. No request is sent to Keycafe while demo mode is active.

Set `KEYCAFE_DEMO_MODE=false` or remove it to use the real API. If demo mode and real credentials are both configured, demo mode takes precedence.

### Live Keycafe mode

Configure the server-side Keycafe token:

```bash
export KEYCAFE_EMAIL="name@example.com"
export KEYCAFE_TOKEN="your-keycafe-api-token"
export KEYCAFE_AUTH_MODE="token"
export KEYCAFE_USER_AGENT="KeycafeTableau/0.1 (+https://docs.keycafe.com/reference/api-overview)"
```

For an API key created in the Keycafe web UI, set `KEYCAFE_AUTH_MODE="key"`; the value in `KEYCAFE_TOKEN` is then interpreted as the API key. The default is `token`. You can also put those values in a repo-root `.env` file. Django and the token helper load `.env` on startup, so restart Django after changing it.

Start Django:

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Start Svelte/Vite:

```bash
npm run dev
```

Open http://localhost:5173.

The frontend never asks for or sends Keycafe credentials. Django reads the server-side credential from `KEYCAFE_EMAIL` and `KEYCAFE_TOKEN`, selects the Basic-Auth suffix from `KEYCAFE_AUTH_MODE`, and proxies Keycafe requests from the server.

## Create A Keycafe Token

```bash
.venv/bin/python scripts/create_keycafe_token.py --email name@example.com
```

The helper uses Keycafe's documented `POST /v0/authorization` endpoint. It prompts for your Keycafe password, handles the 2FA challenge flow when Keycafe requires it, and prints:

```bash
KEYCAFE_EMAIL='name@example.com'
KEYCAFE_TOKEN='...'
```

Useful options:

```bash
.venv/bin/python scripts/create_keycafe_token.py --email name@example.com --expiry 2026-12-31T23:59:59Z
.venv/bin/python scripts/create_keycafe_token.py --email name@example.com --two-factor
.venv/bin/python scripts/create_keycafe_token.py --email name@example.com --user-agent "KeycafeTableauTokenHelper/0.1"
.venv/bin/python scripts/create_keycafe_token.py --email name@example.com --json
```

If Cloudflare returns `Error 1010: Access denied`, Keycafe's edge layer has rejected the non-browser request signature. The helper and Django proxy both send `KEYCAFE_USER_AGENT`, but Cloudflare may still block Python HTTP clients based on lower-level request fingerprinting. In that case, create the token from Keycafe's web UI or ask Keycafe support to allow documented API calls for your account/network.

## Access Protection

Authentication and access policies are not handled by this app. The app has no login/logout flow, authenticated users, permission groups, or session cookies (a CSRF cookie protects group editing). Keycafe key groups and current key holders are inventory data, not app accounts; all admitted visitors use the same server-side Keycafe credential.

- Protect the entire app origin, including `/api/config/`, `/api/groups/`, `/api/keys/`, and static assets, at the proxy.
- Keep the Django upstream private: bind it to loopback or restrict its container/network port to the proxy. Direct upstream access bypasses authentication.
- Keep the Vite development server local; do not expose it as an alternative public entry point.

## Production With Docker Compose

The multi-stage image builds Svelte, then serves the API and frontend with Gunicorn
and WhiteNoise. Local groups are stored in SQLite in the `tableau-data` Docker volume. No Django migrations or Node runtime are needed. Back up this volume to preserve groups. The container runs non-root with a read-only filesystem and temporary `/tmp`.

Requires Docker Engine and its Compose plugin. Configure your existing `.env`
using `.env.example` as a reference:

- Generate `DJANGO_SECRET_KEY` with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
- Set `DJANGO_CSRF_TRUSTED_ORIGINS` to the public origin, including HTTPS (for example `https://tableau.example.org`), so group editing works behind your TLS proxy.
- Set `DJANGO_ALLOWED_HOSTS` to the public hostname plus `localhost,127.0.0.1` (needed for the health check).
- Set `KEYCAFE_EMAIL`, `KEYCAFE_TOKEN`, and explicitly `KEYCAFE_DEMO_MODE=false` for live data.
- Optionally set `TABLEAU_PORT` (default `8000`) and `TABLEAU_IMAGE` (default `keycafe-tableau:latest`).

Never commit `.env`. It and local databases are excluded from the build context.
Compose passes only named settings and forces `DJANGO_DEBUG=false`.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 tableau
```

The upstream is bound to `127.0.0.1:8000` on the Docker host. Terminate HTTPS and
apply auth at your reverse proxy. A host-based proxy can use
this loopback address. A containerized proxy needs a shared private Docker network
with `tableau` and should use `http://tableau:8000`; do not expose the upstream by
changing the host binding to `0.0.0.0`. Preserve the public `Host` header.

For an image built in CI, set `TABLEAU_IMAGE` to a versioned registry image and run
`docker compose pull && docker compose up -d --no-build`. The `/healthz/` check
verifies the app process only, not Keycafe. Before release, verify
unauthenticated access is blocked for both the page and API, then check asset
loading, real group membership, and key status/holder accuracy.

Local production-server smoke test without Docker:

```bash
npm run build
DJANGO_DEBUG=false .venv/bin/gunicorn --config gunicorn.conf.py keycafe_tableau.wsgi:application
```

API responses contain group IDs/names, key display fields, and summary counts.
Owner profiles, phone numbers, addresses, and redundant metadata are not sent to
the browser. Browser responses remain marked `no-store`. Upstream inventory, key details, and
pickup history are cached server-side for 60 seconds, shared across workers and
browser sessions using SQLite and a file lock. Pickup cache keys include the current
holder; changed custody bypasses the previous holder's cache. The short TTL also
bounds staleness if a return and another pickup happen between refreshes.

The server reserves at most 50 upstream requests in any rolling 60-second window.
When the budget is exhausted it fails fast without contacting Keycafe. HTTP 429
starts a shared cooldown of at least 60 seconds (or a longer numeric Retry-After).
There are no immediate retries. Cache hits remain available during cooldown.
This budget covers this app instance and workers sharing its database; other
applications using the same Keycafe account consume additional quota.

`KEYCAFE_CACHE_SECONDS` (default 60) and `KEYCAFE_REQUESTS_PER_MINUTE` (default 50,
maximum 60) configure these limits. `TABLEAU_UPSTREAM_DB` defaults to
`upstream.sqlite3` beside the groups database, including in the Docker volume.
It contains temporary Keycafe data; protect it like the groups database.

The toolbar offers optional auto-refresh every 2, 5, or 10 minutes, off by default.
It pauses in hidden tabs, during requests, and while editing groups. Manual refresh
also uses the shared cache. No background synchronization runs on the server.

## What It Uses

- Svelte for the frontend.
- Bootstrap 5.3 for layout, controls, table, buttons, and responsive styling.
- Django for `/api/config/`, `/api/groups/`, and `/api/keys/` behind the authentication proxy.
- `POST /v0/authorization` in the helper script to create a Keycafe API token.
- Local `/api/groups/` endpoints to manage dashboard groups.
- `GET /v0/key` to list keys.
- `GET /v0/key/{key_id}` to enrich list results with `homeLocation`, `currentLocation`, and `currentUser`.
- Link-header pagination for group and key lists.

Keycafe's Key object exposes `currentLocation` only when a key is checked in and `currentUser` only when it is checked out. The dashboard derives status from those documented fields.

## Local Key Groups

In live mode, use **Gruppen verwalten** to create, rename, edit, and delete dashboard groups. Load the Keycafe inventory and select keys, or enter numeric key IDs separated by commas or newlines. Membership uses stable key IDs; names and status always come from Keycafe. These groups do not modify Keycafe permissions or Keycafe's own groups. Empty groups are supported. Missing/inaccessible configured keys are reported in the dashboard.

Groups are stored server-side in `data/groups.sqlite3` by default. Override `TABLEAU_GROUPS_DB` with an absolute path if needed. Docker Compose uses `/data/groups.sqlite3` in the persistent `tableau-data` volume. Do not delete that volume when updating the app. Demo groups remain deterministic and cannot be edited.

The current public Keycafe API does not document key-group membership or a group filter for Search Keys. The app fetches the accessible inventory, filters by local membership before fetching details, and never sends an undocumented `group` parameter upstream. `/api/keys/` without a group provides the accessible inventory for the editor; an unknown group returns 404.

All visitors admitted by the authentication proxy can manage local groups. Protect the entire origin and restrict access accordingly. Mutations require Django CSRF validation; the app now uses a CSRF cookie (no login/session cookie). Group writes are transactional. Concurrent edits to the same group use the last saved value.

## Verify

```bash
npm run test:frontend
npm run test:backend
```
