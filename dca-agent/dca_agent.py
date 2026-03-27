"""
BNB Chain DCA Agent — BSC Testnet
──────────────────────────────────
Runs a Dollar-Cost-Averaging strategy on PancakeSwap testnet.
Before every buy, the Groq-powered AI checks 3 guardrails:
  1. Gas price (skip if >20 Gwei)
  2. Price stability (skip if token moved >5% in last hour)
  3. Liquidity (skip if reserves too low)
Alerts and controls are handled through a Telegram bot.
"""

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone

from dotenv import load_dotenv
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
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
# 2.  CONFIGURATION  (all sensitive values come from .env)
# ─────────────────────────────────────────────────────────────
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")   # your personal chat ID
PRIVATE_KEY         = os.getenv("WALLET_PRIVATE_KEY", "")
RPC_URL             = os.getenv("RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545/")

# DCA parameters (can be tuned via the web UI / .env)
DCA_AMOUNT_BNB          = float(os.getenv("DCA_AMOUNT_BNB", "0.01"))
DCA_FREQUENCY           = os.getenv("DCA_FREQUENCY", "daily")   # "daily" | "weekly"
GAS_THRESHOLD_GWEI      = int(os.getenv("GAS_THRESHOLD_GWEI", "20"))
PRICE_CHANGE_THRESHOLD  = float(os.getenv("PRICE_CHANGE_THRESHOLD", "5.0"))  # percent
MIN_LIQUIDITY_BNB       = float(os.getenv("MIN_LIQUIDITY_BNB", "1.0"))       # BNB in pool

# ─────────────────────────────────────────────────────────────
# 3.  BSC TESTNET CONSTANTS
# ─────────────────────────────────────────────────────────────
PANCAKESWAP_ROUTER   = Web3.to_checksum_address("0xD99D1c33F9fC3444f8101754aBC46c52416550D1")
PANCAKESWAP_FACTORY  = Web3.to_checksum_address("0x6725F303b657a9451d8BA641348b6761A6CC7a17")
WBNB_ADDRESS         = Web3.to_checksum_address("0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd")
# Default target: testnet BUSD
TARGET_TOKEN         = Web3.to_checksum_address(
    os.getenv("TARGET_TOKEN", "0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee")
)

# Minimal ABIs — only the functions we actually call
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
    raise ConnectionError(f"Cannot connect to BSC Testnet at {RPC_URL}")

log.info("Connected to BSC Testnet — chain ID %s", w3.eth.chain_id)

router   = w3.eth.contract(address=PANCAKESWAP_ROUTER,  abi=ROUTER_ABI)
factory  = w3.eth.contract(address=PANCAKESWAP_FACTORY, abi=FACTORY_ABI)

# Derive wallet address from private key
wallet = w3.eth.account.from_key(PRIVATE_KEY)
WALLET_ADDRESS = wallet.address
log.info("Wallet address: %s", WALLET_ADDRESS)

# ─────────────────────────────────────────────────────────────
# 5.  AGENT STATE
# ─────────────────────────────────────────────────────────────
# price_history stores (timestamp_utc, price_in_bnb_per_token) tuples
# We keep up to 120 entries (≈2 hours at 1-minute sampling)
state = {
    "paused":         False,
    "history":        [],       # list of cycle result dicts
    "price_history":  deque(maxlen=120),
    "total_invested": 0.0,      # BNB spent so far
    "cycles_run":     0,
    "cycles_skipped": 0,
}

groq_client = Groq(api_key=GROQ_API_KEY)

# ─────────────────────────────────────────────────────────────
# 6.  PRICE HELPERS
# ─────────────────────────────────────────────────────────────
def get_current_price_bnb() -> float:
    """
    Returns how many tokens 1 BNB buys right now (via PancakeSwap getAmountsOut).
    Returns 0.0 if the call fails.
    """
    try:
        one_bnb = Web3.to_wei(1, "ether")
        path = [WBNB_ADDRESS, TARGET_TOKEN]
        amounts = router.functions.getAmountsOut(one_bnb, path).call()
        # amounts[1] is in the token's decimals — we use raw value for ratio comparison
        return float(amounts[1])
    except Exception as exc:
        log.warning("getAmountsOut failed: %s", exc)
        return 0.0


def record_price_snapshot():
    """Called by the background job every minute to track price history."""
    price = get_current_price_bnb()
    if price > 0:
        state["price_history"].append((datetime.now(timezone.utc), price))


