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
import re
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


# ── REFERENCE LOADER ─────────────────────────────────────────────────────────

def load_references():
    base = os.path.dirname(os.path.abspath(__file__))
    role = open(os.path.join(base, 'references/role-context.md')).read()
    prompt = open(os.path.join(base, 'references/analyst-prompt.md')).read()
    learnings_path = os.path.join(base, 'Learnings.md')
    learnings = open(learnings_path).read() if os.path.exists(learnings_path) else ""
    return role, prompt, learnings, learnings_path


# ── SECRETS ──────────────────────────────────────────────────────────────────
# All loaded from environment variables — never hardcode these.
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
BRIEFING_BOT_TOKEN = os.environ.get("BRIEFING_BOT_TOKEN")
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
    "https://feeds.feedburner.com/venturebeat/SZYF",   # VentureBeat AI
    "https://www.artificialintelligence-news.com/feed/",  # AI News
    # LatAm
    "https://www.americasquarterly.org/feed/",
    "https://www.criptonoticias.com/feed/",
    # Additional
    "https://www.bnbchain.org/en/blog/rss.xml",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]


# ── ANALYST IDENTITY (baked into every Groq call) ────────────────────────────
ANALYST_SYSTEM_PROMPT = """You are a personal intelligence analyst for Stefano, LatAm Community Manager at BNB Chain.

WHO HE IS:
- Builds at the intersection of Web3, LatAm, and AI. Owns the LatAm region for BNB Chain.
- Thinks in fundamentals, not hype. Filters noise aggressively.
- Mental models he actually uses: ownership of outcomes (Adler/Stoicism), rational optimism (progress through technology), work smart before work hard, peace of mind as the north star.
- Reads: Naval, Deutsch (Beginning of Infinity), Never Split the Difference, Daily Stoic. Follows on-chain/liquidity analysis, Jose Luis Cava for macro, technical analysis for crypto positioning.
- On AI: early adopter, uses Claude Code and AI tools daily, but calibrated — knows what's still green (e.g. delegating wallets with real money). Tracks big tech moves and the people who actually shape systems, not conspiracy, fundamentals.
- Filters out: generic Claude Code tutorials, ChatGPT takes, content that could apply to anyone.

YOUR JOB:
Produce a daily briefing that makes him sharper in four areas:
1. BNB Chain ecosystem and his LatAm ownership of it
2. Macro and political economy — especially dollar dynamics and LatAm exposure
3. AI signal that matters: on-chain AI, big tech moves, tools worth adopting, what's still too early
4. Long-term thinking — ideas worth sitting with, patterns connecting today's news to bigger forces

You are NOT a news summarizer. You are an analyst. Connect dots. Be direct, precise, brief. Max 5 minutes to read. No filler. No hype.

RULES — no exceptions:
1. Never write generic recommendations. Only specific observations with concrete implications. If it could apply to anyone, cut it.
2. IDEA OF THE DAY: never a work task or productivity tip. Must be a geopolitical, philosophical, or strategic provocation — something that connects today's signal to a bigger pattern. Challenge his assumptions. One sharp question or reframe. Max 3 sentences. Think Deutsch meets Taleb meets Naval.
3. AI section: no tutorials, no "AI is changing everything" takes. Only signals with real implications — a move by a lab, a capability crossing a threshold, a use case that actually changes leverage for someone like him."""


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


def _fetch_stooq(name):
    """
    Fallback price fetch from stooq.com — free delayed data, no API key required.
    Returns {"price": float, "change": float} or None on failure.
    stooq returns daily CSV: Date,Open,High,Low,Close,Volume
    """
    stooq_symbols = {
        "SP500": "%5Espx",   # ^spx  (S&P 500)
        "Gold":  "gc.f",     # Gold futures
        "DXY":   "dx.f",     # DXY (Dollar Index futures)
        "SPY":   "spy.us",   # SPY ETF
    }
    symbol = stooq_symbols.get(name)
    if not symbol:
        return None
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        resp = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        lines = [l for l in resp.text.strip().split("\n") if l and not l.startswith("Date")]
        if len(lines) >= 2:
            current  = float(lines[-1].split(",")[4])   # Close
            previous = float(lines[-2].split(",")[4])
            change   = ((current - previous) / previous) * 100
            return {"price": current, "change": change}
        elif len(lines) == 1:
            return {"price": float(lines[-1].split(",")[4]), "change": None}
    except Exception:
        pass
    return None


