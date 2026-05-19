"""
dca-bnbagent/dca_runner.py — one monthly DCA cycle.

Invoked by GitHub Actions cron once per month. Reads the agent's prior
receipts from on-chain ERC-8004 metadata, runs three real guardrails,
asks Groq whether to buy, optionally executes a PancakeSwap V2 swap,
writes a JSON receipt back on-chain as metadata, and sends a Telegram
alert. Designed to be mainnet-shaped: NETWORK env var flips the entire
address book through config.py — no hardcoded chain-specific values
live in this file.

Exit codes:
  0  cycle completed (executed, skipped, or dry-run)
  1  fatal error before/after Telegram alert
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from groq import Groq
from web3 import Web3

from bnbagent import ERC8004Agent, EVMWalletProvider
from config import get_config


# ─────────────────────────────────────────────────────────────
# 1.  ENVIRONMENT & LOGGING
# ─────────────────────────────────────────────────────────────
load_dotenv()

NETWORK            = os.getenv("NETWORK", "bsc-testnet")
WALLET_PASSWORD    = os.getenv("WALLET_PASSWORD", "")
WALLET_ADDRESS     = os.getenv("BNBAGENT_WALLET_ADDRESS", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
RPC_URL            = os.getenv("RPC_URL", "")

DCA_AMOUNT_BNB        = float(os.getenv("DCA_AMOUNT_BNB", "0.01"))
GAS_THRESHOLD_GWEI    = int(os.getenv("GAS_THRESHOLD_GWEI", "20"))
MIN_LIQUIDITY_BNB     = float(os.getenv("MIN_LIQUIDITY_BNB", "1.0"))
PRICE_CHANGE_SKIP_PCT = float(os.getenv("PRICE_CHANGE_SKIP_THRESHOLD_PCT", "10.0"))
HISTORY_CYCLES        = int(os.getenv("HISTORY_CYCLES", "3"))
DRY_RUN               = os.getenv("DRY_RUN", "false").lower() == "true"

CFG = get_config(NETWORK)
SCHEMA_VERSION = "stefano-dca-agent/v1"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def _require(name: str, value: str) -> None:
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")


def validate_env() -> None:
    """Fail fast if any required env var is unset. RPC_URL stays optional."""
    _require("WALLET_PASSWORD",         WALLET_PASSWORD)
    _require("BNBAGENT_WALLET_ADDRESS", WALLET_ADDRESS)
    _require("GROQ_API_KEY",            GROQ_API_KEY)
    _require("TELEGRAM_BOT_TOKEN",      TELEGRAM_BOT_TOKEN)
    _require("TELEGRAM_CHAT_ID",        TELEGRAM_CHAT_ID)


# ─────────────────────────────────────────────────────────────
# 2.  AGENT ID  (must exist from a prior register.py run)
# ─────────────────────────────────────────────────────────────
AGENT_ID_FILE = Path(__file__).resolve().parent / "agent_id.txt"


def load_agent_id() -> int:
    if not AGENT_ID_FILE.exists():
        raise RuntimeError(
            f"agent_id.txt not found at {AGENT_ID_FILE} — run register.py first."
        )
    return int(AGENT_ID_FILE.read_text().strip())


# ─────────────────────────────────────────────────────────────
# 3.  MINIMAL PANCAKESWAP V2 ABIs
# ─────────────────────────────────────────────────────────────
ROUTER_ABI = json.loads("""[
  {"inputs":[{"name":"amountOutMin","type":"uint256"},
             {"name":"path","type":"address[]"},
             {"name":"to","type":"address"},
             {"name":"deadline","type":"uint256"}],
   "name":"swapExactETHForTokens",
   "outputs":[{"name":"amounts","type":"uint256[]"}],
   "stateMutability":"payable","type":"function"},
  {"inputs":[{"name":"amountIn","type":"uint256"},
             {"name":"path","type":"address[]"}],
   "name":"getAmountsOut",
   "outputs":[{"name":"amounts","type":"uint256[]"}],
   "stateMutability":"view","type":"function"}
]""")

FACTORY_ABI = json.loads("""[
  {"inputs":[{"name":"tokenA","type":"address"},
             {"name":"tokenB","type":"address"}],
   "name":"getPair",
   "outputs":[{"name":"pair","type":"address"}],
   "stateMutability":"view","type":"function"}
]""")

PAIR_ABI = json.loads("""[
  {"inputs":[],"name":"getReserves",
   "outputs":[{"name":"reserve0","type":"uint112"},
              {"name":"reserve1","type":"uint112"},
              {"name":"blockTimestampLast","type":"uint32"}],
   "stateMutability":"view","type":"function"},
  {"inputs":[],"name":"token0",
   "outputs":[{"name":"","type":"address"}],
   "stateMutability":"view","type":"function"}
]""")


# ─────────────────────────────────────────────────────────────
# 4.  CLIENT BOOTSTRAP  (SDK + Web3 sharing one wallet)
# ─────────────────────────────────────────────────────────────

def init_clients():
    wallet = EVMWalletProvider(password=WALLET_PASSWORD, address=WALLET_ADDRESS)
    sdk    = ERC8004Agent(network=NETWORK, wallet_provider=wallet)

    if sdk.wallet_address.lower() != WALLET_ADDRESS.lower():
        raise RuntimeError(
            f"SDK wallet {sdk.wallet_address} != BNBAGENT_WALLET_ADDRESS {WALLET_ADDRESS}"
        )

    if RPC_URL:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
    else:
        from bnbagent.config import resolve_network
        nc = resolve_network(NETWORK)
        w3 = Web3(Web3.HTTPProvider(nc.rpc_url))

    if not w3.is_connected():
        raise RuntimeError(f"Web3 not connected (RPC_URL={RPC_URL or 'SDK default'})")

    if w3.eth.chain_id != CFG["chain_id"]:
        raise RuntimeError(
            f"Chain id mismatch: connected to {w3.eth.chain_id}, config says {CFG['chain_id']}"
        )

    log.info("Wallet:    %s", sdk.wallet_address)
    log.info("Network:   %s (chainId %s)", NETWORK, CFG["chain_id"])
    return sdk, w3, wallet


# ─────────────────────────────────────────────────────────────
# 5.  HISTORY  (read previous cycles from ERC-8004 metadata)
# ─────────────────────────────────────────────────────────────

def cycle_key(dt: datetime) -> str:
    return f"run-{dt.strftime('%Y-%m')}"


def previous_cycle_keys(now: datetime, n: int) -> list[str]:
    """Last `n` cycle keys, oldest first, NOT including the current cycle."""
    out: list[str] = []
    year, month = now.year, now.month
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        out.append(f"run-{year:04d}-{month:02d}")
    out.reverse()
    return out


def fetch_history(sdk: ERC8004Agent, agent_id: int, now: datetime) -> list[dict]:
    keys = previous_cycle_keys(now, HISTORY_CYCLES)
    log.info("History lookup keys: %s", keys)
    history: list[dict] = []
    for key in keys:
        try:
            raw = sdk.get_metadata(agent_id=agent_id, key=key)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_metadata(%s) failed: %s", key, type(exc).__name__)
            continue
        if not raw:
            continue
        try:
            history.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            log.warning("history key %s undecodable: %s", key, type(exc).__name__)
    log.info("Loaded %d historical receipts", len(history))
    return history


# ─────────────────────────────────────────────────────────────
# 6.  GUARDRAILS
# ─────────────────────────────────────────────────────────────

def get_router(w3: Web3):
    return w3.eth.contract(
        address=Web3.to_checksum_address(CFG["pancake_router"]),
        abi=ROUTER_ABI,
    )


def get_factory(w3: Web3):
    return w3.eth.contract(
        address=Web3.to_checksum_address(CFG["pancake_factory"]),
        abi=FACTORY_ABI,
    )


def current_price_per_bnb(w3: Web3, target_token: str) -> int:
    """Tokens received for exactly 1 BNB right now (raw integer)."""
    one_bnb = Web3.to_wei(1, "ether")
    path = [
        Web3.to_checksum_address(CFG["wbnb"]),
        Web3.to_checksum_address(target_token),
    ]
    amounts = get_router(w3).functions.getAmountsOut(one_bnb, path).call()
    return int(amounts[1])


def check_gas(w3: Web3) -> dict:
    gas_gwei = w3.eth.gas_price / 1e9
    ok = gas_gwei <= GAS_THRESHOLD_GWEI
    return {
        "ok": ok,
        "value_gwei": round(gas_gwei, 4),
        "message": (
            f"Gas OK ({gas_gwei:.2f} Gwei <= {GAS_THRESHOLD_GWEI})"
            if ok else
            f"Gas too high ({gas_gwei:.2f} Gwei > {GAS_THRESHOLD_GWEI})"
        ),
    }


def check_liquidity(w3: Web3, target_token: str) -> dict:
    try:
        wbnb   = Web3.to_checksum_address(CFG["wbnb"])
        target = Web3.to_checksum_address(target_token)
        pair_addr = get_factory(w3).functions.getPair(wbnb, target).call()
        if int(pair_addr, 16) == 0:
            return {"ok": False, "reserve_bnb": 0.0, "message": "Pool does not exist"}
        pair = w3.eth.contract(address=pair_addr, abi=PAIR_ABI)
        reserves = pair.functions.getReserves().call()
        token0   = pair.functions.token0().call()
        bnb_wei  = reserves[0] if token0.lower() == wbnb.lower() else reserves[1]
        reserve_bnb = float(Web3.from_wei(bnb_wei, "ether"))
        ok = reserve_bnb >= MIN_LIQUIDITY_BNB
        return {
            "ok": ok,
            "reserve_bnb": round(reserve_bnb, 4),
            "message": (
                f"Liquidity OK ({reserve_bnb:.4f} BNB in pool)"
                if ok else
                f"Liquidity too low ({reserve_bnb:.4f} BNB < {MIN_LIQUIDITY_BNB})"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "reserve_bnb": 0.0,
            "message": f"Liquidity check error: {type(exc).__name__}",
        }


def check_price_trend(current: int, history: list[dict]) -> dict:
    if not history:
        return {"ok": True, "change_pct": None,
                "message": "no history yet — first cycle"}
    last = history[-1]
    try:
        prev = int(last["market"]["current_price_per_bnb"])
    except (KeyError, TypeError, ValueError):
        return {"ok": True, "change_pct": None,
                "message": "previous cycle missing price field — passing"}
    if prev == 0:
        return {"ok": True, "change_pct": None,
                "message": "previous price was zero — passing"}
    # tokens-per-BNB up → BNB more expensive → BNB rallied
    pct = ((current - prev) / prev) * 100.0
    if pct > PRICE_CHANGE_SKIP_PCT:
        return {"ok": False, "change_pct": round(pct, 2),
                "message": f"BNB +{pct:.2f}% vs last cycle (> {PRICE_CHANGE_SKIP_PCT}%) — skip the top"}
    return {"ok": True, "change_pct": round(pct, 2),
            "message": f"BNB {pct:+.2f}% vs last cycle — within tolerance"}


# ─────────────────────────────────────────────────────────────
# 7.  GROQ REASONING  (with manual-guardrail fallback)
# ─────────────────────────────────────────────────────────────

def _summarise_history(history: list[dict]) -> str:
    if not history:
        return "  (no prior cycles)"
    lines = []
    for h in history:
        cycle  = h.get("cycle", "?")
        dec    = h.get("decision", "?")
        m      = h.get("market", {}) or {}
        price  = m.get("current_price_per_bnb", "?")
        change = m.get("change_pct_vs_last_cycle", "n/a")
        lines.append(f"  - {cycle}: decision={dec} price={price} change={change}")
    return "\n".join(lines)


def groq_decision(
    gas: dict, liq: dict, trend: dict,
    current_price: int, history: list[dict],
) -> dict:
    if not GROQ_API_KEY:
        return _fallback(gas, liq, trend, "GROQ_API_KEY missing")

    prompt = f"""You are a DCA risk-management AI for an autonomous BNB Chain agent.

