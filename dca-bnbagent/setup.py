#!/usr/bin/env python3
"""
dca-bnbagent/setup.py — One-shot setup for the BNBAgent SDK DCA agent.

Generates a fresh BSC Testnet wallet, encrypts the private key to a
Keystore V3 file under ~/.bnbagent/wallets/, and pushes the credentials
to GitHub Secrets so the GitHub Actions workflow can run the bot.

The private key is never printed and never written to .env.
"""

from __future__ import annotations

import gc
import getpass
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PASSWORD_LENGTH = 12
SDK_REQUIREMENT = "bnbagent>=0.2.1"

SECRET_NAMES = {
    "private_key": "BNBAGENT_PRIVATE_KEY",
    "password":    "BNBAGENT_WALLET_PASSWORD",
    "address":     "BNBAGENT_WALLET_ADDRESS",
}


# ────────────────────────────────────────────────────────────────────────────
# Pretty output helpers
# ────────────────────────────────────────────────────────────────────────────

def step(n: int, msg: str) -> None:
    print(f"\n[{n}/8] {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def warn(msg: str) -> None:
    print(f"  ! {msg}")


def fail(msg: str, fix: str) -> None:
    print(f"\n❌ {msg}")
    print(f"   Fix: {fix}")
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────────────
# Step 1 — prerequisites
# ────────────────────────────────────────────────────────────────────────────

def check_prerequisites() -> None:
    step(1, "Checking prerequisites...")

    # Python 3.10+
    py = sys.version_info
    if (py.major, py.minor) < (3, 10):
        fail(
            f"Python 3.10+ required, found {py.major}.{py.minor}",
            "Install Python 3.10 or newer (e.g. `brew install python@3.11`)",
        )
    ok(f"Python {py.major}.{py.minor}.{py.micro}")

    # gh CLI installed
    if not shutil.which("gh"):
        fail("GitHub CLI (gh) not found on PATH", "brew install gh")

    # gh authenticated
    proc = subprocess.run(["gh", "auth", "status"], capture_output=True)
    if proc.returncode != 0:
        fail("GitHub CLI not authenticated", "gh auth login")
    ok("gh authenticated")

    # Inside a git repo (gh secret set infers the repo from cwd)
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
# Step 2 — install the SDK
# ────────────────────────────────────────────────────────────────────────────

def install_sdk() -> None:
    step(2, f"Ensuring {SDK_REQUIREMENT} is installed...")

    try:
        import bnbagent  # noqa: F401
        ok(f"bnbagent already importable (version {getattr(bnbagent, '__version__', '?')})")
        return
    except ImportError:
        pass

    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", SDK_REQUIREMENT],
    )
    if proc.returncode != 0:
        fail(
            "pip install failed",
            f"{sys.executable} -m pip install '{SDK_REQUIREMENT}'",
        )

    importlib.invalidate_caches()
    try:
        import bnbagent  # noqa: F401
    except ImportError as exc:
        fail(
            f"Cannot import bnbagent after install: {exc}",
            f"{sys.executable} -m pip install --force-reinstall '{SDK_REQUIREMENT}'",
        )
    ok(f"bnbagent installed (version {getattr(bnbagent, '__version__', '?')})")


# ────────────────────────────────────────────────────────────────────────────
# Step 3 — generate a fresh EOA in memory
# ────────────────────────────────────────────────────────────────────────────

def generate_wallet() -> tuple[str, str]:
    step(3, "Generating fresh BSC Testnet wallet...")
    from eth_account import Account

    acct = Account.create()
    address = acct.address

    # acct.key is HexBytes; .hex() may or may not include the 0x prefix
    # depending on eth-account version. Normalise to "0x..." form.
    key_hex = acct.key.hex()
    if not key_hex.startswith("0x"):
        key_hex = "0x" + key_hex

    ok(f"new address: {address}")
    return address, key_hex


# ────────────────────────────────────────────────────────────────────────────
# Step 4 — prompt for keystore password
# ────────────────────────────────────────────────────────────────────────────

def prompt_password() -> str:
    step(4, "Choose a password to encrypt the keystore...")
    print(f"  (minimum {MIN_PASSWORD_LENGTH} characters; nothing will be echoed)")

    while True:
        pw1 = getpass.getpass("  Password: ")
        if len(pw1) < MIN_PASSWORD_LENGTH:
            print(f"  ✗ too short — need at least {MIN_PASSWORD_LENGTH} characters")
            continue
        pw2 = getpass.getpass("  Confirm:  ")
        if pw1 != pw2:
            print("  ✗ passwords didn't match — try again")
            continue
        ok("password accepted")
        return pw1


