# BNB Chain DCA Agent

An AI-powered Dollar-Cost-Averaging bot for BNB Chain **testnet**. Runs once a month as a
GitHub Actions cron job — free forever, no server needed. Before every buy, a Groq LLM checks
three on-chain guardrails and sends you a Telegram alert whether the trade executes or gets
skipped.

---

## What It Does

| Feature | Detail |
|---|---|
| **DCA cadence** | 1st of every month at 12:00 UTC (GitHub Actions cron) |
| **AI guardrails** | Gas price · Price stability · Pool liquidity |
| **AI model** | Groq `llama-3.3-70b-versatile` (free tier) |
| **DEX** | PancakeSwap testnet |
| **Alerts** | Telegram notifications with plain-language explanations |
| **Network** | BSC Testnet — no real money |
| **Cost** | Free (GitHub Actions free tier: 2,000 min/month) |

---

## Files

```
dca-agent/
├── dca_agent.py                        ← Single-run script (Web3 + Groq + Telegram)
├── .github/
│   └── workflows/
│       └── dca-monthly.yml             ← GitHub Actions cron job
├── requirements.txt                    ← Python dependencies
├── .env.example                        ← Template for local development
├── README.md                           ← This file
└── DEMO.md                             ← Plain-English explainer for non-technical readers
```

---

## GitHub Actions Setup (step by step)

### Step 1 — Fork or push to GitHub

Make sure this repo is on GitHub. If you're starting fresh:

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/dca-agent.git
git push -u origin main
```

### Step 2 — Add GitHub Secrets

The agent reads all sensitive values from GitHub Secrets — **never from code**.

1. Go to your repo on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add each of the following:

| Secret name | Where to get it |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys |
| `TELEGRAM_BOT_TOKEN` | Telegram → [@BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_CHAT_ID` | Telegram → [@userinfobot](https://t.me/userinfobot) → send it a message |
| `WALLET_PRIVATE_KEY` | MetaMask → Account Details → Export Private Key (testnet wallet only!) |
| `RPC_URL` | Use `https://data-seed-prebsc-1-s1.binance.org:8545/` or any BSC Testnet RPC |

> **Important:** `WALLET_PRIVATE_KEY` must be a **testnet-only** wallet with no real funds.

### Step 3 — Verify the workflow is enabled

Go to the **Actions** tab in your repo. If Actions are disabled, click **Enable** to turn them on.
The workflow (`DCA Agent — Monthly Buy`) will appear in the list.

---

## How to Trigger a Manual Run

1. Go to your repo → **Actions** tab
2. Click **DCA Agent — Monthly Buy** in the left sidebar
3. Click **Run workflow** (top right)
4. Choose:
   - **dry_run = false** — real run (executes the swap if guardrails pass)
   - **dry_run = true** — simulation (logs what would happen, no swap)
5. Click the green **Run workflow** button

You'll receive a Telegram message with the result within ~2 minutes.

---

## How to Change the Schedule

Edit `.github/workflows/dca-monthly.yml`, line with `cron:`:

```yaml
- cron: '0 12 1 * *'   # 1st of every month at 12:00 UTC (current)
```

Cron format: `minute hour day-of-month month day-of-week`

| Example schedule | Cron expression |
|---|---|
| 1st of every month, noon UTC | `0 12 1 * *` |
| Every Monday at 09:00 UTC | `0 9 * * 1` |
| Every day at 08:00 UTC | `0 8 * * *` |
| 1st and 15th of every month | `0 12 1,15 * *` |

Use [crontab.guru](https://crontab.guru) to preview any cron expression.

---

## Local Development

### Quick start

```bash
cd dca-agent
cp .env.example .env     # fill in your testnet credentials
pip install -r requirements.txt

# Simulate a run (no swap, no Telegram)
python dca_agent.py --dry-run

# Real run
python dca_agent.py
```

### Get testnet BNB

```
https://testnet.bnbchain.org/faucet-smart
```

---

## How the AI Guardrails Work

Before every scheduled buy, the agent runs three checks and sends the data to Groq:

```
Guardrail 1 — Gas Price
  → Fetch current gas via eth_gasPrice
  → Skip if > GAS_THRESHOLD_GWEI (default: 20 Gwei)

Guardrail 2 — Price Stability
  → Compares current price to history (single-run: assumes stable)
  → Skip if moved > PRICE_CHANGE_THRESHOLD (default: ±5%)

Guardrail 3 — Liquidity
  → Fetch BNB reserves from the PancakeSwap pair
  → Skip if < MIN_LIQUIDITY_BNB (default: 1.0 BNB)
```

Groq reviews all three results and writes a plain-language explanation.
If all pass → swap executes. If any fail → cycle is skipped and you receive an alert.

---

## BSC Testnet Addresses

| Contract | Address |
|---|---|
| PancakeSwap Router | `0xD99D1c33F9fC3444f8101754aBC46c52416550D1` |
| PancakeSwap Factory | `0x6725F303b657a9451d8BA641348b6761A6CC7a17` |
| WBNB | `0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd` |
| BUSD (testnet) | `0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee` |
| USDT (testnet) | `0x337610d27c682E347C9cD60BD4b3b107C9d34dDd` |
| RPC | `https://data-seed-prebsc-1-s1.binance.org:8545/` |
| Chain ID | `97` |

---

## Security Notes

- **Never** use a mainnet wallet or real funds with this agent.
- **Never** commit `.env` to Git — it's already in `.gitignore`.
- All secrets are injected at runtime by GitHub Actions — they are never stored in the repo.

---

## Verify Transactions on BscScan

Every successful swap links directly to:

```
https://testnet.bscscan.com/tx/<tx_hash>
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Workflow not running | Check Actions tab is enabled; verify cron syntax at crontab.guru |
| `Cannot connect to BSC Testnet` | Try a different RPC from [chainlist.org](https://chainlist.org/?search=bnb&testnets=true) |
| `Swap reverted` | Wallet may have insufficient tBNB — get more from the faucet |
| Telegram not receiving messages | Verify `TELEGRAM_BOT_TOKEN` secret and that you've started a chat with the bot |
| `Groq API error` | Check `GROQ_API_KEY` secret; fallback logic applies all guardrails manually |
