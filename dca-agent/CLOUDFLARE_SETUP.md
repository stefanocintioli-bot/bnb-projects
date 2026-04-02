# Cloudflare Worker Setup Guide

This guide connects your Telegram bot to the Cloudflare Worker so you can use
`/status`, `/nextrun`, `/history`, and `/dryrun` commands in real time.

**Total cost: $0. No credit card required.**

---

## Overview

```
You → Telegram message → Cloudflare Worker → reads KV → replies instantly
                                           ↓
                                    triggers GitHub Actions (for /dryrun)

GitHub Actions → runs dca_agent.py → writes result to Cloudflare KV
```

---

## Step 1 — Create a Free Cloudflare Account

1. Go to [cloudflare.com](https://cloudflare.com) and click **Sign Up**
2. Enter your email and a password — no credit card needed
3. Verify your email address
4. You're in. Stay on the free plan.

---

## Step 2 — Install Wrangler (Cloudflare CLI)

You need Node.js 18+ installed. Then:

```bash
npm install -g wrangler
# or use without installing:
npx wrangler --version
```

Log in to your Cloudflare account:

```bash
npx wrangler login
```

A browser window will open. Authorise Wrangler. You only need to do this once.

---

## Step 3 — Create a KV Namespace

KV (Key-Value) is where the agent stores run history so the Worker can read it.

```bash
cd ~/bnb-projects/dca-agent
npx wrangler kv:namespace create "DCA_STORE"
```

This outputs something like:

```
{ binding = "DCA_STORE", id = "abc123def456..." }
```

**Copy the `id` value.** Open `wrangler.toml` and replace the placeholder:

```toml
[[kv_namespaces]]
binding = "DCA_KV"
id      = "abc123def456..."   ← paste your real ID here
```

---

## Step 4 — Get Your Cloudflare Account ID

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Click **Workers & Pages** in the left sidebar
3. Your **Account ID** is shown in the right panel

You'll need this for the GitHub secrets in Step 7.

---

## Step 5 — Create a GitHub PAT for /dryrun

The `/dryrun` command triggers a GitHub Actions workflow. For this, the Worker
needs a GitHub Personal Access Token with `workflow` permission.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Set a name: `dca-agent-worker`
4. Expiration: 1 year (or no expiration)
5. Check the **workflow** scope
6. Click **Generate token**
7. Copy the token — you won't see it again

---

## Step 6 — Set Worker Secrets

Run each command below. Wrangler will prompt you to paste the value:

```bash
cd ~/bnb-projects/dca-agent

# Your Telegram bot token (from @BotFather)
npx wrangler secret put TELEGRAM_BOT_TOKEN

# A random secret string — used to verify requests come from Telegram
# Generate one: openssl rand -hex 20
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET

# Your Telegram chat ID (from @userinfobot)
npx wrangler secret put ALLOWED_CHAT_ID

# GitHub PAT from Step 5
npx wrangler secret put GH_PAT

# Your GitHub repo in "owner/repo" format
# e.g. stefanocintioli-bot/bnb-projects
npx wrangler secret put GH_REPO

# The workflow filename
npx wrangler secret put GH_WORKFLOW_FILE
# → type: dca-monthly.yml

# The branch to dispatch on
npx wrangler secret put GH_BRANCH
# → type: main
```

---

## Step 7 — Deploy the Worker

```bash
cd ~/bnb-projects/dca-agent
npx wrangler deploy
```

You'll see output like:

```
✅ Successfully deployed to:
   https://dca-agent-bot.<your-subdomain>.workers.dev
```

**Copy the Worker URL** — you'll need it in the next step.

---

## Step 8 — Register the Telegram Webhook

This tells Telegram to send all messages to your Worker instead of waiting for
your bot to poll.

Replace the placeholders and run:

```bash
BOT_TOKEN="your_telegram_bot_token"
WORKER_URL="https://dca-agent-bot.YOUR_SUBDOMAIN.workers.dev"
WEBHOOK_SECRET="your_webhook_secret_from_step_6"

curl -s -X POST \
  "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=${WORKER_URL}" \
  -d "secret_token=${WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"message\"]"
```

Expected response:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

Verify the webhook is active:

```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

---

## Step 9 — Add Cloudflare Secrets to GitHub

These let the Python agent write run results to KV after each run.

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Add these three secrets:

| Secret name | Value |
|---|---|
| `CF_ACCOUNT_ID` | Your Cloudflare Account ID from Step 4 |
| `CF_KV_NAMESPACE_ID` | The KV namespace ID from Step 3 |
| `CF_KV_API_TOKEN` | A Cloudflare API token (see below) |

**Creating the `CF_KV_API_TOKEN`:**

1. Go to [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token**
3. Use the **Edit Cloudflare Workers** template
4. Under **Zone Resources**, select **All zones** (or leave default)
5. Click **Continue to summary** → **Create Token**
6. Copy the token — save it immediately, it's shown only once

---

## Step 10 — Test It

Send any of these commands in Telegram to your bot:

```
/status    → shows last run result
/nextrun   → countdown to next scheduled buy
/history   → last 5 runs
/dryrun    → triggers a simulated run via GitHub Actions
```

If `/status` returns "No runs recorded yet", trigger a dry run first:

```bash
# From your terminal, trigger the workflow manually:
gh workflow run dca-monthly.yml --field dry_run=true
```

After ~60 seconds, type `/status` again — it should show the result.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot doesn't respond to commands | Check webhook: `getWebhookInfo` — look for `last_error_message` |
| `403 Forbidden` in Worker logs | Webhook secret mismatch — re-run Step 8 with the correct `WEBHOOK_SECRET` |
| `/status` shows "No runs yet" | The agent hasn't run since KV was set up — trigger a dry run |
| `/dryrun` not triggering | Verify `GH_PAT` has `workflow` scope; check `GH_REPO` format is `owner/repo` |
| KV write errors in GitHub Actions | Check `CF_KV_API_TOKEN` has Write permission to Workers KV |
| Worker error 1101 | Your KV namespace ID in `wrangler.toml` doesn't match the one created in Step 3 |

---

## Free Tier Limits (Cloudflare)

| Resource | Free allowance | This project's usage |
|---|---|---|
| Worker requests | 100,000 / day | ~4 per month (commands) |
| KV reads | 100,000 / day | ~4 per month |
| KV writes | 1,000 / day | 2 per month (from GitHub Actions) |
| Worker CPU time | 10ms per request | ~1ms per command |

You will never come close to the limits.