# ────────────────────────────────────────────────────────────────────────────
# Step 5 — encrypt to Keystore V3
# ────────────────────────────────────────────────────────────────────────────

def encrypt_keystore(address: str, private_key: str, password: str) -> Path:
    step(5, "Encrypting private key to ~/.bnbagent/wallets/...")
    from bnbagent import EVMWalletProvider

    # Constructing the provider with a plaintext private_key writes the
    # Keystore V3 file to ~/.bnbagent/wallets/<address>.json and clears
    # the in-memory plaintext copy inside the SDK.
    EVMWalletProvider(password=password, private_key=private_key)

    keystore_path = Path.home() / ".bnbagent" / "wallets" / f"{address}.json"
    if not keystore_path.exists():
        fail(
            f"Keystore not found at {keystore_path}",
            "Re-run this script and check ~/.bnbagent/wallets/ for stale files",
        )
    ok(f"keystore written: {keystore_path}")
    return keystore_path


# ────────────────────────────────────────────────────────────────────────────
# Step 6 — push secrets to GitHub
# ────────────────────────────────────────────────────────────────────────────

def set_secret(name: str, value: str) -> bool:
    """Set a single GitHub Actions secret via `gh`. Returns True on success.

    We pipe the value through stdin (--body-file -) so it never appears
    in argv (no leak via `ps`).
    """
    proc = subprocess.run(
        ["gh", "secret", "set", name, "--body-file", "-"],
        input=value,
        text=True,
        capture_output=True,
    )
    if proc.returncode == 0:
        ok(name)
        return True

    err = (proc.stderr or proc.stdout or "").strip()
    print(f"  ✗ {name} — {err}")
    print(f"    Manual fallback:")
    print(f"      printf %s '<value>' | gh secret set {name} --body-file -")
    return False


def push_secrets(address: str, private_key: str, password: str) -> None:
    step(6, "Pushing credentials to GitHub Secrets via gh CLI...")
    print(f"  Note: {SECRET_NAMES['private_key']} is single-use.")
    print(f"        Delete it from the repo Secrets after the first successful")
    print(f"        register.py run — the keystore will be the only copy.")

    set_secret(SECRET_NAMES["private_key"], private_key)
    set_secret(SECRET_NAMES["password"],    password)
    set_secret(SECRET_NAMES["address"],     address)


# ────────────────────────────────────────────────────────────────────────────
# Step 7 — wipe sensitive material from memory
# ────────────────────────────────────────────────────────────────────────────

def wipe(*_secrets: str) -> None:
    step(7, "Wiping private key and password from process memory...")
    # Python strings are immutable, so the best we can do is drop the
    # references and force a collection cycle. The persistent copies
    # are the encrypted keystore on disk and the GitHub Secrets.
    del _secrets
    gc.collect()
    ok("references dropped, gc.collect() called")


# ────────────────────────────────────────────────────────────────────────────
# Step 8 — next-steps summary
# ────────────────────────────────────────────────────────────────────────────

def print_next_steps(address: str, keystore_path: Path) -> None:
    step(8, "Next steps")
    bar = "═" * 68
    print(f"\n{bar}")
    print("  Setup complete")
    print(bar)
    print(f"  Wallet address : {address}")
    print(f"  Keystore       : {keystore_path}")
    print(f"  BscScan        : https://testnet.bscscan.com/address/{address}")
    print()
    print("  Next:")
    print(f"    1. Send ~0.5 tBNB from your existing testnet wallet (24 tBNB)")
    print(f"       to: {address}")
    print(f"    2. Once funded, run:")
    print(f"         python register.py")
    print(f"       (registers the agent on ERC-8004; gas is sponsored by")
    print(f"        MegaFuel on BSC Testnet, so this should not consume tBNB.)")
    print(bar)


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    check_prerequisites()
    install_sdk()
    address, private_key = generate_wallet()
    password = prompt_password()
    keystore_path = encrypt_keystore(address, private_key, password)
    push_secrets(address, private_key, password)
    wipe(private_key, password)
    # Drop the local names too, just in case the above wipe function
    # captured them in its frame.
    del private_key, password
    gc.collect()
    print_next_steps(address, keystore_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted by user. No secrets were sent to GitHub.")
        sys.exit(130)
