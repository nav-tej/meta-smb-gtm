"""Configure Google OAuth credentials in .env and push to Vercel (never prints secrets).

Usage:
    # From a downloaded Google Cloud Console client_secret_*.json file:
    .venv/bin/python scripts/google_oauth_setup.py \\
        --from-json ~/Downloads/client_secret_*.json --push-vercel

    # Or after setting GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env:
    .venv/bin/python scripts/google_oauth_setup.py --push-vercel
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
EXPECTED_REDIRECT_URI = "https://meta-smb-gtm.vercel.app/api/v1/account/oauth/google/callback"


def _upsert_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    prefix = f"{key}="
    updated = False
    out: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")


def _load_from_json(json_path: Path) -> tuple[str, str]:
    raw = json.loads(json_path.read_text())
    block = raw.get("web") or raw.get("installed") or raw
    client_id = str(block.get("client_id") or "").strip()
    client_secret = str(block.get("client_secret") or "").strip()
    redirects = block.get("redirect_uris") or []
    if not client_id or not client_secret:
        sys.exit(f"Missing client_id or client_secret in {json_path.name}")
    if redirects and EXPECTED_REDIRECT_URI not in redirects:
        print(
            f"WARNING: {EXPECTED_REDIRECT_URI} not listed in JSON redirect_uris ({redirects}). "
            "Ensure it is added in Google Cloud Console."
        )
    return client_id, client_secret


def _push_vercel(name: str, value: str, target_env: str) -> None:
    subprocess.run(
        ["vercel", "env", "rm", name, target_env, "--yes"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    proc = subprocess.run(
        ["vercel", "env", "add", name, target_env, "--sensitive"],
        cwd=ROOT,
        input=value,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.exit(f"Failed to push {name} to Vercel {target_env}: {proc.stderr.strip()}")
    print(f"pushed {name} to Vercel ({target_env})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Path to downloaded Google Cloud OAuth client_secret_*.json",
    )
    parser.add_argument(
        "--push-vercel",
        action="store_true",
        help="Push GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to Vercel Production and Preview",
    )
    args = parser.parse_args()

    if args.from_json:
        client_id, client_secret = _load_from_json(args.from_json.expanduser().resolve())
        _upsert_env(ENV_FILE, "GOOGLE_CLIENT_ID", client_id)
        _upsert_env(ENV_FILE, "GOOGLE_CLIENT_SECRET", client_secret)
        print("saved GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env")
    else:
        vals = dotenv_values(ENV_FILE)
        client_id = (vals.get("GOOGLE_CLIENT_ID") or "").strip()
        client_secret = (vals.get("GOOGLE_CLIENT_SECRET") or "").strip()

    if not client_id or not client_secret:
        sys.exit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env or pass --from-json.")
    if not client_id.endswith(".apps.googleusercontent.com"):
        print("WARNING: GOOGLE_CLIENT_ID does not end with .apps.googleusercontent.com")

    if args.push_vercel:
        for env_name in ("production", "preview"):
            _push_vercel("GOOGLE_CLIENT_ID", client_id, env_name)
            _push_vercel("GOOGLE_CLIENT_SECRET", client_secret, env_name)
        print("Vercel environment variables updated. Run a production deploy to activate.")


if __name__ == "__main__":
    main()
