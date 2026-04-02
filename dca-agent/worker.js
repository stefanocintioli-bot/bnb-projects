/**
 * BNB Chain DCA Agent — Cloudflare Worker
 * ─────────────────────────────────────────
 * Receives Telegram webhook POST requests and handles 4 interactive commands:
 *   /status   → full agent dashboard from KV
 *   /nextrun  → countdown to next scheduled run
 *   /history  → last 5 runs from KV
 *   /dryrun   → triggers GitHub Actions workflow_dispatch with dry_run=true
 *
 * Required Worker secrets (set via: npx wrangler secret put <NAME>):
 *   TELEGRAM_BOT_TOKEN       — from @BotFather
 *   TELEGRAM_WEBHOOK_SECRET  — any random string (matches webhook registration)
 *   ALLOWED_CHAT_ID          — your Telegram chat ID (security gate)
 *   GH_PAT                   — GitHub PAT with 'workflow' scope
 *   GH_REPO                  — e.g. "youruser/bnb-projects"
 *   GH_WORKFLOW_FILE         — e.g. "dca-monthly.yml"
 *   GH_BRANCH                — e.g. "main"
 *
 * KV binding (set in wrangler.toml):
 *   DCA_KV
 */

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'POST') {
      return new Response('DCA Agent Worker — OK', { status: 200 });
    }

    // Validate Telegram webhook secret token to reject forged requests
    const incomingSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token');
    if (env.TELEGRAM_WEBHOOK_SECRET && incomingSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    // Respond immediately to Telegram (avoids the 5-second timeout).
    // The actual command handling runs in the background via ctx.waitUntil.
    ctx.waitUntil(handleUpdate(body, env));
    return new Response('OK', { status: 200 });
  },
};

// ─────────────────────────────────────────────────────────────
// Update dispatcher
// ─────────────────────────────────────────────────────────────
async function handleUpdate(body, env) {
  const message = body?.message;
  if (!message?.text) return;

  const chatId = String(message.chat.id);

  // Security: only respond to the authorised chat
  if (env.ALLOWED_CHAT_ID && chatId !== env.ALLOWED_CHAT_ID) {
    await sendTelegram(env, chatId, '⛔ Unauthorised.');
    return;
  }

  // Strip @botname suffix from commands (e.g. /status@mybot → /status)
  const cmd = message.text.trim().split(/\s+/)[0].toLowerCase().split('@')[0];

  let replyText;

  try {
    switch (cmd) {
      case '/status':
        replyText = await handleStatus(env);
        break;

      case '/nextrun':
        replyText = handleNextRun();
        break;

      case '/history':
        replyText = await handleHistory(env);
        break;

      case '/dryrun':
        await triggerDryRun(env);
        replyText = '🤖 Dry run triggered, check Telegram in ~60s';
        break;

      default:
        replyText =
          'Available commands:\n' +
          '/status — full agent dashboard\n' +
          '/nextrun — countdown to next run\n' +
          '/history — last 5 runs\n' +
          '/dryrun — simulate this month\'s buy';
    }
  } catch (err) {
    replyText = `❌ Error: ${err.message}`;
  }

  await sendTelegram(env, chatId, replyText);
}

// ─────────────────────────────────────────────────────────────
// Command handlers
// ─────────────────────────────────────────────────────────────