def price_change_last_hour() -> float:
    """
    Compares current price vs the oldest snapshot within the last 60 minutes.
    Returns percentage change (positive = price went up, negative = down).
    Returns 0.0 if not enough history.
    """
    now = datetime.now(timezone.utc)
    current = get_current_price_bnb()
    if current == 0:
        return 0.0

    # Find the oldest snapshot within the last 60 minutes
    cutoff = now.timestamp() - 3600
    candidates = [
        (ts, price)
        for ts, price in state["price_history"]
        if ts.timestamp() >= cutoff
    ]

    if not candidates:
        return 0.0   # not enough data → assume stable

    oldest_price = candidates[0][1]
    if oldest_price == 0:
        return 0.0

    return ((current - oldest_price) / oldest_price) * 100.0

# ─────────────────────────────────────────────────────────────
# 7.  GUARDRAIL CHECKS
# ─────────────────────────────────────────────────────────────
def check_gas_price() -> dict:
    """
    Guardrail 1: Gas price must be below GAS_THRESHOLD_GWEI.
    Returns {"ok": bool, "value_gwei": float, "message": str}
    """
    gas_wei    = w3.eth.gas_price
    gas_gwei   = gas_wei / 1e9
    ok         = gas_gwei <= GAS_THRESHOLD_GWEI
    return {
        "ok":         ok,
        "value_gwei": round(gas_gwei, 2),
        "message":    (
            f"Gas OK ({gas_gwei:.2f} Gwei ≤ {GAS_THRESHOLD_GWEI} Gwei)"
            if ok else
            f"Gas too high ({gas_gwei:.2f} Gwei > {GAS_THRESHOLD_GWEI} Gwei threshold)"
        ),
    }


def check_price_stability() -> dict:
    """
    Guardrail 2: Token price must not have moved more than PRICE_CHANGE_THRESHOLD%
    in the last hour.
    Returns {"ok": bool, "change_pct": float, "message": str}
    """
    change = price_change_last_hour()
    ok     = abs(change) <= PRICE_CHANGE_THRESHOLD
    return {
        "ok":         ok,
        "change_pct": round(change, 2),
        "message":    (
            f"Price stable ({change:+.2f}% in last hour)"
            if ok else
            f"Price volatile ({change:+.2f}% > ±{PRICE_CHANGE_THRESHOLD}% threshold)"
        ),
    }


def check_liquidity() -> dict:
    """
    Guardrail 3: The BNB/TOKEN pool must have at least MIN_LIQUIDITY_BNB in BNB reserves.
    Returns {"ok": bool, "reserve_bnb": float, "message": str}
    """
    try:
        pair_address = factory.functions.getPair(WBNB_ADDRESS, TARGET_TOKEN).call()
        if pair_address == "0x0000000000000000000000000000000000000000":
            return {"ok": False, "reserve_bnb": 0.0, "message": "Liquidity pool does not exist"}

        pair         = w3.eth.contract(address=pair_address, abi=PAIR_ABI)
        reserves     = pair.functions.getReserves().call()
        token0       = pair.functions.token0().call()

        # Determine which reserve slot is WBNB
        if token0.lower() == WBNB_ADDRESS.lower():
            bnb_reserve_wei = reserves[0]
        else:
            bnb_reserve_wei = reserves[1]

        reserve_bnb = float(Web3.from_wei(bnb_reserve_wei, "ether"))
        ok          = reserve_bnb >= MIN_LIQUIDITY_BNB
        return {
            "ok":          ok,
            "reserve_bnb": round(reserve_bnb, 4),
            "message":     (
                f"Liquidity OK ({reserve_bnb:.4f} BNB in pool)"
                if ok else
                f"Liquidity too low ({reserve_bnb:.4f} BNB < {MIN_LIQUIDITY_BNB} BNB threshold)"
            ),
        }
    except Exception as exc:
        log.warning("Liquidity check failed: %s", exc)
        return {"ok": False, "reserve_bnb": 0.0, "message": f"Liquidity check error: {exc}"}

