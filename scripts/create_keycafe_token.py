#!/usr/bin/env python3
"""Create a Keycafe API token via the documented authorization endpoint."""

import argparse
import base64
import getpass
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keycafe_api.transport import open_authenticated, trusted_destination
from keycafe_tableau.env import load_env_file


DEFAULT_USER_AGENT = (
    "KeycafeTableauTokenHelper/0.1 "
    "(+https://docs.keycafe.com/reference/create-authorization)"
)


def main() -> int:
    load_env_file(Path(__file__).resolve().parent.parent / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=os.environ.get("KEYCAFE_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("KEYCAFE_PASSWORD"))
    parser.add_argument("--expiry", help="Optional ISO 8601 expiry without milliseconds.")
    parser.add_argument("--code", help="Two-factor authentication code.")
    parser.add_argument(
        "--two-factor",
        action="store_true",
        help="Always request a 2FA challenge before creating the token.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KEYCAFE_BASE_URL", "https://www.keycafe.com"),
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("KEYCAFE_USER_AGENT", DEFAULT_USER_AGENT),
        help="HTTP User-Agent sent to Keycafe. Defaults to KEYCAFE_USER_AGENT.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    args = parser.parse_args()

    if not trusted_destination(args.base_url, args.base_url):
        parser.error("The Keycafe base URL must use HTTPS with a valid hostname and no embedded credentials.")

    email = args.email or input("Keycafe email: ").strip()
    password = args.password or getpass.getpass("Keycafe password: ")
    body = build_body(args)

    try:
        response = create_authorization(
            args.base_url, email, password, body, args.user_agent
        )
    except HTTPError as error:
        error_body = parse_error(error)
        if is_two_factor_challenge(error_body) and not args.code:
            print("Keycafe sent a two-factor code. Enter it to finish token creation.")
            body["code"] = input("2FA code: ").strip()
            response = create_authorization(
                args.base_url, email, password, body, args.user_agent
            )
        else:
            if is_cloudflare_browser_signature_ban(error_body):
                print(
                    "Keycafe/Cloudflare rejected this non-browser request signature. "
                    "Try setting KEYCAFE_USER_AGENT, generate the token in Keycafe's "
                    "web UI, or ask Keycafe support to allow documented API traffic.",
                    file=sys.stderr,
                )
            print(json.dumps(error_body, indent=2), file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(response, indent=2))
    else:
        token = response.get("token")
        if not token:
            print(json.dumps(response, indent=2))
            return 1
        print("KEYCAFE_EMAIL=" + shell_quote(email))
        print("KEYCAFE_TOKEN=" + shell_quote(token))

    return 0


def build_body(args) -> dict:
    body = {}
    if args.expiry:
        body["expiry"] = args.expiry
    if args.code:
        body["code"] = args.code
    if args.two_factor:
        body["twoFactor"] = True
    return body


def create_authorization(
    base_url: str, email: str, password: str, body: dict, user_agent: str
) -> dict:
    url = urljoin(base_url.rstrip("/") + "/", "v0/authorization")
    if not trusted_destination(url, base_url):
        raise ValueError("The token endpoint must use HTTPS on the configured Keycafe origin.")
    encoded = base64.b64encode(f"{email}:{password}".encode("utf-8")).decode("ascii")
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
        method="POST",
    )

    with open_authenticated(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_error(error: HTTPError):
    raw = error.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": error.code, "error": raw}


def is_two_factor_challenge(error_body) -> bool:
    error = error_body.get("error") if isinstance(error_body, dict) else None
    return isinstance(error, dict) and error.get("errorId") == "authorization.twoFactor"


def is_cloudflare_browser_signature_ban(error_body) -> bool:
    return (
        isinstance(error_body, dict)
        and error_body.get("cloudflare_error") is True
        and error_body.get("error_code") == 1010
    )


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
