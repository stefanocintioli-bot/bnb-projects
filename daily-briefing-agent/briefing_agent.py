#!/usr/bin/env python3
"""
Daily Intelligence Briefing Agent
-----------------------------------
Fetches prices (BTC, ETH, BNB, S&P, Gold, DXY), scrapes RSS feeds,
sends everything to Groq (LLaMA 3) for analyst-style synthesis,
then delivers the result via Telegram bot AND Gmail.

Run with:  python briefing_agent.py          ← scheduled mode
           python briefing_agent.py --test   ← fires immediately for testing
"""

import os
import sys
import asyncio
import argparse
import smtplib
import calendar
import feedparser
import requests
import yfinance as yf

from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import Groq
from telegram import Bot


# ── SECRETS ──────────────────────────────────────────────────────────────────
# All loaded from environment variables — never hardcode these.
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("BRIEFING_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")
GMAIL_USER         = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Argentina is UTC-3 (no daylight saving)
ARGENTINA_TZ = timezone(timedelta(hours=-3))


# ── RSS SOURCE LIST ───────────────────────────────────────────────────────────
RSS_SOURCES = [
    # Web3 + Crypto
    "https://www.theblock.co/rss.xml",
    "https://banklesshq.com/rss",
    "https://dlnews.com/arc/outbound/rss/",
    "https://www.bnbchain.org/en/blog/rss/",
    # Macro + Finance
    "https://api.axios.com/feed/markets",
    "https://www.economist.com/finance-and-economics/rss.xml",
    # Technology + AI
    "https://www.ben-evans.com/benedictevans/rss.xml",
    "https://jack-clark.net/feed/",
    # LatAm
    "https://www.americasquarterly.org/feed/",
    "https://www.criptonoticias.com/feed/",
]


# ── ANALYST IDENTITY (baked into every Groq call) ────────────────────────────
ANALYST_SYSTEM_PROMPT = """You are a personal intelligence analyst for Stefano, LatAm Community Manager at BNB Chain.
Your job is to produce a daily briefing that makes him sharper in three areas:
1. His ecosystem work (BNB Chain, Web3, LatAm crypto)
2. His macro understanding (global markets, political economy, dollar dynamics in LatAm)
3. His long-term thinking (technology trends, AI, ideas worth sitting with)

You are NOT a news summarizer. You are an analyst. Connect dots. Flag what's relevant to LatAm specifically.
Be direct, precise, and brief. Max 5 minutes to read. No filler. No hype."""


# ── PRICE FETCHING ────────────────────────────────────────────────────────────

def fetch_crypto_prices():
    """
    Fetch BTC, ETH, BNB prices + 24h change from CoinGecko.
    No API key required. Returns dict or gracefully returns None per asset.
    """
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum,binancecoin",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        prices = {
            "BTC": {
                "price": data["bitcoin"]["usd"],
                "change": data["bitcoin"].get("usd_24h_change"),
            },
            "ETH": {
                "price": data["ethereum"]["usd"],
                "change": data["ethereum"].get("usd_24h_change"),
            },
            "BNB": {
                "price": data["binancecoin"]["usd"],
                "change": data["binancecoin"].get("usd_24h_change"),
            },
        }
        print("✅ Crypto prices fetched")
        return prices

    except Exception as e:
        print(f"⚠️  Crypto prices failed: {e}")
        return {"BTC": None, "ETH": None, "BNB": None}


def fetch_tradfi_prices():
    """
    Fetch S&P 500, Gold, DXY from Yahoo Finance via yfinance.
    Uses 2-day history to compute 24h change %.
    Returns dict with price + change, or None if the ticker fails.
    """
    tickers = {
        "SP500": "^GSPC",
        "Gold":  "GC=F",
        "DXY":   "DX-Y.NYB",
    }
    results = {}

    for name, symbol in tickers.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")  # 5d to handle weekends/holidays

            if len(hist) >= 2:
                current  = hist["Close"].iloc[-1]
                previous = hist["Close"].iloc[-2]
                change   = ((current - previous) / previous) * 100
                results[name] = {"price": float(current), "change": float(change)}
            elif len(hist) == 1:
                results[name] = {"price": float(hist["Close"].iloc[-1]), "change": None}
            else:
                results[name] = None

        except Exception as e:
            print(f"⚠️  {name} ({symbol}) failed: {e}")
            results[name] = None

    print("✅ TradFi prices fetched")
    return results


