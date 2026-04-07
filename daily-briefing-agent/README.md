# Daily Intelligence Briefing Agent

Every day at **7:00 AM Argentina time**, this agent:
1. Fetches prices: BTC, ETH, BNB (CoinGecko), S&P 500, Gold, DXY (Yahoo Finance)
2. Scrapes the latest articles from 10 curated RSS feeds
3. Sends everything to Groq (LLaMA 3 70B) with a custom analyst prompt
4. Delivers one formatted briefing to your **Telegram** and your **Gmail**

---

## Environment Variables Required

Add these as **GitHub Secrets** (for the cron job) AND export them locally (for testing):

| Variable | What it is |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (console.groq.com) |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | Your personal Telegram chat ID (see below) |
| `GMAIL_USER` | Your full Gmail address (e.g. you@gmail.com) |
| `GMAIL_APP_PASSWORD` | Your Gmail App Password — NOT your login password (see below) |

---

## How to Add GitHub Secrets

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each variable from the table above

---

## How to Get Your Gmail App Password (3 steps)

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security) and make sure **2-Step Verification is ON**
2. Search for **"App passwords"** in the Google Account search bar → click it
3. Select app: **Mail**, device: **Other** (type "Daily Briefing") → click **Generate**
   - Copy the 16-character password shown → this is your `GMAIL_APP_PASSWORD`
   - You only see it once, save it immediately

---

## How to Find Your Telegram Chat ID

1. Start a chat with **@userinfobot** on Telegram
2. Send it any message (e.g. `/start`)
3. It replies with your ID — that number is your `TELEGRAM_CHAT_ID`

---

## How to Test Right Now (from terminal)

```bash
# 1. Go to the project folder
cd daily-briefing-agent

# 2. Export your secrets (replace values with real ones)
export GROQ_API_KEY="your_groq_key"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="your_app_password"

# 3. Install dependencies
pip install -r requirements.txt

# 4. Fire the briefing immediately
python briefing_agent.py --test
```

You should see logs like:
```
🚀 Daily Intelligence Briefing — Tuesday, April 07 2026
============================================================
✅ Crypto prices fetched
✅ TradFi prices fetched
✅ 14 articles found
✅ Groq response received
✅ Telegram sent
✅ Email sent
============================================================
✅ Briefing complete
```

---

## RSS Sources

| Category | Feed |
|---|---|
| Web3/Crypto | The Block, Bankless, DL News, BNB Chain Blog |
| Macro | Axios Markets, The Economist |
| Tech/AI | Benedict Evans, Import AI (Jack Clark) |
| LatAm | Americas Quarterly, Criptonoticias |

---

## Failsafe Behavior

- If any RSS feed fails → silently skipped, briefing continues
- If Groq fails → fallback briefing sent with raw prices + top 3 headlines
- If Telegram fails → logged, email still attempted
- If email fails → logged, Telegram still attempted
- Missing env variables → script exits immediately with clear error message
