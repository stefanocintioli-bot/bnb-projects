# BNB Chain DCA Agent

An AI-powered Dollar-Cost-Averaging bot for BNB Chain **testnet**. Before every buy, a Groq LLM checks three on-chain guardrails and sends you a Telegram alert — whether the trade executes or gets skipped.

---

## What It Does

| Feature | Detail |
|---|---|
| **DCA cadence** | Daily or weekly automated buys |
| **AI guardrails** | Gas price · Price stability · Pool liquidity |
| **AI model** | Groq `llama3-8b-8192` (free tier) |
| **DEX** | PancakeSwap testnet |
| **Alerts** | Telegram bot with plain-language explanations |
| **Network** | BSC Testnet — no real money |

---

## Files

```
dca-agent/
├── dca_agent.py      ← Main bot logic (Web3 + Groq + Telegram)
├── dca_ui.html       ← Web UI to configure & generate .env
├── requirements.txt  ← Python dependencies
├── .env.example      ← Template for environment variables
└── README.md         ← This file
```

---

## Quick Start

### Step 1 — Prerequisites

- Python 3.10+
- MetaMask with a **testnet-only** wallet
- Free accounts: [Groq](https://console.groq.com) · [Telegram @BotFather](https://t.me/BotFather)

### Step 2 — Get testnet BNB

Visit the faucet and request free tBNB for your wallet:

```
https://testnet.bnbchain.org/faucet-smart
```

Make sure MetaMask is on **BSC Testnet** (Chain ID: 97).

### Step 3 — Configure with the Web UI

Open `dca_ui.html` in your browser. Fill in:

- Groq API key
- Telegram bot token + your chat ID
- Wallet private key (testnet only)
- DCA amount, frequency, and guardrail thresholds

Click **Download .env** — place the file in this folder as `.env`.

### Step 4 — Install dependencies

```bash
cd dca-agent
pip install -r requirements.txt
```

> Using a virtual environment is recommended:
> ```bash
> python -m venv .venv
> source .venv/bin/activate   # macOS/Linux
> .venv\Scripts\activate      # Windows
> pip install -r requirements.txt
> ```

### Step 5 — Run the agent

```bash
python dca_agent.py
```

The agent will:
1. Connect to BSC Testnet
2. Start the Telegram bot
3. Run a price tracker every 60 seconds
4. Execute your first DCA cycle 30 seconds after startup

---

## Telegram Commands

| Command | Description |
|---|---|
| `/status` | Current agent state, wallet balance, live guardrail readings |
| `/pause` | Pause the agent (cycles are skipped until resumed) |
| `/resume` | Resume the agent |
| `/history` | Last 5 cycle results with AI explanations |
| `/runnow` | Trigger a DCA cycle immediately |

---

## How the AI Guardrails Work

Before every scheduled buy, the agent runs three checks and sends the data to Groq:

```
Guardrail 1 — Gas Price
  → Fetch current gas via eth_gasPrice
  → Skip if > GAS_THRESHOLD_GWEI (default: 20 Gwei)

Guardrail 2 — Price Stability
  → Compare current PancakeSwap price vs 1 hour ago
  → Skip if moved > PRICE_CHANGE_THRESHOLD (default: ±5%)

Guardrail 3 — Liquidity
  → Fetch BNB reserves from the PancakeSwap pair
  → Skip if < MIN_LIQUIDITY_BNB (default: 1.0 BNB)
```

Groq `llama3-8b-8192` reviews all three results and writes a plain-language explanation. If all pass → swap executes. If any fail → cycle is skipped and you receive an alert.

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
- The web UI runs 100% in your browser — keys are written only to the local `.env` file you download.

---

## Verify on BscScan

Every successful swap links directly to:

```
https://testnet.bscscan.com/tx/<tx_hash>
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot connect to BSC Testnet` | Check your internet connection; try a different RPC from [chainlist.org](https://chainlist.org/?search=bnb&testnets=true) |
| `Swap reverted` | Your wallet may have insufficient tBNB — get more from the faucet |
| Telegram bot not responding | Verify `TELEGRAM_BOT_TOKEN` and that you've started a chat with the bot |
| `Groq API error` | Check your `GROQ_API_KEY`; the fallback logic applies all guardrails manually |
| Price stability always failing | Not enough price history yet — wait a few minutes after startup |