Current cycle readings:
- Gas:       {gas['value_gwei']} Gwei (threshold {GAS_THRESHOLD_GWEI}) -> {'PASS' if gas['ok'] else 'FAIL'}
- Liquidity: {liq['reserve_bnb']} BNB in pool (min {MIN_LIQUIDITY_BNB}) -> {'PASS' if liq['ok'] else 'FAIL'}
- Price:     {current_price} target tokens per 1 BNB
- Trend:     {trend['message']} -> {'PASS' if trend['ok'] else 'FAIL'}

Previous cycles (oldest first):
{_summarise_history(history)}

Rules:
- If ANY guardrail FAILs, skip this cycle.
- Consider trend, not just snapshot: avoid buying when BNB just rallied hard.
- DCA is about consistency. Don't chase, don't fear.

Respond with JSON only, no markdown, no commentary:
{{"should_buy": true|false, "confidence": "low"|"medium"|"high", "reason": "<= 200 chars"}}
"""

    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip("` \n")
        data = json.loads(raw)
        return {
            "should_buy": bool(data["should_buy"]),
            "confidence": str(data.get("confidence", "low")),
            "reason":     str(data.get("reason", ""))[:200],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("Groq call failed: %s — falling back", type(exc).__name__)
        return _fallback(gas, liq, trend, "AI unavailable, fallback to manual guardrails")


def _fallback(gas: dict, liq: dict, trend: dict, prefix: str) -> dict:
    all_pass = gas["ok"] and liq["ok"] and trend["ok"]
    parts = [prefix]
    if not gas["ok"]:   parts.append(gas["message"])
    if not liq["ok"]:   parts.append(liq["message"])
    if not trend["ok"]: parts.append(trend["message"])
    return {
        "should_buy": all_pass,
        "confidence": "low",
        "reason": (" | ".join(parts))[:200],
    }


# ─────────────────────────────────────────────────────────────
# 8.  SWAP EXECUTION  (PancakeSwap V2, 1% slippage, 200k gas)
# ─────────────────────────────────────────────────────────────

def execute_swap(w3: Web3, wallet, target_token: str) -> dict:
    try:
        amount_wei = Web3.to_wei(DCA_AMOUNT_BNB, "ether")
        wbnb       = Web3.to_checksum_address(CFG["wbnb"])
        target     = Web3.to_checksum_address(target_token)
        path       = [wbnb, target]
        router     = get_router(w3)

        amounts_out = router.functions.getAmountsOut(amount_wei, path).call()
        expected    = int(amounts_out[1])
        # Integer 1% slippage — safer than float math for big token amounts.
        min_out     = expected * 99 // 100

        deadline  = int(datetime.now(timezone.utc).timestamp()) + 300
        nonce     = w3.eth.get_transaction_count(wallet.address)
        gas_price = w3.eth.gas_price

        tx = router.functions.swapExactETHForTokens(
            min_out, path, wallet.address, deadline,
        ).build_transaction({
            "from":     wallet.address,
            "value":    amount_wei,
            "gas":      200_000,
            "gasPrice": gas_price,
            "nonce":    nonce,
            "chainId":  CFG["chain_id"],
        })

        signed = wallet.sign_transaction(tx)
        raw = signed["rawTransaction"] if isinstance(signed, dict) else signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] != 1:
            return {"success": False, "tx_hash": tx_hash.hex(), "message": "Swap reverted on-chain"}

        return {
            "success":         True,
            "tx_hash":         tx_hash.hex(),
            "expected_tokens": str(expected),
            "min_tokens_out":  str(min_out),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False, "tx_hash": "",
            "message": f"Swap error: {type(exc).__name__}: {exc}",
        }


# ─────────────────────────────────────────────────────────────
# 9.  RECEIPT BUILD + ON-CHAIN ANCHOR
# ─────────────────────────────────────────────────────────────

def build_receipt(
    agent_id: int, cycle: str, decision: str,
    swap_result: dict | None,
    market: dict, reasoning: dict,
    target_token: str,
) -> dict:
    trade = {
        "tx_hash":         (swap_result or {}).get("tx_hash", ""),
        "amount_bnb":      str(DCA_AMOUNT_BNB),
        "target_token":    target_token,
        "tokens_received": (swap_result or {}).get("expected_tokens"),
    }
    return {
        "schema":    SCHEMA_VERSION,
        "agent_id":  agent_id,
        "cycle":     cycle,
        "decision":  decision,
        "trade":     trade,
        "market":    market,
        "reasoning": reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def anchor_receipt(sdk: ERC8004Agent, agent_id: int, key: str, receipt: dict) -> str:
    payload = json.dumps(receipt, separators=(",", ":"))
    log.info("setMetadata %s — %d bytes", key, len(payload.encode("utf-8")))
    res = sdk.set_metadata(agent_id=agent_id, key=key, value=payload)
    return res.get("transactionHash", "") if isinstance(res, dict) else str(res)


# ─────────────────────────────────────────────────────────────
# 10. TELEGRAM
# ─────────────────────────────────────────────────────────────

STATUS_ICONS = {"executed": "🟢", "skipped": "🟡", "failed": "🔴", "dry_run": "🔵"}


def send_telegram(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        log.warning("Telegram credentials missing; skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.error("Telegram send error: %s", exc)


def build_message(
    agent_id: int, cycle: str, decision: str,
    reasoning: dict, swap_tx_hash: str, receipt_tx_hash: str,
) -> str:
    icon  = STATUS_ICONS.get(decision, "⚪")
    bscan = CFG["bscscan_base"]
    nft   = f"{bscan}/token/{CFG['identity_registry']}?a={agent_id}"

    lines = [
        f"{icon} <b>DCA Cycle — {cycle}</b>",
        f"Agent: <a href=\"{nft}\">#{agent_id}</a> · {NETWORK}",
        f"Decision: <b>{decision.upper()}</b> "
        f"(confidence: {reasoning.get('confidence', '?')})",
        f"<i>{reasoning.get('reason', '')}</i>",
    ]
    if swap_tx_hash:
        lines.append(f"Trade: <a href=\"{bscan}/tx/{swap_tx_hash}\">view swap</a>")
    if receipt_tx_hash:
        lines.append(f"Receipt: <a href=\"{bscan}/tx/{receipt_tx_hash}\">on-chain</a>")
    lines.append("")
    lines.append(f"Agent {agent_id} — BAP-692 reference build")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 11. MAIN
# ─────────────────────────────────────────────────────────────

def run() -> int:
    validate_env()

    now   = datetime.now(timezone.utc)
    cycle = cycle_key(now)
    log.info("=== DCA cycle %s — network=%s dry_run=%s ===", cycle, NETWORK, DRY_RUN)

    agent_id = load_agent_id()
    log.info("Agent ID:  %d", agent_id)

    sdk, w3, wallet = init_clients()
    target_token = CFG["default_target_token"]

    # ── History ───────────────────────────────────────────
    history = fetch_history(sdk, agent_id, now)

    # ── Market snapshot ───────────────────────────────────
    current = current_price_per_bnb(w3, target_token)
    log.info("Price: 1 BNB = %s target tokens", current)

    # ── Guardrails ────────────────────────────────────────
    gas   = check_gas(w3)
    liq   = check_liquidity(w3, target_token)
    trend = check_price_trend(current, history)
    log.info("Gas:   %s", gas["message"])
    log.info("Liq:   %s", liq["message"])
    log.info("Trend: %s", trend["message"])

    # ── Groq decision ─────────────────────────────────────
    reasoning = groq_decision(gas, liq, trend, current, history)
    log.info("Groq: should_buy=%s confidence=%s reason=%s",
             reasoning["should_buy"], reasoning["confidence"], reasoning["reason"])

    market = {
        "gas_gwei":                 gas["value_gwei"],
        "liquidity_bnb":            liq["reserve_bnb"],
        "current_price_per_bnb":    str(current),
        "change_pct_vs_last_cycle": trend["change_pct"],
    }

    # ── Execute or skip ──────────────────────────────────
    decision = "skipped"
    swap_result: dict | None = None
    if reasoning["should_buy"]:
        if DRY_RUN:
            decision = "dry_run"
            log.info("[DRY-RUN] would execute swap of %s BNB", DCA_AMOUNT_BNB)
        else:
            log.info("Executing swap…")
            swap_result = execute_swap(w3, wallet, target_token)
            decision = "executed" if swap_result["success"] else "failed"
            if swap_result["success"]:
                log.info("Swap OK: %s", swap_result["tx_hash"])
            else:
                log.error("Swap failed: %s", swap_result.get("message"))
    else:
        log.info("Skipping cycle: %s", reasoning["reason"])

    # ── Build receipt + anchor on-chain ──────────────────
    receipt = build_receipt(agent_id, cycle, decision, swap_result, market, reasoning, target_token)
    log.info("Receipt:\n%s", json.dumps(receipt, indent=2))

    receipt_tx_hash = ""
    if DRY_RUN:
        log.info("[DRY-RUN] would setMetadata(%s) with the receipt above", cycle)
    else:
        try:
            receipt_tx_hash = anchor_receipt(sdk, agent_id, cycle, receipt)
            log.info("Receipt anchored: %s", receipt_tx_hash)
        except Exception as exc:  # noqa: BLE001
            log.error("setMetadata failed (cycle still completed): %s", exc)

    # ── Telegram alert ───────────────────────────────────
    swap_tx_hash = (swap_result or {}).get("tx_hash", "")
    msg = build_message(agent_id, cycle, decision, reasoning, swap_tx_hash, receipt_tx_hash)
    if DRY_RUN:
        log.info("[DRY-RUN] would send Telegram:\n%s", msg)
    else:
        send_telegram(msg)

    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("Fatal error: %s\n%s", exc, traceback.format_exc())
        if not DRY_RUN:
            safe = (str(exc) or "")[:240]
            send_telegram(
                f"🔴 <b>DCA cycle FAILED</b>\n"
                f"Network: {NETWORK}\n"
                f"Error: <code>{type(exc).__name__}</code>\n"
                f"<i>{safe}</i>"
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