# ─────────────────────────────────────────────────────────────
# 8.  GROQ AI ANALYSIS
# ─────────────────────────────────────────────────────────────
def ai_should_buy(gas_result: dict, price_result: dict, liq_result: dict) -> dict:
    """
    Sends guardrail data to Groq llama3-8b-8192 and asks whether to execute the DCA buy.
    The AI acts as a final reasoning layer on top of the raw checks.
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
   - Threshold: ±{PRICE_CHANGE_THRESHOLD}%
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
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,   # low temperature for consistent decisions
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        log.info("Groq decision: %s", result)
        return result

    except Exception as exc:
        log.error("Groq API error: %s", exc)
        # Fallback: apply strict AND logic ourselves if AI is unavailable
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
# 9.  SWAP EXECUTION
# ─────────────────────────────────────────────────────────────
def execute_swap() -> dict:
    """
    Calls swapExactETHForTokens on PancakeSwap testnet router.
    Swaps DCA_AMOUNT_BNB of tBNB for TARGET_TOKEN.
    Returns {"success": bool, "tx_hash": str, "message": str}
    """
    try:
        amount_wei  = Web3.to_wei(DCA_AMOUNT_BNB, "ether")
        path        = [WBNB_ADDRESS, TARGET_TOKEN]
        deadline    = int(datetime.now(timezone.utc).timestamp()) + 300  # 5 minutes

        # 1% slippage tolerance: get expected output and allow 1% less
        amounts_out  = router.functions.getAmountsOut(amount_wei, path).call()
        min_out      = int(amounts_out[1] * 0.99)

        nonce        = w3.eth.get_transaction_count(WALLET_ADDRESS)
        gas_price    = w3.eth.gas_price

        tx = router.functions.swapExactETHForTokens(
            min_out, path, WALLET_ADDRESS, deadline
        ).build_transaction({
            "from":     WALLET_ADDRESS,
            "value":    amount_wei,
            "gas":      200_000,
            "gasPrice": gas_price,
            "nonce":    nonce,
            "chainId":  97,  # BSC Testnet chain ID
        })

        signed  = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            tx_hex = tx_hash.hex()
            log.info("Swap successful: %s", tx_hex)
            return {
                "success":  True,
                "tx_hash":  tx_hex,
                "message":  f"Swap executed successfully! Bought tokens for {DCA_AMOUNT_BNB} BNB.",
                "explorer": f"https://testnet.bscscan.com/tx/{tx_hex}",
            }
        else:
            log.error("Swap reverted: %s", tx_hash.hex())
            return {
                "success": False,
                "tx_hash": tx_hash.hex(),
                "message": "Swap transaction reverted on-chain.",
            }

    except Exception as exc:
        log.error("Swap execution error: %s", exc)
        return {"success": False, "tx_hash": "", "message": f"Swap error: {exc}"}

# ─────────────────────────────────────────────────────────────
# 10.  DCA CYCLE — the main logic loop
# ─────────────────────────────────────────────────────────────
async def run_dca_cycle(context=None):
    """
    Called by the scheduler at the configured DCA interval.
    Runs all guardrails → AI decision → swap (or skip).
    Sends a Telegram alert with the result.
    """
    if state["paused"]:
        log.info("DCA cycle skipped — agent is paused.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("── DCA Cycle starting at %s ──", timestamp)

    # Run the three guardrail checks
    gas_result   = check_gas_price()
    price_result = check_price_stability()
    liq_result   = check_liquidity()

    log.info("Gas:       %s", gas_result["message"])
    log.info("Price:     %s", price_result["message"])
    log.info("Liquidity: %s", liq_result["message"])

    # Ask Groq AI to make the final decision
    decision = ai_should_buy(gas_result, price_result, liq_result)

    cycle_record = {
        "timestamp":    timestamp,
        "gas":          gas_result,
        "price":        price_result,
        "liquidity":    liq_result,
        "ai_decision":  decision,
        "executed":     False,
        "tx_hash":      "",
    }

    if decision["should_buy"]:
        # All guardrails passed → execute the swap
        swap_result = execute_swap()
        cycle_record["executed"] = swap_result["success"]
        cycle_record["tx_hash"]  = swap_result.get("tx_hash", "")

        if swap_result["success"]:
            state["total_invested"] += DCA_AMOUNT_BNB
            state["cycles_run"]     += 1
            msg = (
                f"✅ *DCA Buy Executed*\n"
                f"📅 {timestamp}\n"
                f"💰 Bought tokens for `{DCA_AMOUNT_BNB}` BNB\n"
                f"⛽ Gas: `{gas_result['value_gwei']} Gwei`\n"
                f"📊 Price change: `{price_result['change_pct']:+.2f}%`\n"
                f"💧 Liquidity: `{liq_result['reserve_bnb']} BNB`\n"
                f"🤖 AI: _{decision['reason']}_\n"
                f"🔗 [View on BscScan]({swap_result['explorer']})"
            )
        else:
            state["cycles_skipped"] += 1
            msg = (
                f"⚠️ *DCA Swap Failed*\n"
                f"📅 {timestamp}\n"
                f"{swap_result['message']}\n"
                f"🤖 AI approved but swap reverted on-chain."
            )
    else:
        # At least one guardrail failed → skip this cycle
        state["cycles_skipped"] += 1
        failed = []
        if not gas_result["ok"]:   failed.append(f"⛽ {gas_result['message']}")
        if not price_result["ok"]: failed.append(f"📊 {price_result['message']}")
        if not liq_result["ok"]:   failed.append(f"💧 {liq_result['message']}")

        msg = (
            f"⏭️ *DCA Cycle Skipped*\n"
            f"📅 {timestamp}\n"
            f"🤖 AI reason: _{decision['reason']}_\n\n"
            f"*Failed guardrails:*\n" + "\n".join(failed)
        )

    state["history"].append(cycle_record)
    # Keep only last 50 cycle records
    if len(state["history"]) > 50:
        state["history"] = state["history"][-50:]

    # Send Telegram notification
    await send_telegram(msg, context)


async def send_telegram(text: str, context=None):
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_CHAT_ID:
        log.warning("TELEGRAM_CHAT_ID not set — skipping Telegram notification.")
        return
    try:
        if context:
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        log.info("Telegram message sent.")
    except Exception as exc:
        log.error("Telegram send error: %s", exc)

# ─────────────────────────────────────────────────────────────
# 11.  PRICE TRACKER BACKGROUND JOB (runs every 60 seconds)
# ─────────────────────────────────────────────────────────────
async def price_tracker_job(context=None):
    """Background job: records price every minute for stability checks."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, record_price_snapshot)

