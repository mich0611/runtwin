"""One-time Garmin Connect login that saves reusable tokens for RunTwin.

RunTwin never stores your Garmin password. This script signs in once (including MFA),
writes OAuth tokens to a local folder, and optionally enables Garmin in `.env`. Afterwards
RunTwin only reads those tokens. Re-run this script whenever Garmin asks you to sign in again.

Garmin Connect has no official public API for personal use; this relies on the unofficial
`garminconnect` package and may stop working if Garmin changes its login.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

DEFAULT_TOKEN_DIR = "~/.garminconnect"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sign in to Garmin Connect and save tokens for RunTwin.")
    parser.add_argument("--token-dir", default=os.getenv("RUNTWIN_GARMIN_TOKEN_DIR") or DEFAULT_TOKEN_DIR,
                        help=f"Folder for Garmin tokens (default {DEFAULT_TOKEN_DIR}).")
    parser.add_argument("--email", help="Garmin Connect email (prompted if omitted).")
    parser.add_argument("--is-cn", action="store_true", help="Use Garmin Connect China (garmin.cn).")
    parser.add_argument("--env-file", default=".env", help="Update RUNTWIN_GARMIN_ENABLED/TOKEN_DIR in this file.")
    parser.add_argument("--no-env", action="store_true", help="Do not modify the .env file.")
    return parser.parse_args()


def update_env(env_file: Path, token_dir: str) -> None:
    values = {"RUNTWIN_GARMIN_ENABLED": "1", "RUNTWIN_GARMIN_TOKEN_DIR": token_dir}
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[index] = f"{key}={values[key]}"
            seen.add(key)
    lines.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        from garminconnect import Garmin
    except ImportError:
        print("garminconnect is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 2

    token_path = Path(args.token_dir).expanduser().resolve()
    token_path.mkdir(parents=True, exist_ok=True)
    email = args.email or input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password (not stored): ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 2

    client = Garmin(email, password, is_cn=args.is_cn, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    try:
        client.login(str(token_path))
    except Exception as exc:  # garminconnect raises several auth/connection error types
        print(f"Garmin login failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""

    if not any(token_path.iterdir()):
        print(f"Login succeeded but no tokens were written to {token_path}.", file=sys.stderr)
        return 1

    print(f"Garmin tokens saved to {token_path}")
    if not args.no_env:
        update_env(Path(args.env_file), args.token_dir)
        print(f"Updated {args.env_file}: RUNTWIN_GARMIN_ENABLED=1, RUNTWIN_GARMIN_TOKEN_DIR={args.token_dir}")
    print("Keep this folder private: it grants access to your Garmin account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