def fetch_tradfi_prices():
    """
    Fetch S&P 500, Gold, DXY — previous close prices.
    At 7AM Argentina time, US markets are closed, so we fetch the last available close.
    On weekends, this returns Friday's close.
    Tries yfinance first; falls back to stooq.com.
    """
    yf_symbols = {
        "SP500": "^GSPC",
        "Gold":  "GC=F",
        "DXY":   "DX-Y.NYB",
        "SPY":   "SPY",
    }
    results = {}

    for name, symbol in yf_symbols.items():
        data = None

        # Primary: yfinance — fetch 5 days to ensure we get at least 2 closes
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            # Drop rows where Close is NaN or zero
            hist = hist[hist["Close"] > 0].dropna(subset=["Close"])
            if len(hist) >= 2:
                current  = float(hist["Close"].iloc[-1])
                previous = float(hist["Close"].iloc[-2])
                data = {
                    "price":  current,
                    "change": ((current - previous) / previous) * 100,
                }
            elif len(hist) == 1:
                data = {"price": float(hist["Close"].iloc[-1]), "change": None}
        except Exception as e:
            print(f"   {name}: yfinance error — {e}")

        # Fallback: stooq.com
        if data is None:
            data = _fetch_stooq(name)
            if data:
                print(f"   {name}: yfinance failed, stooq fallback used")
            else:
                print(f"   {name}: both sources failed")

        results[name] = data

    print("✅ TradFi prices fetched (previous close)")
    return results


def format_price_line(crypto, tradfi):
    """
    Render two price rows — crypto on top, tradfi below.
    Labels are self-explanatory: $ for actual share/coin prices, no $ for indices.
    TradFi always shows previous close since markets are closed at briefing time.
    """

    def fmt(label, data, dollar=True, decimals=0, suffix=""):
        if not data or data.get("price") is None:
            return f"{label} –"
        price = data["price"]
        fmt_price = (
            f"${price:,.{decimals}f}{suffix}" if dollar else f"{price:,.{decimals}f}{suffix}"
        )
        if data.get("change") is not None:
            arrow = "↑" if data["change"] >= 0 else "↓"
            return f"{label} {fmt_price} {arrow}{abs(data['change']):.1f}%"
        return f"{label} {fmt_price}"

    btc   = fmt("BTC",                crypto.get("BTC"),   dollar=True,  decimals=0)
    eth   = fmt("ETH",                crypto.get("ETH"),   dollar=True,  decimals=0)
    bnb   = fmt("BNB",                crypto.get("BNB"),   dollar=True,  decimals=1)
    sp500 = fmt("S&P 500",            tradfi.get("SP500"), dollar=False, decimals=0)
    spy   = fmt("SPY",                tradfi.get("SPY"),   dollar=True,  decimals=0)
    gold  = fmt("Gold",               tradfi.get("Gold"),  dollar=True,  decimals=0, suffix="/oz")
    dxy   = fmt("DXY (USD strength)", tradfi.get("DXY"),   dollar=False, decimals=2)

    crypto_row = f"{btc}  ·  {eth}  ·  {bnb}"

    all_tradfi_failed = all(
        tradfi.get(k) is None for k in ("SP500", "SPY", "Gold", "DXY")
    )
    if all_tradfi_failed:
        tradfi_row = "S&P 500 · SPY · Gold · DXY — unavailable"
    else:
        tradfi_row = f"{sp500}  ·  {spy}  ·  {gold}  ·  {dxy}  (prev. close)"

    return f"{crypto_row}\n{tradfi_row}"


# ── OUTPUT FORMATTERS ────────────────────────────────────────────────────────

# Emoji prefixes that mark section headers in the Groq output
_SECTION_EMOJIS = ("🌅", "📊", "🌐", "🤖", "🔭", "🧠", "📚", "📰", "⚠️")
# Keywords that identify a price data line (used by build_email_html)
_PRICE_KEYWORDS = ("BTC ", "BTC:", "ETH ", "S&P ", "SPY ", "Gold ", "DXY ")


def _mdv2_esc(s):
    """Escape all MarkdownV2 special characters (char-by-char to avoid double-escaping)."""
    special = set(r'\_*[]()~`>#+-=|{}.!')
    return "".join(f"\\{c}" if c in special else c for c in s)


