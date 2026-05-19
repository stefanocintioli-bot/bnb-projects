#!/usr/bin/env python3
"""
dca-bnbagent/push_secrets.py — retry the GitHub Secrets push from setup.py.

The original setup.py used `gh secret set NAME --body-file -`, which the
installed `gh` (2.89) rejects. This script pushes the same three secrets
using the stdin form that 2.89 accepts (plain `gh secret set NAME`, value
on stdin), reading the private key from the existing encrypted keystore.

The private key is never printed; it only flows from the keystore decrypt
into subprocess stdin, then gets dropped + garbage collected.
"""

from __future__ import annotations

import gc
import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path

WALLET_ADDRESS = "0x92B3243013d9993c8d1c3d4Ac5E49f9C61405889"
KEYSTORE_PATH = Path.home() / ".bnbagent" / "wallets" / f"{WALLET_ADDRESS}.json"

SECRET_NAMES = {
    "private_key": "BNBAGENT_PRIVATE_KEY",
    "password":    "BNBAGENT_WALLET_PASSWORD",
    "address":     "BNBAGENT_WALLET_ADDRESS",
}


# ────────────────────────────────────────────────────────────────────────────
# Pretty output helpers
# ────────────────────────────────────────────────────────────────────────────

def step(n: int, msg: str) -> None:
    print(f"\n[{n}/7] {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str, fix: str) -> None:
    print(f"\n❌ {msg}")
    print(f"   Fix: {fix}")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────────────
# Step 1 — prerequisites
# ────────────────────────────────────────────────────────────────────────────

def check_prerequisites() -> None:
    step(1, "Checking prerequisites...")

    py = sys.version_info
    if (py.major, py.minor) < (3, 10):
        fail(
            f"Python 3.10+ required, found {py.major}.{py.minor}",
            "Install Python 3.10 or newer (e.g. `brew install python@3.11`)",
        )
    ok(f"Python {py.major}.{py.minor}.{py.micro}")

    if not shutil.which("gh"):
        fail("GitHub CLI (gh) not found on PATH", "brew install gh")

    proc = subprocess.run(["gh", "auth", "status"], capture_output=True)
    if proc.returncode != 0:
        fail("GitHub CLI not authenticated", "gh auth login")
    ok("gh authenticated")

    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
    )
    if proc.returncode != 0:
        fail(
            "Not inside a git repository",
            "cd into the repo (e.g. `cd ~/bnb-projects`) before running this script",
        )
    ok("inside git repo")


# ────────────────────────────────────────────────────────────────────────────
# Step 2 — show target repo and confirm
# ────────────────────────────────────────────────────────────────────────────

def confirm_repo() -> str:
    step(2, "Confirming target repository...")
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        fail(
            f"Cannot resolve current repo via gh: {err}",
            "Run this script from inside a cloned GitHub repo (e.g. `cd ~/bnb-projects`)",
        )

    repo = proc.stdout.strip()
    print(f"  Target repo: {repo}")
    answer = input(f"  Push secrets to {repo}? (y/N): ").strip()
    if answer not in {"y", "Y"}:
        print("\nAborted — no secrets pushed.")
        sys.exit(0)
    return repo


# ────────────────────────────────────────────────────────────────────────────
# Step 3 — locate keystore
# ────────────────────────────────────────────────────────────────────────────

def locate_keystore() -> Path:
    step(3, "Locating encrypted keystore...")
    if not KEYSTORE_PATH.exists():
        fail(
            f"Keystore not found at {KEYSTORE_PATH}",
            "Re-run `python setup.py` to regenerate the wallet and keystore",
        )
    ok(str(KEYSTORE_PATH))
    return KEYSTORE_PATH


# ────────────────────────────────────────────────────────────────────────────
# Step 4 — prompt for password (once)
# ────────────────────────────────────────────────────────────────────────────

def prompt_password() -> str:
    step(4, "Enter the keystore password...")
    print("  (nothing will be echoed)")
    return getpass.getpass("  Password: ")