def format_price_line(crypto, tradfi):
    """
    Render a single compact price line for the briefing header.
    Example: BTC: $83,200 (+1.2%) | ETH: $1,580 | BNB: $590 | S&P: 5,200 | Gold: $3,100 | DXY: 103.4
    """

    def fmt(label, data, dollar=True, decimals=0):
        if not data or data.get("price") is None:
            return f"{label}: N/A"
        price = data["price"]
        fmt_price = (
            f"${price:,.{decimals}f}" if dollar else f"{price:,.{decimals}f}"
        )
        if data.get("change") is not None:
            return f"{label}: {fmt_price} ({data['change']:+.1f}%)"
        return f"{label}: {fmt_price}"

    btc   = fmt("BTC",   crypto.get("BTC"),  dollar=True,  decimals=0)
    eth   = fmt("ETH",   crypto.get("ETH"),  dollar=True,  decimals=0)
    bnb   = fmt("BNB",   crypto.get("BNB"),  dollar=True,  decimals=1)
    sp500 = fmt("S&P",   tradfi.get("SP500"), dollar=False, decimals=0)
    gold  = fmt("Gold",  tradfi.get("Gold"),  dollar=True,  decimals=0)
    dxy   = fmt("DXY",   tradfi.get("DXY"),   dollar=False, decimals=2)

    return f"{btc} | {eth} | {bnb} | {sp500} | {gold} | {dxy}"


# ── RSS FEED SCRAPING ─────────────────────────────────────────────────────────

def fetch_rss_articles():
    """
    Fetch up to 3 articles per source published in the last 24 hours.
    Silently skips any feed that times out or errors — never crashes the run.
    Returns a flat list of article dicts.
    """
    all_articles = []
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    for url in RSS_SOURCES:
        try:
            # Fetch raw bytes via requests (supports timeout), then parse
            resp = requests.get(
                url,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DailyBriefingBot/1.0)"},
            )
            feed = feedparser.parse(resp.content)

            count = 0
            for entry in feed.entries:
                if count >= 3:
                    break

                # Parse publish date if available
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    # calendar.timegm treats the struct as UTC (correct for RSS)
                    ts = calendar.timegm(entry.published_parsed)
                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc)

                # Skip if older than 24h (only when date is known)
                if pub_date and pub_date < cutoff:
                    continue

                all_articles.append({
                    "title":   entry.get("title", "No title").strip(),
                    "link":    entry.get("link", ""),
                    "summary": entry.get("summary", "")[:300].strip(),
                    "source":  feed.feed.get("title", url),
                    "date":    pub_date.strftime("%Y-%m-%d") if pub_date else "unknown",
                })
                count += 1

        except Exception as e:
            # Silent skip — one dead feed should never kill the whole briefing
            print(f"⚠️  Feed skipped ({url[:50]}): {e}")
            continue

    print(f"✅ {len(all_articles)} articles found")
    return all_articles


# ── GROQ AI BRIEFING ──────────────────────────────────────────────────────────

def build_user_prompt(date_str, price_line, articles):
    """
    Assemble the full user message to send to Groq.
    Includes market data + article list, then specifies the exact output format.
    """
    # Format articles into a numbered list (cap at 15 to save tokens)
    articles_block = ""
    for i, art in enumerate(articles[:15], 1):
        articles_block += f"{i}. [{art['source']}] {art['title']}\n"
        if art["summary"]:
            articles_block += f"   {art['summary'][:200]}\n"
        if art["link"]:
            articles_block += f"   {art['link']}\n"
        articles_block += "\n"

    if not articles_block:
        articles_block = "No articles available today.\n"

    return f"""Today is {date_str}.

MARKET DATA:
{price_line}

TODAY'S ARTICLES ({len(articles)} found, showing top {min(15, len(articles))}):
{articles_block}
---
Produce the daily briefing in EXACTLY this format (no extra sections, no preamble):

🌅 Stefano's Daily Intelligence — {date_str}

📊 MARKETS
{price_line}
[2 sentences: what does this combination tell us today, especially for LatAm?]

🌐 ECOSYSTEM (BNB Chain + Web3)
- [Signal 1: one line, what it means for Stefano's work]
- [Signal 2]
- [Signal 3 max]

🔭 MACRO + WORLD
- [1-2 signals from macro/political/finance sources relevant to LatAm or Web3]

🧠 IDEA OF THE DAY
[One concept, trend, or question worth thinking about this week. Not news. A thinking prompt. Calibrated to someone building at the intersection of Web3, LatAm, and AI.]

📚 WORTH READING
[1 article link from the sources above, with one sentence on why THIS person should read it]

Keep it under 500 words. Be an analyst, not a summarizer. Connect dots."""