async function handleStatus(env) {
  const run = await env.DCA_KV.get('last_run', { type: 'json' });

  if (!run) {
    return (
      '🤖 <b>DCA Agent Status</b>\n\n' +
      '📭 No runs recorded yet.\n' +
      'The agent writes here after its first GitHub Actions execution.\n\n' +
      handleNextRun()
    );
  }

  // ── Status indicator ──────────────────────────────────────
  const statusDot = {
    executed: '🟢',
    skipped:  '🟡',
    failed:   '🔴',
    dry_run:  '🔵',
  }[run.status] ?? '⚪';

  const resultIcon = {
    executed: '✅',
    skipped:  '⚠️',
    failed:   '❌',
    dry_run:  '🔬',
  }[run.status] ?? '❓';

  const resultLabel = {
    executed: 'Executed',
    skipped:  'Skipped',
    failed:   'Failed',
    dry_run:  'Dry run',
  }[run.status] ?? run.status;

  // ── Next run countdown ────────────────────────────────────
  const { nextStr, countdown } = computeNextRun();

  // ── Field reads with backward-compat fallbacks ────────────
  const reason       = run.reason       ?? run.ai_reason   ?? '—';
  const liquidityBnb = run.liquidity_bnb ?? run.reserve_bnb ?? 0;
  const tokenName    = run.token_name   ?? 'USDT (BSC Testnet)';
  const pricePct     = run.price_change_pct != null
    ? `${Number(run.price_change_pct).toFixed(2)}%`
    : '—';
  const totalRun     = run.total_cycles_run     ?? '—';
  const totalSkip    = run.total_cycles_skipped ?? '—';

  const txLine = run.tx_hash
    ? `<a href="${run.tx_url}">View on BscScan</a>`
    : 'No tx yet';

  const dryTag = run.dry_run ? ' <i>(dry run)</i>' : '';

  return (
    `🤖 <b>DCA Agent Status</b>\n\n` +
    `${statusDot} Last run: ${run.timestamp}${dryTag}\n` +
    `🪙 Token: ${escapeHtml(tokenName)}\n` +
    `💰 Amount per cycle: <code>${run.amount_bnb} BNB</code>\n` +
    `📅 Frequency: Monthly (1st of each month, 12:00 UTC)\n` +
    `⏰ Next run: <b>${nextStr}</b> (in ${countdown})\n` +
    `\n` +
    `${resultIcon} Last result: <b>${resultLabel}</b>\n` +
    `   <i>${escapeHtml(reason)}</i>\n` +
    `\n` +
    `⛽ Gas at last run: <code>${run.gas_gwei} Gwei</code>\n` +
    `📊 Price change at last run: <code>${pricePct}</code>\n` +
    `💧 Liquidity at last run: <code>${liquidityBnb} BNB</code>\n` +
    `🔗 Last TX: ${txLine}\n` +
    `\n` +
    `📈 Total cycles run: <b>${totalRun}</b>\n` +
    `📉 Total cycles skipped: <b>${totalSkip}</b>`
  );
}

function handleNextRun() {
  const { nextStr, countdown } = computeNextRun();
  return (
    `⏰ <b>Next DCA Run</b>\n` +
    `${nextStr}\n\n` +
    `In <b>${countdown}</b>`
  );
}

async function handleHistory(env) {
  const history = await env.DCA_KV.get('history', { type: 'json' });

  if (!history || history.length === 0) {
    return '📭 No run history yet.';
  }

  const icons = { executed: '✅', skipped: '⚠️', failed: '❌', dry_run: '🔬' };
  const labels = { executed: 'Bought', skipped: 'Skipped', failed: 'Failed', dry_run: 'Dry run' };

  const lines = history.map((run, i) => {
    const icon    = icons[run.status]  ?? '❓';
    const label   = labels[run.status] ?? run.status;
    const reason  = run.reason ?? run.ai_reason ?? '—';
    const dryTag  = run.dry_run ? ' <i>[dry]</i>' : '';
    const txLine  = run.tx_hash
      ? `<a href="${run.tx_url}">BscScan</a>`
      : '—';

    return (
      `<b>${run.timestamp}</b> — ${icon} ${label}${dryTag}\n` +
      `Reason: <i>${escapeHtml(reason.slice(0, 100))}</i>\n` +
      `TX: ${txLine}`
    );
  });

  return `📜 <b>Last ${history.length} DCA Runs</b>\n\n` + lines.join('\n\n');
}

async function triggerDryRun(env) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${env.GH_WORKFLOW_FILE}/dispatches`;

  const resp = await fetch(url, {
    method:  'POST',
    headers: {
      'Authorization': `Bearer ${env.GH_PAT}`,
      'Accept':        'application/vnd.github+json',
      'Content-Type':  'application/json',
      'User-Agent':    'dca-agent-cloudflare-worker',
    },
    body: JSON.stringify({
      ref:    env.GH_BRANCH ?? 'main',
      inputs: { dry_run: 'true' },
    }),
  });

  if (!resp.ok) {
    const errBody = await resp.text();
    throw new Error(`GitHub API ${resp.status}: ${errBody}`);
  }
}

// ─────────────────────────────────────────────────────────────
// Shared next-run calculator
// ─────────────────────────────────────────────────────────────
function computeNextRun() {
  const now = new Date();
  let next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1, 12, 0, 0));
  if (next <= now) {
    next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1, 12, 0, 0));
  }
  const msLeft    = next - now;
  const daysLeft  = Math.floor(msLeft / 86_400_000);
  const hoursLeft = Math.floor((msLeft % 86_400_000) / 3_600_000);
  const minsLeft  = Math.floor((msLeft % 3_600_000)  / 60_000);
  const nextStr   = next.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  return { nextStr, countdown: `${daysLeft}d ${hoursLeft}h ${minsLeft}m` };
}

// ─────────────────────────────────────────────────────────────
// Telegram helper
// ─────────────────────────────────────────────────────────────
async function sendTelegram(env, chatId, text) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  await fetch(url, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      chat_id:                  chatId,
      text,
      parse_mode:               'HTML',
      disable_web_page_preview: true,
    }),
  });
}

// ─────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