# ────────────────────────────────────────────────────────────────────────────
# Step 5 — decrypt keystore → 0x-prefixed hex private key
# ────────────────────────────────────────────────────────────────────────────

def decrypt_keystore(keystore_path: Path, password: str) -> str:
    step(5, "Decrypting keystore...")
    try:
        from eth_account import Account
    except ImportError:
        fail(
            "eth_account not installed (transitive dep of bnbagent)",
            f"{sys.executable} -m pip install 'bnbagent>=0.2.1'",
        )

    with keystore_path.open() as fh:
        keystore = json.load(fh)

    try:
        key_bytes = Account.decrypt(keystore, password)
    except ValueError:
        # eth-account raises ValueError("MAC mismatch") on bad password.
        # Deliberately do NOT include the password or any key material in the message.
        print("\n❌ Incorrect password")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Keystore decryption failed: {type(exc).__name__}")
        sys.exit(1)

    key_hex = "0x" + key_bytes.hex()
    # Drop the raw bytes reference now that we have the hex form.
    del key_bytes
    ok("keystore decrypted")
    return key_hex


# ────────────────────────────────────────────────────────────────────────────
# Step 6 — push secrets via stdin (gh 2.89 form)
# ────────────────────────────────────────────────────────────────────────────

def set_secret(name: str, value: str) -> tuple[bool, str]:
    """Push a single secret via `gh secret set NAME` reading stdin.

    Returns (success, stderr). The value never appears in argv.
    """
    proc = subprocess.run(
        ["gh", "secret", "set", name],
        input=value,
        text=True,
        capture_output=True,
    )
    err = (proc.stderr or proc.stdout or "").strip()
    return proc.returncode == 0, err


def push_secrets(address: str, private_key: str, password: str) -> int:
    step(6, "Pushing GitHub Secrets (stdin → gh)...")

    items = [
        (SECRET_NAMES["private_key"], private_key),
        (SECRET_NAMES["password"],    password),
        (SECRET_NAMES["address"],     address),
    ]

    failures = 0
    for name, value in items:
        success, err = set_secret(name, value)
        if success:
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name} — {err}")
            failures += 1
            # Stop at first failure as the task spec requires.
            break

    if failures:
        print(f"\n❌ Aborting — {failures} secret(s) failed.")
        sys.exit(failures)

    return 0


# ────────────────────────────────────────────────────────────────────────────
# Step 7 — verify + next steps
# ────────────────────────────────────────────────────────────────────────────

def verify_secrets() -> None:
    step(7, "Verifying secrets via `gh secret list`...")
    proc = subprocess.run(
        ["gh", "secret", "list"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        print(f"  ! could not run `gh secret list`: {err}")
        return

    matches = [
        line for line in proc.stdout.splitlines()
        if "BNBAGENT_" in line
    ]
    expected = set(SECRET_NAMES.values())
    found_names = {line.split()[0] for line in matches if line.strip()}
    missing = expected - found_names

    if matches:
        print("  Found:")
        for line in matches:
            print(f"    {line}")
    if missing:
        print(f"  ! missing: {', '.join(sorted(missing))}")
    else:
        ok("all three BNBAGENT_* secrets present")


def print_next_steps() -> None:
    bar = "═" * 68
    print(f"\n{bar}")
    print("  Secrets pushed")
    print(bar)
    print(f"  Wallet : {WALLET_ADDRESS}")
    print(f"  Next   : python3.11 register.py")
    print(bar)


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    check_prerequisites()
    confirm_repo()
    keystore_path = locate_keystore()
    password = prompt_password()
    private_key = decrypt_keystore(keystore_path, password)

    try:
        push_secrets(WALLET_ADDRESS, private_key, password)
    finally:
        # Wipe sensitive material regardless of push outcome.
        del private_key, password
        gc.collect()

    verify_secrets()
    print_next_steps()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted by user, no secrets pushed.")
        sys.exit(130)