def call_groq(price_line, articles, date_str):
    """
    Send market data + articles to Groq (llama3-70b-8192).
    Returns the briefing string, or None if Groq fails.
    """
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = build_user_prompt(date_str, price_line, articles)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.7,
        )

        briefing = response.choices[0].message.content.strip()
        print("✅ Groq response received")
        return briefing

    except Exception as e:
        print(f"⚠️  Groq failed: {e}")
        return None


def build_fallback_briefing(date_str, price_line, articles):
    """
    Emergency fallback when Groq is unavailable.
    Sends raw price data + top 3 headlines so the day never starts blind.
    """
    headlines = "\n".join(
        f"• [{a['source']}] {a['title']}" for a in articles[:3]
    ) or "No headlines available."

    return (
        f"🌅 Stefano's Daily Intelligence — {date_str}\n"
        f"⚠️ [AI analysis unavailable — raw data only]\n\n"
        f"📊 MARKETS\n{price_line}\n\n"
        f"📰 TOP HEADLINES\n{headlines}"
    )


# ── TELEGRAM DELIVERY ─────────────────────────────────────────────────────────

async def send_telegram(text):
    """
    Send briefing via Telegram bot.
    Splits into 2 messages if the text exceeds Telegram's 4096-char limit.
    """
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)

        if len(text) > 4096:
            # Find the last newline before the 4096 limit for a clean split
            split_at = text.rfind("\n", 0, 4096)
            if split_at == -1:
                split_at = 4096

            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[:split_at])
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[split_at:].strip())
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

        print("✅ Telegram sent")

    except Exception as e:
        print(f"❌ Telegram failed: {e}")


# ── EMAIL DELIVERY ────────────────────────────────────────────────────────────

def send_email(text, date_str):
    """
    Send briefing via Gmail SMTP (port 587, STARTTLS).
    Self-send: from your Gmail to your Gmail.
    Requires a Gmail App Password — NOT your regular Gmail password.
    """
    try:
        subject = f"🧠 Daily Intel — {date_str}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = GMAIL_USER  # self-send

        # Attach plain text body
        msg.attach(MIMEText(text, "plain", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()   # Upgrade to TLS
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())

        print("✅ Email sent")

    except Exception as e:
        print(f"❌ Email failed: {e}")


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

async def run():
    """Orchestrates the full briefing pipeline end to end."""

    now_ar   = datetime.now(ARGENTINA_TZ)
    date_str = now_ar.strftime("%A, %B %d %Y")  # e.g. "Monday, April 07 2026"

    print(f"\n🚀 Daily Intelligence Briefing — {date_str}")
    print("=" * 60)

    # Step 1 — Fetch prices
    crypto = fetch_crypto_prices()
    tradfi = fetch_tradfi_prices()
    price_line = format_price_line(crypto, tradfi)
    print(f"   {price_line}")

    # Step 2 — Scrape RSS feeds
    articles = fetch_rss_articles()

    # Step 3 — Ask Groq for analyst synthesis
    briefing = call_groq(price_line, articles, date_str)

    # Step 4 — Fall back to raw data if Groq failed
    if not briefing:
        print("⚠️  Using fallback briefing (Groq unavailable)")
        briefing = build_fallback_briefing(date_str, price_line, articles)

    # Step 5 — Deliver via Telegram
    await send_telegram(briefing)

    # Step 6 — Deliver via Email
    send_email(briefing, date_str)

    print("=" * 60)
    print("✅ Briefing complete\n")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Intelligence Briefing Agent")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Fire immediately without waiting for scheduled time (use for local testing)",
    )
    args = parser.parse_args()

    # Validate that all required secrets are present before doing any work
    required = [
        "GROQ_API_KEY",
        "BRIEFING_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GMAIL_USER",
        "GMAIL_APP_PASSWORD",
    ]
    missing = [v for v in required if not os.environ.get(v)]

    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("   Export them in your shell or .env before running.")
        sys.exit(1)

    # Run the pipeline
    asyncio.run(run())
