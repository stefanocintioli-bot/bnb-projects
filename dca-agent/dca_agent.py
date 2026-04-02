"""
BNB Chain DCA Agent — BSC Testnet
──────────────────────────────────
Single-run script. Designed to be invoked by a cron job (e.g. GitHub Actions)
once per month. Runs guardrails → AI decision → swap (or skip) → Telegram alert
→ exits.

Usage:
  python dca_agent.py            # live run
  python dca_agent.py --dry-run  # simulate without executing the swap
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from groq import Groq
from web3 import Web3

# ─────────────────────────────────────────────────────────────
# 1.  ENVIRONMENT & LOGGING
# ─────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 2.  CONFIGURATION  (all sensitive values come from env / GitHub Secrets)
# ─────────────────────────────────────────────────────────────
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
PRIVATE_KEY         = os.getenv("WALLET_PRIVATE_KEY", "")
RPC_URL             = os.getenv("RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545/")

# DCA parameters
DCA_AMOUNT_BNB          = float(os.getenv("DCA_AMOUNT_BNB", "0.01"))
GAS_THRESHOLD_GWEI      = int(os.getenv("GAS_THRESHOLD_GWEI", "20"))
PRICE_CHANGE_THRESHOLD  = float(os.getenv("PRICE_CHANGE_THRESHOLD", "5.0"))  # percent
MIN_LIQUIDITY_BNB       = float(os.getenv("MIN_LIQUIDITY_BNB", "1.0"))
TOKEN_NAME              = os.getenv("TOKEN_NAME", "USDT (BSC Testnet)")

# Cloudflare KV (optional — enables /status /history /nextrun /dryrun via Telegram bot)
CF_ACCOUNT_ID      = os.getenv("CF_ACCOUNT_ID", "")
CF_KV_NAMESPACE_ID = os.getenv("CF_KV_NAMESPACE_ID", "")
CF_KV_API_TOKEN    = os.getenv("CF_KV_API_TOKEN", "")

# ─────────────────────────────────────────────────────────────
# 3.  BSC TESTNET CONSTANTS
# ─────────────────────────────────────────────────────────────
PANCAKESWAP_ROUTER   = Web3.to_checksum_address("0xD99D1c33F9fC3444f8101754aBC46c52416550D1")
PANCAKESWAP_FACTORY  = Web3.to_checksum_address("0x6725F303b657a9451d8BA641348b6761A6CC7a17")
WBNB_ADDRESS         = Web3.to_checksum_address("0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd")
TARGET_TOKEN         = Web3.to_checksum_address(
    os.getenv("TARGET_TOKEN", "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee")
)

ROUTER_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
      {"internalType": "address[]", "name": "path", "type": "address[]"},
      {"internalType": "address", "name": "to", "type": "address"},
      {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactETHForTokens",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "payable",
    "type": "function"
  },
  {
    "inputs": [
      {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
      {"internalType": "address[]", "name": "path", "type": "address[]"}
    ],
    "name": "getAmountsOut",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

FACTORY_ABI = json.loads("""[
  {
    "inputs": [
      {"internalType": "address", "name": "tokenA", "type": "address"},
      {"internalType": "address", "name": "tokenB", "type": "address"}
    ],
    "name": "getPair",
    "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

PAIR_ABI = json.loads("""[
  {
    "inputs": [],
    "name": "getReserves",
    "outputs": [
      {"internalType": "uint112", "name": "reserve0", "type": "uint112"},
      {"internalType": "uint112", "name": "reserve1", "type": "uint112"},
      {"internalType": "uint32",  "name": "blockTimestampLast", "type": "uint32"}
    ],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "token0",
    "outputs": [{"internalType": "address", "name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

# ─────────────────────────────────────────────────────────────
# 4.  WEB3 & CONTRACT SETUP
# ─────────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    log.error("Cannot connect to BSC Testnet at %s", RPC_URL)
    sys.exit(1)

log.info("Connected to BSC Testnet — chain ID %s", w3.eth.chain_id)

router  = w3.eth.contract(address=PANCAKESWAP_ROUTER,  abi=ROUTER_ABI)
factory = w3.eth.contract(address=PANCAKESWAP_FACTORY, abi=FACTORY_ABI)

wallet         = w3.eth.account.from_key(PRIVATE_KEY)
WALLET_ADDRESS = wallet.address
log.info("Wallet address: %s", WALLET_ADDRESS)

groq_client = Groq(api_key=GROQ_API_KEY)

# ─────────────────────────────────────────────────────────────
# 5.  TELEGRAM HELPER  (simple HTTP call — no persistent bot needed)
# ─────────────────────────────────────────────────────────────
def send_telegram(text: str) -> None:
    """Send a plain-text message to the configured Telegram chat via Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set — skipping notification.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id":                  TELEGRAM_CHAT_ID,
                "text":                     text,
                "parse_mode":               "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        log.info("Telegram message sent.")
    except Exception as exc:
        log.error("Telegram send error: %s", exc)

# ─────────────────────────────────────────────────────────────
# 6.  CLOUDFLARE KV HELPERS  (no-op when CF vars are absent)
# ─────────────────────────────────────────────────────────────
_KV_BASE = (
    "https://api.cloudflare.com/client/v4/accounts/{account}"
    "/storage/kv/namespaces/{ns}/values/{key}"
)


def _kv_headers() -> dict:
    return {
        "Authorization": f"Bearer {CF_KV_API_TOKEN}",
        "Content-Type":  "application/json",
    }


def _kv_configured() -> bool:
    return bool(CF_ACCOUNT_ID and CF_KV_NAMESPACE_ID and CF_KV_API_TOKEN)


def read_kv(key: str):
    """Read and JSON-parse a value from Cloudflare KV. Returns None on miss or error."""
    if not _kv_configured():
        return None
    url = _KV_BASE.format(account=CF_ACCOUNT_ID, ns=CF_KV_NAMESPACE_ID, key=key)
    try:
        resp = requests.get(url, headers=_kv_headers(), timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("KV read failed for key '%s': %s", key, exc)
        return None


def write_kv(key: str, value) -> None:
    """Serialise value as JSON and write it to Cloudflare KV."""
    if not _kv_configured():
        log.info("Cloudflare KV not configured — skipping KV write for '%s'.", key)
        return
    url = _KV_BASE.format(account=CF_ACCOUNT_ID, ns=CF_KV_NAMESPACE_ID, key=key)
    try:
        resp = requests.put(
            url,
            data=json.dumps(value),
            headers=_kv_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        log.info("KV write OK: %s", key)
    except Exception as exc:
        log.error("KV write failed for key '%s': %s", key, exc)


def persist_run(record: dict) -> None:
    """Write last_run (with running totals) and update history (last 5) in KV."""
    # Carry forward cumulative cycle counters from previous last_run
    prev      = read_kv("last_run") or {}
    prev_run  = int(prev.get("total_cycles_run",     0))
    prev_skip = int(prev.get("total_cycles_skipped", 0))

    status = record.get("status", "")
    if status == "executed":
        record["total_cycles_run"]     = prev_run + 1
        record["total_cycles_skipped"] = prev_skip
    elif status == "skipped":
        record["total_cycles_run"]     = prev_run
        record["total_cycles_skipped"] = prev_skip + 1
    else:
        # failed / dry_run — counters unchanged
        record["total_cycles_run"]     = prev_run
        record["total_cycles_skipped"] = prev_skip

    write_kv("last_run", record)
    existing = read_kv("history") or []
    if not isinstance(existing, list):
        existing = []
    write_kv("history", ([record] + existing)[:5])


# ─────────────────────────────────────────────────────────────
# 7.  PRICE HELPER
# ─────────────────────────────────────────────────────────────
def get_current_price_bnb() -> float:
    """Returns how many tokens 1 BNB buys right now via PancakeSwap."""
    try:
        one_bnb = Web3.to_wei(1, "ether")
        amounts = router.functions.getAmountsOut(one_bnb, [WBNB_ADDRESS, TARGET_TOKEN]).call()
        return float(amounts[1])
    except Exception as exc:
        log.warning("getAmountsOut failed: %s", exc)
        return 0.0

# ─────────────────────────────────────────────────────────────
# 8.  GUARDRAIL CHECKS
# ─────────────────────────────────────────────────────────────
def check_gas_price() -> dict:
    """Guardrail 1: gas must be below GAS_THRESHOLD_GWEI."""
    gas_gwei = w3.eth.gas_price / 1e9
    ok = gas_gwei <= GAS_THRESHOLD_GWEI
    return {
        "ok":         ok,
        "value_gwei": round(gas_gwei, 2),
        "message": (
            f"Gas OK ({gas_gwei:.2f} Gwei <= {GAS_THRESHOLD_GWEI} Gwei)"
            if ok else
            f"Gas too high ({gas_gwei:.2f} Gwei > {GAS_THRESHOLD_GWEI} Gwei threshold)"
        ),
    }


def check_price_stability() -> dict:
    """
    Guardrail 2: price must not have moved more than PRICE_CHANGE_THRESHOLD% in the last hour.

    Note: in single-run mode there is no 60-minute price history to compare against.
    This check always passes (0% change). The gas and liquidity guardrails remain fully
    active. To add historical price context, configure a price-oracle or persist the
    last price in a GitHub Actions artifact between runs.
    """
    return {
        "ok":         True,
        "change_pct": 0.0,
        "message":    "Price stability: no historical snapshot available — assuming stable (single-run mode).",
    }


def check_liquidity() -> dict:
    """Guardrail 3: BNB/TOKEN pool must have at least MIN_LIQUIDITY_BNB in BNB reserves."""
    try:
        pair_address = factory.functions.getPair(WBNB_ADDRESS, TARGET_TOKEN).call()
        if pair_address == "0x0000000000000000000000000000000000000000":
            return {"ok": False, "reserve_bnb": 0.0, "message": "Liquidity pool does not exist"}

        pair     = w3.eth.contract(address=pair_address, abi=PAIR_ABI)
        reserves = pair.functions.getReserves().call()
        token0   = pair.functions.token0().call()

        bnb_reserve_wei = reserves[0] if token0.lower() == WBNB_ADDRESS.lower() else reserves[1]
        reserve_bnb = float(Web3.from_wei(bnb_reserve_wei, "ether"))
        ok = reserve_bnb >= MIN_LIQUIDITY_BNB

        return {
            "ok":          ok,
            "reserve_bnb": round(reserve_bnb, 4),
            "message": (
                f"Liquidity OK ({reserve_bnb:.4f} BNB in pool)"
                if ok else
                f"Liquidity too low ({reserve_bnb:.4f} BNB < {MIN_LIQUIDITY_BNB} BNB threshold)"
            ),
        }
    except Exception as exc:
        log.warning("Liquidity check failed: %s", exc)
        return {"ok": False, "reserve_bnb": 0.0, "message": f"Liquidity check error: {exc}"}

# ─────────────────────────────────────────────────────────────
# 9.  GROQ AI ANALYSIS
# ─────────────────────────────────────────────────────────────
def ai_should_buy(gas_result: dict, price_result: dict, liq_result: dict) -> dict:
    """
    Sends guardrail data to Groq llama-3.3-70b-versatile and asks whether to buy.
    Falls back to strict AND logic if the API is unavailable.
    Returns {"should_buy": bool, "reason": str}
    """
    prompt = f"""
You are a DCA (Dollar-Cost-Averaging) risk management AI for a crypto trading bot on BNB Chain testnet.

Your job: decide whether to execute a small buy of {DCA_AMOUNT_BNB} BNB worth of tokens RIGHT NOW.

Here are the current market guardrail readings:

1. GAS PRICE CHECK
   - Status: {"PASS" if gas_result["ok"] else "FAIL"}
   - Current gas: {gas_result["value_gwei"]} Gwei
   - Threshold: {GAS_THRESHOLD_GWEI} Gwei
   - Detail: {gas_result["message"]}

2. PRICE STABILITY CHECK
   - Status: {"PASS" if price_result["ok"] else "FAIL"}
   - Price change last hour: {price_result["change_pct"]}%
   - Threshold: +/-{PRICE_CHANGE_THRESHOLD}%
   - Detail: {price_result["message"]}

3. LIQUIDITY CHECK
   - Status: {"PASS" if liq_result["ok"] else "FAIL"}
   - BNB in pool: {liq_result["reserve_bnb"]} BNB
   - Minimum required: {MIN_LIQUIDITY_BNB} BNB
   - Detail: {liq_result["message"]}

Rule: Execute the buy ONLY if ALL three guardrails PASS.
If even one fails, skip this cycle and explain why clearly in plain language (suitable for a Telegram message).
Be concise. Do not use technical jargon the user won't understand.

Respond with a JSON object only (no markdown, no extra text):
{{"should_buy": true/false, "reason": "your explanation here"}}
"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        log.info("Groq decision: %s", result)
        return result

    except Exception as exc:
        log.error("Groq API error: %s", exc)
        all_pass = gas_result["ok"] and price_result["ok"] and liq_result["ok"]
        return {
            "should_buy": all_pass,
            "reason": (
                "AI unavailable — applied manual guardrails. " +
                (gas_result["message"] if not gas_result["ok"] else "") + " " +
                (price_result["message"] if not price_result["ok"] else "") + " " +
                (liq_result["message"] if not liq_result["ok"] else "")
            ).strip(),
        }

# ─────────────────────────────────────────────────────────────
# 10.  SWAP EXECUTION
# ─────────────────────────────────────────────────────────────
def execute_swap() -> dict:
    """Calls swapExactETHForTokens on PancakeSwap testnet. 1% slippage tolerance."""
    try:
        amount_wei  = Web3.to_wei(DCA_AMOUNT_BNB, "ether")
        path        = [WBNB_ADDRESS, TARGET_TOKEN]
        deadline    = int(datetime.now(timezone.utc).timestamp()) + 300

        amounts_out = router.functions.getAmountsOut(amount_wei, path).call()
        min_out     = int(amounts_out[1] * 0.99)

        nonce     = w3.eth.get_transaction_count(WALLET_ADDRESS)
        gas_price = w3.eth.gas_price

        tx = router.functions.swapExactETHForTokens(
            min_out, path, WALLET_ADDRESS, deadline
        ).build_transaction({
            "from":     WALLET_ADDRESS,
            "value":    amount_wei,
            "gas":      200_000,
            "gasPrice": gas_price,
            "nonce":    nonce,
            "chainId":  97,
        })

        signed  = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            tx_hex = tx_hash.hex()
            log.info("Swap successful: %s", tx_hex)
            return {
                "success":  True,
                "tx_hash":  tx_hex,
                "message":  f"Swap executed. Bought tokens for {DCA_AMOUNT_BNB} BNB.",
                "explorer": f"https://testnet.bscscan.com/tx/{tx_hex}",
            }
        else:
            return {
                "success": False,
                "tx_hash": tx_hash.hex(),
                "message": "Swap transaction reverted on-chain.",
            }

    except Exception as exc:
        log.error("Swap execution error: %s", exc)
        return {"success": False, "tx_hash": "", "message": f"Swap error: {exc}"}

# ─────────────────────────────────────────────────────────────
# 11.  MAIN — single-run entry point
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BNB Chain DCA Agent — single-run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the cycle without executing the swap or sending Telegram alerts.",
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        log.info("=== DRY-RUN MODE — no swap will be executed ===")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("DCA cycle started at %s", timestamp)

    # ── Guardrails ────────────────────────────────────────────
    log.info("[1/3] Checking gas price...")
    gas_result = check_gas_price()
    log.info("      %s", gas_result["message"])

    log.info("[2/3] Checking price stability...")
    price_result = check_price_stability()
    log.info("      %s", price_result["message"])

    log.info("[3/3] Checking liquidity...")
    liq_result = check_liquidity()
    log.info("      %s", liq_result["message"])

    # ── AI decision ───────────────────────────────────────────
    log.info("[AI]  Sending guardrail data to Groq...")
    decision = ai_should_buy(gas_result, price_result, liq_result)
    log.info("[AI]  should_buy=%s | reason=%s", decision["should_buy"], decision["reason"])

    # ── Base run record (persisted to KV after the cycle) ─────
    run_record = {
        "status":               "pending",
        "timestamp":            timestamp,
        "token_name":           TOKEN_NAME,
        "token_address":        TARGET_TOKEN,
        "amount_bnb":           DCA_AMOUNT_BNB,
        "gas_gwei":             gas_result["value_gwei"],
        "price_change_pct":     price_result["change_pct"],
        "liquidity_bnb":        liq_result["reserve_bnb"],
        "reason":               decision["reason"],
        "tx_hash":              "",
        "tx_url":               "",
        "dry_run":              dry_run,
        # total_cycles_run / total_cycles_skipped filled in by persist_run()
    }

    exit_code = 0

    # ── Execute or skip ───────────────────────────────────────
    if decision["should_buy"]:
        if dry_run:
            log.info("[DRY-RUN] All guardrails passed. Would execute swap of %s BNB.", DCA_AMOUNT_BNB)
            run_record["status"] = "dry_run"
            msg = (
                f"<b>[DRY-RUN] DCA Cycle Simulated</b>\n"
                f"Date: {timestamp}\n"
                f"All guardrails passed.\n"
                f"Would buy tokens for <code>{DCA_AMOUNT_BNB}</code> BNB\n"
                f"Gas: <code>{gas_result['value_gwei']} Gwei</code>\n"
                f"Liquidity: <code>{liq_result['reserve_bnb']} BNB</code>\n"
                f"AI: <i>{decision['reason']}</i>\n"
                f"(No swap executed — dry-run mode)"
            )
        else:
            log.info("All guardrails passed — executing swap...")
            swap_result = execute_swap()

            if swap_result["success"]:
                run_record["status"]   = "executed"
                run_record["tx_hash"]  = swap_result["tx_hash"]
                run_record["tx_url"]   = swap_result["explorer"]
                msg = (
                    f"<b>DCA Buy Executed</b>\n"
                    f"Date: {timestamp}\n"
                    f"Bought tokens for <code>{DCA_AMOUNT_BNB}</code> BNB\n"
                    f"Gas: <code>{gas_result['value_gwei']} Gwei</code>\n"
                    f"Liquidity: <code>{liq_result['reserve_bnb']} BNB</code>\n"
                    f"AI: <i>{decision['reason']}</i>\n"
                    f"<a href=\"{swap_result['explorer']}\">View on BscScan</a>"
                )
            else:
                run_record["status"] = "failed"
                log.error("Swap failed: %s", swap_result["message"])
                msg = (
                    f"<b>DCA Swap Failed</b>\n"
                    f"Date: {timestamp}\n"
                    f"{swap_result['message']}\n"
                    f"AI approved but swap reverted on-chain."
                )
                exit_code = 1
    else:
        run_record["status"] = "skipped"
        failed = []
        if not gas_result["ok"]:   failed.append(f"Gas: {gas_result['message']}")
        if not price_result["ok"]: failed.append(f"Price: {price_result['message']}")
        if not liq_result["ok"]:   failed.append(f"Liquidity: {liq_result['message']}")
        msg = (
            f"<b>DCA Cycle Skipped</b>\n"
            f"Date: {timestamp}\n"
            f"AI: <i>{decision['reason']}</i>\n\n"
            f"<b>Failed guardrails:</b>\n" + "\n".join(failed)
        )
        log.info("Cycle skipped — %s", " | ".join(failed) if failed else decision["reason"])

    # ── Persist run record to Cloudflare KV ──────────────────
    persist_run(run_record)

    # ── Telegram alert ────────────────────────────────────────
    if dry_run:
        log.info("[DRY-RUN] Telegram message that would be sent:\n%s", msg)
    else:
        send_telegram(msg)

    log.info("DCA cycle complete.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