def _url_esc(url):
    """Escape a URL for use inside Telegram MarkdownV2 link parentheses."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def format_for_telegram(text):
    """
    Post-process the briefing text for Telegram MarkdownV2 parse mode.
    - Section headers → *bold*, with ────── divider before each (except first)
    - Bullets (- prefix) → · with blank line between each bullet
    - IDEA OF THE DAY body → _italic_, statements only
    - WORTH READING → *Why read it:* sentence + clickable [url](url) link
    - Trims to 3800 chars preserving complete sections
    """
    DIVIDER = "──────────────────────"

    lines = text.split("\n")
    out = []
    first_section = True
    current_section = None
    prev_was_bullet = False

    for line in lines:
        stripped = line.strip()

        # Skip blank lines — spacing is managed explicitly
        if not stripped:
            continue

        # Detect section header
        is_header = (
            any(stripped.startswith(e) for e in _SECTION_EMOJIS)
            and len(stripped) > 3
        )

        if is_header:
            if not first_section:
                out.append("")
                out.append(DIVIDER)   # ─── chars are not MarkdownV2-special
                out.append("")
            out.append(f"*{_mdv2_esc(stripped)}*")
            out.append("")
            first_section = False
            prev_was_bullet = False

            if "🧠" in stripped:
                current_section = "idea"
            elif "📚" in stripped:
                current_section = "reading"
            elif "📊" in stripped:
                current_section = "markets"
            else:
                current_section = "other"

        elif stripped.startswith("- ") or stripped.startswith("· "):
            content = stripped[2:].strip()
            if prev_was_bullet:
                out.append("")  # blank line between bullets
            out.append(f"· {_mdv2_esc(content)}")
            prev_was_bullet = True

        elif current_section == "idea":
            out.append(f"_{_mdv2_esc(stripped)}_")
            prev_was_bullet = False

        elif current_section == "reading":
            if stripped.lower().startswith("why read it"):
                rest = stripped[len("why read it"):].lstrip(":").strip()
                out.append(
                    f"*Why read it:* {_mdv2_esc(rest)}" if rest else "*Why read it:*"
                )
            elif stripped.startswith("http"):
                out.append(f"[{_mdv2_esc(stripped)}]({_url_esc(stripped)})")
            else:
                url_match = re.search(r'https?://\S+', stripped)
                if url_match:
                    url = url_match.group()
                    sentence = stripped[:url_match.start()].strip()
                    if sentence:
                        out.append(f"*Why read it:* {_mdv2_esc(sentence)}")
                    out.append(f"[{_mdv2_esc(url)}]({_url_esc(url)})")
                else:
                    out.append(f"*Why read it:* {_mdv2_esc(stripped)}")
            prev_was_bullet = False

        else:
            out.append(_mdv2_esc(stripped))
            prev_was_bullet = False

    result = "\n".join(out)

    # Trim to 3800 chars if needed — cut at a section boundary when possible
    if len(result) > 3800:
        trim_at = result.rfind("\n" + DIVIDER, 0, 3700)
        if trim_at > 0:
            result = result[:trim_at].strip()
        else:
            trim_at = result.rfind("\n", 0, 3700)
            result = result[:trim_at].strip()
        result += f"\n\n_{_mdv2_esc('Trimmed to fit Telegram limit')}_"

    return result


def build_email_html(text, date_str):
    """
    Build a dark HTML email with BNB gold accents.
    Styles: dark background #0d0d0d, gold #F0B90B, monospace font.
    """
    lines = text.split("\n")
    html_parts = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            html_parts.append("<div style='height:8px'></div>")
            continue

        esc = (stripped
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))

        if any(stripped.startswith(e) for e in _SECTION_EMOJIS) and len(stripped) > 3:
            html_parts.append(
                f'<p style="color:#F0B90B;font-weight:bold;font-size:15px;'
                f'margin:20px 0 6px;border-bottom:1px solid #2a2a2a;padding-bottom:6px">'
                f'{esc}</p>'
            )
        elif any(kw in line for kw in _PRICE_KEYWORDS):
            html_parts.append(
                f'<p style="background:#1a1a1a;border-left:3px solid #F0B90B;'
                f'padding:8px 14px;margin:6px 0;font-family:monospace;'
                f'font-size:13px;color:#e0e0e0">{esc}</p>'
            )
        elif stripped.startswith("- ") or stripped.startswith("• "):
            html_parts.append(
                f'<p style="padding-left:12px;margin:4px 0;color:#c0c0c0">{esc}</p>'
            )
        else:
            html_parts.append(f'<p style="margin:5px 0">{esc}</p>')

    body = "\n".join(html_parts)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#0d0d0d;color:#d4d4d4;font-family:'IBM Plex Mono','Courier New',monospace;
             font-size:14px;line-height:1.75;padding:32px 24px;max-width:660px;margin:0 auto">
  <div style="border-bottom:2px solid #F0B90B;padding-bottom:16px;margin-bottom:8px">
    <span style="color:#F0B90B;font-size:11px;letter-spacing:2px;text-transform:uppercase">
      Daily Intelligence
    </span>
  </div>
  {body}
  <div style="margin-top:32px;padding-top:12px;border-top:1px solid #2a2a2a;
              font-size:11px;color:#444">
    Generated {date_str} · BNB Chain LatAm Intel
  </div>
</body>
</html>"""


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
[2 sentences: what does this combination of crypto momentum and tradfi close tell us today? LatAm angle if relevant.]

