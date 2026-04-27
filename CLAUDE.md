Before building any presentation, read ~/bnb-projects/slides-master.md
and run ALL 10 questions of the Pre-Build Questionnaire before writing
any code.

BEFORE BUILDING ANY BNB CHAIN PRESENTATION:
Read ~/bnb-projects/brand-system.md and apply all confirmed values.
Key corrections: font=Space Grotesk, gold=#FFE900, logo=bottom-left.

# CLAUDE.md — bnb-projects

## WHO I AM
Stefano Cintioli — LatAm Community Lead at BNB Chain (Ecosynth Limited)
Buenos Aires, Argentina. UTC-3.
GitHub: github.com/stefanocintioli-bot

Not an engineer. Builds entirely through natural language (vibecoding).
Never writes code manually. Describes what is wanted, Claude builds it.

---

## AGENT HARNESS RULES (read before every task)

### Planning
- Always read existing files before proposing changes
- Confirm full approach with one summary before writing any code
- If a task touches multiple files, list them all before starting
- Never assume a file's contents — read it first

### Execution
- One task at a time. Complete it fully before starting the next
- If something will fail or is the wrong approach, say so immediately
- Surgical edits only when fixing bugs — never rewrite working code
- After completing a task, confirm what was done in one sentence

### Context management
- Never reload files already read in this session
- If context is getting long, summarize completed work and continue
- Skills load on demand — read SKILL.md only when explicitly invoked

### Quality gates
- Every HTML file must open correctly in browser before task is complete
- Every deployed URL must be confirmed working before reporting done
- Never report success without verification

---

## PROJECTS

### bnb-presentations/ ← ACTIVE
- What: Presentation generator skill for BNB Chain events
- Stack: HTML/JS single-file outputs, Vercel deployment
- Skill: /presentation-skill/SKILL.md
- Templates: yellow (workshop/hackathon), dark (institutional/BD)
- Outputs: /outputs/[event-name]/index.html
- Deployed: bnbchain-presentations.vercel.app/[event-name]
- Logos: /presentation-skill/assets/logos/

### bnb-learn/
- What: Bilingual learning platform for BNB Chain
- Stack: HTML, JavaScript, Vercel
- Live: bnb-learn.vercel.app
- Status: Deployed

### dca-agent/
- What: Autonomous DCA agent on BSC Testnet
- Stack: Python, Cloudflare Worker, GitHub Actions
- AI: Groq API (LLaMA 3, free tier)
- Known issue: /dryrun command unresolved — deprioritized

### bnb-guild-bot/
- What: Telegram bot for BNB Guild operator program
- Stack: TypeScript, Node.js, Vercel, Notion API
- Status: Built April 2026

### bnb-onboarding-agent.html
- What: Standalone bilingual onboarding agent EN/ES
- Stack: Single HTML file
- Status: Built, not deployed

---

## ROLE CONTEXT

Role: LatAm Community Lead, BNB Chain
Primary KPIs: Project leads + Developer leads for BNB Chain ecosystem

BD Directory:
- Stablecoins → Jong
- RWA & Emerging Assets → Ben
- Trading / Memes / Prediction Markets → Vlad
- AI / Agentic Economy → Walter
- Privacy + Metaphysics → Diane

Tools: Monday.com (CRM), Luma (events), Vega (expenses),
Yelling (internal Slack), Telegram, GitHub, Vercel, Cloudflare Workers

Content rules:
- No hashtags on official BNB Chain posts
- No financial advice, no price speculation
- Tech-first messaging
- Argentine Spanish for community content
- English for internal BD and institutional content

---

## TECH STACK (proven, free tier)

- Single-file HTML/JS — default for browser tools and presentations
- Cloudflare Workers + KV — lightweight backends and webhooks
- Vercel — all deployments
- GitHub Actions — scheduled automations (cron)
- Groq free tier (LLaMA 3) — AI inference, pin groq==0.9.0 httpx==0.27.0
- Python — scripts on schedule
- TypeScript — bots with external API integrations

## DEPENDENCY LESSONS
- GitHub workflow files MUST be at repo root .github/workflows/
- Clipboard API blocked in sandboxed iframes — use textarea + execCommand
- Free API tiers exhaust fast — always have fallback model

---

## AESTHETIC (for all UI tools)
- BNB Chain yellow: #F0B90B / dark: #0D0D0D / white: #FFFFFF
- Fonts: Syne (display), DM Mono (mono), Lato (body)
- Terminal-style logs for agent tools
- Always include copy-to-clipboard and export options
- Presentations: yellow style = workshop/hackathon, dark style = institutional/BD

---

## PRESENTATION SKILL — DESIGN DECISIONS LOG
_Updated each time a presentation is generated. Claude reads this before building._

2026-04: Intro BNB Chain (dark style) — rebuilt from scratch, 11 slides, trilingual ES/EN/PT
2026-04: Vendimia Tech (yellow style)
- Syne + DM Mono fonts work well, load from Google Fonts
- Geometric diamond pattern overlay at opacity 0.06 — subtle, on-brand
- Two-column layout on slide 4 requires explicit grid CSS — stacking bug fixed
- Photo embed: use base64 inline, not external URLs
- Slide 5 content sparse — increase bullet font to 0.95rem, use flex space-between
- Cards on slide 6: max-height 320px, don't stretch to full viewport
- Logo: inline SVG hexagon polygon, not base64 — renders reliably
- Navigation: circular (last → first), keyboard + touch swipe
- Progress bar: 3px, switches color based on slide background

## TOKEN DISCIPLINE
- Never use deep research or extended search tools without explicit permission
- Prefer targeted single searches over broad research tasks
- Summarize findings in under 200 words unless more depth is requested
- Before any task estimated >5 minutes: state the plan and ask for confirmation
