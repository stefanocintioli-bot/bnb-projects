#!/usr/bin/env python3
"""
dca-bnbagent/register.py — register the wallet at WALLET_ADDRESS as a
BNBAgent on the ERC-8004 Identity Registry, exactly once.

Idempotent: if agent_id.txt already exists in this folder, the script
fetches the on-chain record for that agentId and exits without writing.

The private key is never displayed. The data URI is never decoded back
to its plaintext components in any output.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────────

WALLET_ADDRESS    = "0x92B3243013d9993c8d1c3d4Ac5E49f9C61405889"
IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
NETWORK           = "bsc-testnet"
AGENT_ID_FILE     = Path(__file__).resolve().parent / "agent_id.txt"

AGENT_NAME        = "stefano-dca-agent"
AGENT_DESCRIPTION = (
    "Monthly DCA agent on BSC testnet — built by @s_cintioli_ "
    "as a BAP-692 reference build"
)
AGENT_ENDPOINT_NAME    = "Telegram"
AGENT_ENDPOINT_URL     = "https://t.me/bnbchainDCA"
AGENT_ENDPOINT_VERSION = "1.0"

TOTAL_STEPS = 8


# ────────────────────────────────────────────────────────────────────────────
# Pretty output helpers
# ────────────────────────────────────────────────────────────────────────────

def step(n: int, msg: str) -> None:
    print(f"\n[{n}/{TOTAL_STEPS}] {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def warn(msg: str) -> None:
    print(f"  ! {msg}")


def fail(msg: str, fix: str = "") -> None:
    print(f"\n❌ {msg}")
    if fix:
        print(f"   Fix: {fix}")
    sys.exit(1)


def bscscan_tx_url(tx_hash: str) -> str:
    if not tx_hash.startswith("0x"):
        tx_hash = "0x" + tx_hash
    return f"https://testnet.bscscan.com/tx/{tx_hash}"


def bscscan_nft_url(agent_id: int) -> str:
    return f"https://testnet.bscscan.com/token/{IDENTITY_REGISTRY}?a={agent_id}"


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

    try:
        import bnbagent
    except ImportError:
        fail(
            "bnbagent SDK not installed",
            f"{sys.executable} -m pip install 'bnbagent>=0.2.1'",
        )
    ok(f"bnbagent importable (version {getattr(bnbagent, '__version__', '?')})")


# ────────────────────────────────────────────────────────────────────────────
# Wallet + SDK loaders (shared by step 2's idempotency check and step 3/4)
# ────────────────────────────────────────────────────────────────────────────

def _load_wallet():
    """Prompt for password, decrypt keystore, return EVMWalletProvider.

    Never prints the password or any wallet internals.
    """
    print("  (nothing will be echoed)")
    password = getpass.getpass("  Keystore password: ")

    from bnbagent import EVMWalletProvider

    try:
        wallet = EVMWalletProvider(password=password, address=WALLET_ADDRESS)
    except FileNotFoundError:
        fail(
            f"Keystore not found at ~/.bnbagent/wallets/{WALLET_ADDRESS}.json",
            "Re-run `python setup.py` to regenerate the wallet and keystore",
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if any(tok in msg for tok in ("mac", "decryption", "incorrect", "wrong password")):
            print("\n❌ Incorrect password")
            sys.exit(1)
        print(f"\n❌ Wallet load failed: {type(exc).__name__}")
        sys.exit(1)
    finally:
        # Drop the password reference as soon as the SDK has consumed it.
        try:
            del password
        except UnboundLocalError:
            pass

    ok("keystore decrypted")
    return wallet


def _init_sdk(wallet):
    """Construct the ERC8004Agent client and verify the loaded wallet
    address matches the one we expect."""
    from bnbagent import ERC8004Agent

    sdk = ERC8004Agent(
        network=NETWORK,
        wallet_provider=wallet,
        debug=True,
    )

    if sdk.wallet_address.lower() != WALLET_ADDRESS.lower():
        fail(
            f"Loaded wallet {sdk.wallet_address} does not match expected {WALLET_ADDRESS}",
            "Check ~/.bnbagent/wallets/ for the correct keystore file",
        )
    ok(f"SDK initialised, wallet = {sdk.wallet_address}")
    return sdk


# ────────────────────────────────────────────────────────────────────────────
# Step 2 — prior-registration check (idempotency)
# ────────────────────────────────────────────────────────────────────────────

def check_prior_registration() -> None:
    step(2, "Checking for prior registration...")

    if not AGENT_ID_FILE.exists():
        ok(f"no {AGENT_ID_FILE.name} found — will proceed to register")
        return

    try:
        existing = int(AGENT_ID_FILE.read_text().strip())
    except (ValueError, OSError) as exc:
        fail(
            f"{AGENT_ID_FILE.name} exists but is unreadable: {type(exc).__name__}",
            f"Delete {AGENT_ID_FILE} and re-run, or fix the file by hand",
        )

    print(f"  Existing agentId on file: {existing}")
    print("  Loading wallet to fetch the on-chain record...")
    wallet = _load_wallet()
    sdk = _init_sdk(wallet)

    try:
        info = sdk.get_agent_info(agent_id=existing)
    except Exception as exc:  # noqa: BLE001
        warn(f"could not fetch on-chain record: {type(exc).__name__}")
        print(f"  Local agentId       : {existing}")
        print(f"  Agent NFT on BscScan: {bscscan_nft_url(existing)}")
        print("\nAlready registered locally. Nothing to do.")
        sys.exit(0)

    print("\n  Already registered. On-chain record:")
    print(f"    {info}")
    print(f"\n  Agent NFT on BscScan: {bscscan_nft_url(existing)}")
    print("\nNothing to do.")
    sys.exit(0)


# ────────────────────────────────────────────────────────────────────────────
# Step 3 — load wallet from keystore
# ────────────────────────────────────────────────────────────────────────────

def step3_load_wallet():
    step(3, "Loading wallet from encrypted keystore...")
    return _load_wallet()


# ────────────────────────────────────────────────────────────────────────────
# Step 4 — initialise SDK
# ────────────────────────────────────────────────────────────────────────────

def step4_init_sdk(wallet):
    step(4, "Initialising ERC-8004 SDK client...")
    return _init_sdk(wallet)


# ────────────────────────────────────────────────────────────────────────────
# Step 5 — build agent registration URI
# ────────────────────────────────────────────────────────────────────────────

def step5_build_uri(sdk) -> str:
    step(5, "Building agent registration URI...")
    from bnbagent import AgentEndpoint

    endpoints = [
        AgentEndpoint(
            name=AGENT_ENDPOINT_NAME,
            endpoint=AGENT_ENDPOINT_URL,
            version=AGENT_ENDPOINT_VERSION,
        )
    ]

    agent_uri = sdk.generate_agent_uri(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        endpoints=endpoints,
    )

    print(f"  URI length : {len(agent_uri)} chars")
    print(f"  URI head   : {agent_uri[:100]}")
    return agent_uri


# ────────────────────────────────────────────────────────────────────────────
# Step 6 — register on-chain
# ────────────────────────────────────────────────────────────────────────────

def step6_register(sdk, agent_uri: str) -> tuple[int, str]:
    step(6, "Submitting register transaction on BSC Testnet...")
    print("  (gas-sponsored by MegaFuel paymaster — should not consume tBNB)")

    try:
        result = sdk.register_agent(agent_uri=agent_uri)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if len(msg) > 240:
            msg = msg[:240] + "..."
        fail(f"register_agent failed: {type(exc).__name__}: {msg}")

    agent_id = int(result["agentId"])
    tx_hash = result["transactionHash"]

    print(f"  Agent ID            : {agent_id}")
    print(f"  TX hash             : {tx_hash}")
    print(f"  TX on BscScan       : {bscscan_tx_url(tx_hash)}")
    print(f"  Agent NFT on BscScan: {bscscan_nft_url(agent_id)}")
    return agent_id, tx_hash


# ────────────────────────────────────────────────────────────────────────────
# Step 7 — persist agentId to disk (committed to repo)
# ────────────────────────────────────────────────────────────────────────────

def step7_persist(agent_id: int) -> None:
    step(7, f"Writing agentId to {AGENT_ID_FILE.name}...")
    AGENT_ID_FILE.write_text(f"{agent_id}\n")
    ok(f"wrote {AGENT_ID_FILE}")


# ────────────────────────────────────────────────────────────────────────────
# Step 8 — verify round-trip (read-after-write)
# ────────────────────────────────────────────────────────────────────────────

def step8_verify(sdk, agent_id: int) -> None:
    step(8, "Verifying registration round-trip via get_agent_info()...")
    try:
        info = sdk.get_agent_info(agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001
        warn(
            f"on-chain read failed: {type(exc).__name__} "
            "(propagation delay is common; the tx already succeeded)"
        )
        return
    print("  On-chain record:")
    print(f"    {info}")


# ────────────────────────────────────────────────────────────────────────────
# Final summary
# ────────────────────────────────────────────────────────────────────────────

def print_next_steps(agent_id: int, tx_hash: str) -> None:
    bar = "═" * 70
    print(f"\n{bar}")
    print("  Registration complete")
    print(bar)
    print(f"  Agent ID            : {agent_id}")
    print(f"  TX on BscScan       : {bscscan_tx_url(tx_hash)}")
    print(f"  Agent NFT on BscScan: {bscscan_nft_url(agent_id)}")
    print(f"  Persisted to        : {AGENT_ID_FILE}")
    print()
    print("  Next:")
    print("    Delete BNBAGENT_PRIVATE_KEY from GitHub Secrets — it's no")
    print("    longer needed since the agent is registered and the keystore")
    print("    on this machine is the only access path going forward.")
    print()
    print("      gh secret delete BNBAGENT_PRIVATE_KEY")
    print(bar)


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    check_prerequisites()
    check_prior_registration()  # may sys.exit(0) if already registered
    wallet = step3_load_wallet()
    sdk = step4_init_sdk(wallet)
    agent_uri = step5_build_uri(sdk)
    agent_id, tx_hash = step6_register(sdk, agent_uri)
    step7_persist(agent_id)
    step8_verify(sdk, agent_id)
    print_next_steps(agent_id, tx_hash)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted by user before registration completed; no changes made.")
        sys.exit(130)