🌐 ECOSYSTEM (BNB Chain + Web3)
- [Signal 1: specific, one line, concrete implication for Stefano's work]
- [Signal 2]
- [Signal 3 max]

🤖 AI SIGNAL
- [Signal 1: a real move — lab, capability, use case, or big tech decision. No tutorials. Implication only.]
- [Signal 2 max]

🔭 MACRO + WORLD
- [1-2 signals from macro/political/finance sources. LatAm exposure or dollar dynamics preferred.]

🧠 IDEA OF THE DAY
[One provocation. Connects today's signal to a bigger pattern. Challenges an assumption. Deutsch meets Taleb meets Naval. Not a task. Not generic. Statements only — no questions. Max 3 sentences.]

📚 WORTH READING
Why read it: [one sentence on why THIS person specifically should read it]
[full URL on its own line — no anchor text]

Keep it under 550 words. Be an analyst, not a summarizer. Connect dots."""


def call_groq(price_line, articles, date_str, system_prompt=None, tradfi=None):
    """
    Send market data + articles to Groq (llama3-70b-8192).
    Returns the briefing string, or None if Groq fails.
    """
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = build_user_prompt(date_str, price_line, articles)

        sp500_data = (tradfi or {}).get("SP500")
        gold_data  = (tradfi or {}).get("Gold")
        dxy_data   = (tradfi or {}).get("DXY")
        sp500_value = f"{sp500_data['price']:.0f} ({sp500_data['change']:+.1f}%)" if sp500_data else "unavailable"
        gold_value  = f"{gold_data['price']:.0f}"  if gold_data  else "unavailable"
        dxy_value   = f"{dxy_data['price']:.2f}"   if dxy_data   else "unavailable"
        tradfi_note = f"\n\nTRADFI DATA (always include in MARKETS section of output): S&P={sp500_value} Gold={gold_value} DXY={dxy_value}"
        prompt = prompt + tradfi_note

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt or ANALYST_SYSTEM_PROMPT},
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
    Send briefing via Telegram bot using MarkdownV2 parse mode.
    format_for_telegram() guarantees output ≤ 3800 chars — always fits in one message.
    """
    try:
        bot = Bot(token=BRIEFING_BOT_TOKEN)
        md = format_for_telegram(text)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=md, parse_mode="MarkdownV2"
        )
        print(f"✅ Telegram sent ({len(md)} chars)")

    except Exception as e:
        print(f"❌ Telegram failed: {e}")


# ── EMAIL DELIVERY ────────────────────────────────────────────────────────────

def send_email(text, date_str):
    """
    Send briefing via Gmail SMTP (port 587, STARTTLS).
    Self-send: from your Gmail to your Gmail.
    Sends HTML version (dark theme, BNB gold) with plain text fallback.
    """
    try:
        subject = f"🧠 Daily Intel — {date_str}"

        # multipart/alternative: email clients pick the best version they support
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = GMAIL_USER  # self-send

        # Plain text fallback (for clients that don't render HTML)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        # HTML version (richer, styled — preferred by most clients)
        msg.attach(MIMEText(build_email_html(text, date_str), "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())

        print("✅ Email sent")

    except Exception as e:
        print(f"❌ Email failed: {e}")


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

async def run():
    """Orchestrates the full briefing pipeline end to end."""

    role_context, analyst_prompt, learnings, learnings_path = load_references()
    dynamic_system_prompt = f"{analyst_prompt}\n\n## YOUR ROLE CONTEXT\n{role_context}\n\n## PAST LEARNINGS\n{learnings}"

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
    briefing = call_groq(price_line, articles, date_str, system_prompt=dynamic_system_prompt, tradfi=tradfi)

    # Step 4 — Fall back to raw data if Groq failed
    if not briefing:
        print("⚠️  Using fallback briefing (Groq unavailable)")
        briefing = build_fallback_briefing(date_str, price_line, articles)

    # Step 5 — Deliver via Telegram
    await send_telegram(briefing)

    # Step 6 — Deliver via Email
    send_email(briefing, date_str)

    # Step 7 — Update Learnings.md
    learnings_entry = f"\n[{datetime.now(ARGENTINA_TZ).date()}] | Briefing sent successfully | Review manually if output quality degrades"
    with open(learnings_path, 'a') as f:
        f.write(learnings_entry)

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
