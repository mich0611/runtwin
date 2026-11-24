from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
DEFAULT_SCOPE = "activity:read_all,activity:write"
ENV_KEYS = ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN", "STRAVA_ATHLETE_ID")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorize a personal Strava app and update the local .env file.")
    parser.add_argument("--client-id", help="Strava API application client ID")
    parser.add_argument("--client-secret", help="Strava API application client secret")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-browser", action="store_true", help="Print the authorization URL without opening a browser.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client_id = args.client_id or input("Strava Client ID: ").strip()
    client_secret = args.client_secret or input("Strava Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Client ID and Client Secret are required.", file=sys.stderr)
        return 2

    redirect = urlparse(args.redirect_uri)
    if redirect.scheme != "http" or redirect.hostname not in {"localhost", "127.0.0.1"} or not redirect.port:
        print("redirect-uri must be a local HTTP URL with an explicit port.", file=sys.stderr)
        return 2

    state = secrets.token_urlsafe(32)
    authorization_url = f"{AUTHORIZE_URL}?{urlencode({'client_id': client_id, 'redirect_uri': args.redirect_uri, 'response_type': 'code', 'approval_prompt': 'auto', 'scope': args.scope, 'state': state})}"
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            result["state"] = query.get("state", [""])[0]
            result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            result["scope"] = query.get("scope", [""])[0]
            body = "Strava authorization received. You can close this window."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format, *args):
            return

    print("Open this URL and authorize your own Strava account.")
    print("Keep every permission checkbox ticked on the Strava page (read all activities + write).\n")
    print(authorization_url)
    if not args.no_browser:
        webbrowser.open(authorization_url)

    server = HTTPServer((redirect.hostname, redirect.port), CallbackHandler)
    server.timeout = 300
    print(f"\nWaiting up to 5 minutes for Strava to redirect to {args.redirect_uri} ...")
    server.handle_request()
    server.server_close()
    if not result:
        print("Timed out waiting for the Strava redirect. Run the script again.", file=sys.stderr)
        return 1

    if result.get("state") != state:
        print("Authorization failed: invalid or missing OAuth state.", file=sys.stderr)
        return 1
    if result.get("error") or not result.get("code"):
        print(f"Authorization failed: {result.get('error') or 'missing code'}", file=sys.stderr)
        return 1
    missing = missing_scopes(args.scope, result.get("scope", ""))
    if missing:
        print(
            "Authorization is missing required permissions: " + ", ".join(missing)
            + ". Run the script again and keep every checkbox ticked on the Strava page.",
            file=sys.stderr,
        )
        return 1

    payload = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": result["code"],
        "grant_type": "authorization_code",
    }).encode("ascii")
    request = Request(TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            token = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Strava token exchange failed (HTTP {exc.code}): {exc.read().decode('utf-8', errors='replace')[:500]}", file=sys.stderr)
        return 1
    except (URLError, json.JSONDecodeError) as exc:
        print(f"Strava token exchange failed: {exc}", file=sys.stderr)
        return 1

    refresh_token = token.get("refresh_token")
    athlete_id = (token.get("athlete") or {}).get("id")
    if not refresh_token or not athlete_id:
        print("Strava response did not include refresh_token and athlete.id.", file=sys.stderr)
        return 1

    update_env(Path(args.env_file), {
        "STRAVA_CLIENT_ID": str(client_id),
        "STRAVA_CLIENT_SECRET": str(client_secret),
        "STRAVA_REFRESH_TOKEN": str(refresh_token),
        "STRAVA_ATHLETE_ID": str(athlete_id),
    })
    print(f"Updated {args.env_file} with this athlete's Strava OAuth settings.")
    print("Keep .env private. Restart RunTwin services after changing credentials.")
    return 0


def missing_scopes(requested: str, granted: str) -> list[str]:
    """Strava lets the athlete untick scopes; report requested scopes that were not granted."""
    granted_set = {item.strip() for item in granted.split(",") if item.strip()}
    if not granted_set:
        return []  # Some Strava responses omit scope; the token exchange still validates access.
    return [item.strip() for item in requested.split(",") if item.strip() and item.strip() not in granted_set]


def update_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    remaining = dict(values)
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    if remaining:
        if output and output[-1]:
            output.append("")
        output.extend(f"{key}={remaining[key]}" for key in ENV_KEYS if key in remaining)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
