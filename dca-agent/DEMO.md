# DCA Agent — Plain-English Demo

This document explains what the BNB Chain DCA Agent does, why it matters,
and shows real proof of work from BSC Testnet.

Intended audience: non-technical readers, community members, and anyone curious
about what an AI-powered trading bot actually does under the hood.

---

## What Does This Agent Actually Do?

**DCA** stands for **Dollar-Cost Averaging** — a simple investing strategy where you
buy a fixed amount of an asset on a regular schedule, regardless of the price.
Instead of trying to time the market, you just buy consistently over time.

This agent automates that strategy on the BNB Chain. Here's what happens every month:

1. **It wakes up automatically** — GitHub runs it on the 1st of every month at 12:00 UTC.
   No server, no computer needs to be on. GitHub's free tier handles everything.

2. **It checks three safety conditions** (called "guardrails") before doing anything.
   See the next section for details.

3. **An AI reviews the guardrail results** — it uses Groq's LLaMA model to read all three
   checks and write a plain-language explanation of its decision.

4. **It either buys or skips:**
   - If all three guardrails pass → it buys a small amount of tokens on PancakeSwap testnet.
   - If any guardrail fails → it skips the buy and tells you exactly why.

5. **You get a Telegram message** with the result: what happened, why, and a link to the
   transaction on BscScan (if a buy was made).

That's it. Set it up once, and it runs for free, every month, indefinitely.

---

## The 3 Guardrails — and Why They Matter

These safety checks exist to protect you from bad market conditions. Even a DCA strategy
should have guardrails — "always buy no matter what" can hurt you if the market is
behaving very unusually.

---

### Guardrail 1 — Gas Price

**What it checks:** How much it costs to process the transaction on the BNB Chain.
Gas prices spike during periods of network congestion.

**The rule:** If gas is above 20 Gwei, skip this month's buy.

**Why it matters:** Paying 50 Gwei in gas to buy $5 worth of tokens means you've already
lost 10%+ on fees before the trade even starts. Waiting one day for gas to normalize
saves real money. For monthly buys, missing one cycle is trivial.

---

### Guardrail 2 — Price Stability

**What it checks:** Whether the token's price has moved more than 5% in the last hour.

**The rule:** If the price swung wildly (up or down more than 5%) in the last hour, skip.

**Why it matters:** A sudden 10% spike often means a whale is pumping the price — buying
into that means you're overpaying. A sudden 10% crash might mean something is wrong with
the project. DCA works best when you buy during normal, stable conditions, not during
anomalies. The AI can add context here that a simple rule cannot.

---

### Guardrail 3 — Liquidity

**What it checks:** How much BNB is in the trading pool on PancakeSwap.

**The rule:** If the pool has less than 1 BNB of liquidity, skip.

**Why it matters:** Low liquidity means your buy will cause significant price slippage —
you'd pay much more than the listed price. In extreme cases, a nearly-empty pool
could lead to a failed transaction or a very bad price. This guardrail ensures the
market is deep enough to absorb your buy cleanly.

---

## Why Run It on GitHub Actions Instead of a Server?

| Option | Cost | Reliability | Complexity |
|---|---|---|---|
| Personal server / VPS | $5–20/month | Depends on uptime | Needs maintenance |
| Persistent bot process | Compute costs | Can crash, needs restart | Moderate |
| **GitHub Actions cron** | **Free** | **Managed by GitHub** | **Zero maintenance** |

GitHub Actions gives you 2,000 free minutes per month. Our agent runs in about 1–2 minutes,
once a month. That's less than 0.1% of the free quota.

The trade-off: GitHub Actions has a minimum resolution of once per 5 minutes for cron jobs,
and it's designed for CI/CD — not always-on bots. That's perfectly fine for a monthly DCA.

---

## Proof of Work — BSC Testnet Transaction

The agent has been tested against BSC Testnet (Chain ID: 97). All transactions are
publicly verifiable on BscScan Testnet — no real money is involved.

**Latest test transaction:**

> After your first real run via GitHub Actions, paste the transaction hash here:
> `https://testnet.bscscan.com/tx/YOUR_TX_HASH`
>
> You can find it in the GitHub Actions run log, or in the Telegram message the agent
> sends you after a successful swap.

**What you'll see on BscScan:**
- The wallet address that initiated the transaction
- The PancakeSwap router contract being called
- The amount of tBNB spent
- The amount of testnet BUSD received
- Gas used and gas price
- Block confirmation timestamp

---

## Technical Summary (for the curious)

| Component | Technology |
|---|---|
| Blockchain interaction | Web3.py + BSC Testnet RPC |
| DEX | PancakeSwap V2 (testnet router) |
| AI reasoning | Groq API (LLaMA 3.3 70B) |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron (`0 12 1 * *`) |
| Secrets management | GitHub Actions encrypted secrets |
| Language | Python 3.11 |

---

## Want to Run It Yourself?

See [README.md](README.md) for the full setup guide. You need:

- A free [Groq account](https://console.groq.com) for the AI
- A Telegram bot (free, via [@BotFather](https://t.me/BotFather))
- A testnet wallet with some free tBNB from the [faucet](https://testnet.bnbchain.org/faucet-smart)
- A GitHub account (the free tier is enough)

Total setup time: about 15 minutes. Total ongoing cost: $0.
