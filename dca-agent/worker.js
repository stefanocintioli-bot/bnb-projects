/**
 * BNB Chain DCA Agent — Cloudflare Worker
 * ─────────────────────────────────────────
 * Receives Telegram webhook POST requests and handles 4 interactive commands:
 *   /status   → last run result from KV
 *   /nextrun  → days until next scheduled run
 *   /history  → last 5 run results from KV
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
    // Only accept POST from Telegram
    if (request.method !== 'POST') {
      return new Response('DCA Agent Worker — OK', { status: 200 });
    }

    // Validate Telegram webhook secret token to reject forged requests
    const incomingSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token');
    if (env.TELEGRAM_WEBHOOK_SECRET && incomingSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }

    // Parse body — clone first so we can read it
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
        // Fire GitHub dispatch in background — reply immediately
        env._ctx_waitUntil_dryrun = triggerDryRun(env); // stored for potential debug
        replyText = '🤖 Dry run triggered, check Telegram in ~60s';
        // Also actually kick it off:
        await triggerDryRun(env);
        break;

      default:
        replyText =
          'Available commands:\n' +
          '/status — last run result\n' +
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
    return '📭 No runs recorded yet.\nThe agent writes here after its first GitHub Actions execution.';
  }

  const statusIcon = {
    executed: '✅',
    skipped:  '⏭️',
    failed:   '❌',
    dry_run:  '🔬',
  }[run.status] ?? '❓';

  const dryTag = run.dry_run ? ' <i>(dry run)</i>' : '';
  let text =
    `${statusIcon} <b>Last DCA Run</b>${dryTag}\n` +
    `📅 ${run.timestamp}\n` +
    `Status: <b>${run.status}</b>\n` +
    `⛽ Gas: <code>${run.gas_gwei} Gwei</code>\n` +
    `💧 Liquidity: <code>${run.reserve_bnb} BNB</code>\n` +
    `🤖 AI: <i>${escapeHtml(run.ai_reason)}</i>`;

  if (run.tx_hash) {
    text += `\n🔗 <a href="${run.tx_url}">View on BscScan</a>`;
  }

  return text;
}

function handleNextRun() {
  const now = new Date();
  const y   = now.getUTCFullYear();
  const m   = now.getUTCMonth(); // 0-11

  // Next 1st of month at 12:00 UTC
  let next = new Date(Date.UTC(y, m, 1, 12, 0, 0));
  if (next <= now) {
    // This month's run already passed — go to next month
    next = new Date(Date.UTC(y, m + 1, 1, 12, 0, 0));
  }

  const msLeft    = next - now;
  const daysLeft  = Math.floor(msLeft / 86_400_000);
  const hoursLeft = Math.floor((msLeft % 86_400_000) / 3_600_000);
  const minsLeft  = Math.floor((msLeft % 3_600_000)  / 60_000);

  const nextStr = next.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';

  return (
    `⏰ <b>Next DCA Run</b>\n` +
    `${nextStr}\n\n` +
    `In <b>${daysLeft}d ${hoursLeft}h ${minsLeft}m</b>`
  );
}

async function handleHistory(env) {
  const history = await env.DCA_KV.get('history', { type: 'json' });

  if (!history || history.length === 0) {
    return '📭 No run history yet.';
  }

  const icons = { executed: '✅', skipped: '⏭️', failed: '❌', dry_run: '🔬' };
  const lines = history.map((run, i) => {
    const icon   = icons[run.status] ?? '❓';
    const dryTag = run.dry_run ? ' [dry]' : '';
    const txLink = run.tx_hash
      ? ` — <a href="${run.tx_url}">tx</a>`
      : '';
    return `${i + 1}. ${icon} <code>${run.timestamp}</code>${dryTag}${txLink}\n   <i>${escapeHtml(run.ai_reason.slice(0, 80))}</i>`;
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
    const body = await resp.text();
    throw new Error(`GitHub API ${resp.status}: ${body}`);
  }
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