# ─────────────────────────────────────────────────────────────
# 12.  TELEGRAM BOT COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — show current agent status and last guardrail readings."""
    gas   = check_gas_price()
    price = check_price_stability()
    liq   = check_liquidity()

    bnb_balance = float(Web3.from_wei(w3.eth.get_balance(WALLET_ADDRESS), "ether"))

    text = (
        f"📊 *DCA Agent Status*\n"
        f"{'🟢 Running' if not state['paused'] else '🔴 Paused'}\n\n"
        f"*Wallet:* `{WALLET_ADDRESS[:10]}...`\n"
        f"*Balance:* `{bnb_balance:.4f} tBNB`\n"
        f"*Target:* `{DCA_AMOUNT_BNB} BNB` per cycle ({DCA_FREQUENCY})\n"
        f"*Total invested:* `{state['total_invested']:.4f} BNB`\n"
        f"*Cycles run:* `{state['cycles_run']}`\n"
        f"*Cycles skipped:* `{state['cycles_skipped']}`\n\n"
        f"*Current Guardrails:*\n"
        f"{'✅' if gas['ok'] else '❌'} Gas: `{gas['value_gwei']} Gwei`\n"
        f"{'✅' if price['ok'] else '❌'} Price change: `{price['change_pct']:+.2f}%`\n"
        f"{'✅' if liq['ok'] else '❌'} Liquidity: `{liq['reserve_bnb']} BNB`\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pause — pause the DCA agent (skips upcoming cycles)."""
    state["paused"] = True
    await update.message.reply_text(
        "⏸️ *DCA Agent paused.* Cycles will be skipped until you /resume.",
        parse_mode="Markdown",
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/resume — resume the DCA agent."""
    state["paused"] = False
    await update.message.reply_text(
        "▶️ *DCA Agent resumed.* Cycles will run on schedule.",
        parse_mode="Markdown",
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/history — show last 5 DCA cycle results."""
    if not state["history"]:
        await update.message.reply_text("No cycles have run yet.")
        return

    recent = state["history"][-5:]
    lines  = ["📜 *Last 5 DCA Cycles*\n"]

    for c in reversed(recent):
        icon = "✅" if c["executed"] else ("⏭️" if not c["ai_decision"]["should_buy"] else "⚠️")
        tx_part = f"\n   🔗 [tx]({f'https://testnet.bscscan.com/tx/{c[\"tx_hash\"]}'})" if c["tx_hash"] else ""
        lines.append(
            f"{icon} `{c['timestamp']}`\n"
            f"   _{c['ai_decision']['reason'][:80]}_"
            + tx_part
        )

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_runnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runnow — manually trigger a DCA cycle immediately."""
    await update.message.reply_text("🔄 Triggering DCA cycle now...")
    was_paused = state["paused"]
    state["paused"] = False
    await run_dca_cycle(context)
    state["paused"] = was_paused

# ─────────────────────────────────────────────────────────────
# 13.  MAIN — wire everything together
# ─────────────────────────────────────────────────────────────
def main():
    # Build the Telegram Application
    # python-telegram-bot v20+ requires the [job-queue] extra for scheduling
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register Telegram command handlers
    application.add_handler(CommandHandler("status",  cmd_status))
    application.add_handler(CommandHandler("pause",   cmd_pause))
    application.add_handler(CommandHandler("resume",  cmd_resume))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("runnow",  cmd_runnow))

    # Determine DCA interval in seconds
    dca_interval = 86_400 if DCA_FREQUENCY == "daily" else 604_800  # daily or weekly

    # Schedule the price tracker (every 60 seconds)
    application.job_queue.run_repeating(
        price_tracker_job,
        interval=60,
        first=5,
        name="price_tracker",
    )

    # Schedule the DCA cycle
    application.job_queue.run_repeating(
        run_dca_cycle,
        interval=dca_interval,
        first=30,   # first run 30 seconds after startup
        name="dca_cycle",
    )

    log.info(
        "DCA Agent started — frequency: %s, amount: %s BNB, target token: %s",
        DCA_FREQUENCY, DCA_AMOUNT_BNB, TARGET_TOKEN,
    )

    # Start polling (blocking)
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
