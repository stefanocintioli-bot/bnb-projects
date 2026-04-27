# BNB Chain — Slides Master Prompt
# Version 1.0 — April 2026
# Source: BNB Chain Slides Material Library (Google Slides)
# Visual reference: PDF rasterization of official template
# Author: Stefano Cintioli, LatAm Community Lead

# ─────────────────────────────────────────────────────────────
# HOW TO USE THIS FILE
# Claude Code reads this before building any presentation.
# Contains: verified brand values, exact component specs from
# the official Material Library, and the pre-build questionnaire.
# ─────────────────────────────────────────────────────────────

## CRITICAL BRAND RULES (DOM-verified, non-negotiable)
- Font: Space Grotesk ONLY
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap')
- NEVER use: Syne, Inter, Roboto, Arial, DM Mono, system fonts
- Gold: #FFE900 — NEVER #F0B90B
- Background: #0D0D0D
- Text primary: #FFFFFF
- Text muted: #888888
- Logo: BOTTOM-LEFT, every slide, ~24px from edges
- Footer right: "BUILD WEB3 WITH BNB CHAIN" — small, muted
- Slide counter: bottom right (e.g. "01 / 27")
- Aspect ratio: 16:9 fixed
- Background decoration: dark grid lines (very subtle, ~4% opacity)
  + geometric hexagon/cube shapes on RIGHT side, dark tones
  with subtle gold accent — present on ALL slides except
  full-bleed photo slides. Background has a slight gradient
  from very dark charcoal (~#131313) to near-black (#0D0D0D).

---

## COMPONENT LIBRARY
# Each component below is extracted visually from the official
# Material Library slides. Colors marked [APPROX] are visually
# estimated from PDF — use brand-system.md verified values
# for exact CSS implementation.

---

### COMPONENT 1 — SLIDE COVER (Section divider)
Visual reference: Slide 1 of Material Library
Use for: opening slide of every presentation
Layout: large text bottom-left, decorative hexagon pattern right
- Main title: very large (~72–96px), bold, #FFE900 (gold)
  + #FFFFFF (white) on separate lines
- BNB Chain logo: top-left corner
- Background: dark with hexagon/cube 3D elements right side,
  gold accents visible in bottom-right geometric shapes
- No logo bottom-left on this specific slide (uses top-left)
- "BUILD WEB3 WITH BNB CHAIN" not shown on cover

### COMPONENT 2 — SLIDE BACKGROUND (Content base)
Visual reference: Slides 4, 7, 9 of Material Library
Use for: base background for all content slides
Variants confirmed in template:
  A) Dark grid + BNB cube top-right (slide 4) — most common
  B) Dark grid + sphere/planet bottom (slide 5) — atmospheric
  C) Dark grid + DeFi coin stack right (slide 6) — finance topics
  D) Plain dark grid only (slide 7) — cleanest, most flexible
  E) Split dark/medium grey (slide 9) — for comparison layouts
All variants share:
- BNB Chain logo bottom-left
- "BUILD WEB3 WITH BNB CHAIN" bottom-right, small, ~#555555
- Subtle grid lines across full slide

### COMPONENT 3 — LABEL / TAG PILL
Visual reference: Slide 32 (OUR MISSION / OUR VISION pills)
Use for: section labels, slide category identifiers
Appearance: dark rounded pill/capsule
  background: ~#2a2a2a [APPROX]
  border-radius: 999px (fully rounded)
  padding: ~6px 16px
  font: 11–12px, uppercase, bold, #FFFFFF
  letter-spacing: 0.08–0.1em
Examples in template: "OUR MISSION", "OUR VISION",
  "IDEATION", "DEPLOYMENT", "POST DEPLOYMENT"

### COMPONENT 4 — SECTION HEADER (Yellow title + subtitle)
Visual reference: Slides 32, 33, 34, 35, 36, 39
Use for: slide title at top of content slides
Structure:
  - Section category label: LABEL PILL (Component 3) centered
    or small yellow text top-left (varies by layout)
  - Main title: 28–40px bold, centered or left-aligned
    Color: #FFE900 (gold) or mixed gold + white words
    e.g. "Onboard the [next billion Web3 users]."
    white words normal weight, gold words bold
  - Subtitle/description: 14–16px, #FFFFFF or #888888, below title
  Yellow section label variant (slide 33, 34, 35):
  - Small label text: 11px uppercase bold #FFE900, top-left
  - Large stat or title: 36–72px bold #FFE900, below label

### COMPONENT 5 — BENTO STAT CARD (Small — 4-up grid)
Visual reference: Slide 19 top row, Slide 36 top row
Use for: metrics, KPIs, comparative stats
Appearance:
  background: ~#1e1e1e [APPROX — dark grey card]
  border: 1px solid ~#333333 [APPROX]
  border-radius: ~8–10px
  padding: ~20–24px
Internal structure (top to bottom):
  - Label: 10–11px, uppercase, #888888 or #FFFFFF normal weight
    e.g. "LOREM IPSUM", "DAILY ACTIVE WALLETS"
  - Value: 36–48px, bold, #FFE900
    e.g. "$9.99B", "4.32M", "700M+"
  - Sub-label: 13–14px, #FFFFFF or #888888
    e.g. "Lorem Ipsum Dolor Simet", "#1 across all chains"
Grid layout: 4 cards per row, equal width, ~10px gap
Card height: fills available vertical space equally

### COMPONENT 6 — BENTO STAT CARD (Large — 2-up)
Visual reference: Slide 19 middle row
Use for: featured metrics, primary KPI highlight
Same appearance as Component 5 but:
  - Spans 2 columns width (50% each instead of 25%)
  - Value font size larger: ~60–72px bold #FFE900
  - More body text below value (1–2 lines description)
  - More padding inside card

### COMPONENT 7 — BAR CHART BENTO
Visual reference: Slide 19 bottom row, Slide 36 bottom section
Use for: competitive comparison, chain rankings
Appearance: single wide card spanning full width
  background: ~#1e1e1e [APPROX]
  border: 1px solid ~#333333 [APPROX]
  border-radius: ~8–10px
  padding: ~20–24px
Internal structure:
  - Title: 10–11px uppercase #888888 centered top
    e.g. "DAILY ACTIVE WALLETS - CHAIN COMPARISON"
  - Bar chart: horizontal bars, proportional heights
    BNB Chain bar: #FFE900 (gold, tallest)
    Competitor bars: ~#3a3a3a [APPROX] (grey, shorter)
  - Value above each bar: 13–14px #FFE900 (BNB) or #888888
  - Label below each bar: 12px #FFFFFF
    e.g. "BNB Chain", "Solana", "NEAR", "Ethereum"

### COMPONENT 8 — SPLIT LAYOUT (Stat left + Cards right)
Visual reference: Slide 35 (DeFi layout)
Use for: topic intro with supporting evidence
Layout: 40% left column / 60% right column, vertical divider
Left column:
  - Topic title: 28–36px bold #FFE900, top-left
  - Stat label: 10–11px uppercase #888888
    e.g. "CHAIN TVL", "DAILY USERS"
  - Stat value: 48–64px bold #FFE900
    e.g. "$5.9B", "4.32M"
  - Description paragraph: 13–15px #FFFFFF, line-height ~1.5
Right column: 4 stacked content cards (Component 9)
Divider: very subtle, ~1px #222222 [APPROX] vertical line

### COMPONENT 9 — CONTENT CARD (Right column card)
Visual reference: Slide 35 right column cards
Use for: supporting points, evidence cards in split layout
Appearance:
  background: ~#242424 [APPROX — slightly lighter than bg]
  border-radius: ~6–8px
  padding: ~16–20px
  margin-bottom: ~8px
Internal structure:
  - Card title: 13–14px bold #FFE900
    e.g. "Deep stablecoin liquidity"
  - Card body: 13px #FFFFFF, line-height ~1.5
    1–2 lines of supporting text

### COMPONENT 10 — BULLET LIST WITH DIAMOND ICON
Visual reference: Slide 34 (institutional adoption)
Use for: lists of items, features, ecosystem players
Structure:
  - Section title: 13–14px bold #FFE900, top-left, italic
    e.g. "Institutional adoption of RWA in numbers"
  - Each bullet item:
    Icon: ◆ diamond shape, #FFE900 (gold)
    Text: 22–28px, #FFFFFF, bold/regular mix
    e.g. "Circle USYC ($2.5b+)"
  - Sub-section divider: same structure, new yellow title
  - Multi-column variant: 2 columns of bullets at bottom
Background: right side has gold/dark 3D cube stack decoration

### COMPONENT 11 — TABLE
Visual reference: Slides internal (text extracted shows tables)
Visual seen in: Slide 33 (stablecoins table)
Use for: ranked lists, data tables
Layout: left stats column + right table column
Left column:
  - Topic label: 28–36px bold #FFE900 (e.g. "Stablecoins")
  - Stat rows: label 10px uppercase #888888 + value 36px bold #FFE900
Table right column:
  background: ~#1e1e1e [APPROX]
  border-radius: ~8px
  Header row: 12px #FFFFFF, column names
  Data rows alternating: ~#1e1e1e / ~#222222 [APPROX]
  Row content: logo icon (32px circle) + name + platform +
    ticker + asset class + value
  Each row: ~52–56px height
  Bottom note: 10px #888888 "Source: ..."

### COMPONENT 12 — ECOSYSTEM INCENTIVES / PIPELINE DIAGRAM
Visual reference: Slide 39 (ECOSYSTEM INCENTIVES)
Use for: process flows, program stages, timelines
Structure:
  - Title: centered, uppercase, bold #FFE900, ~28px
  - Subtitle: centered, #FFFFFF, ~14px
  - 3 phase headers: dark pill labels (#2a2a2a bg, #FFE900 text)
    e.g. "IDEATION", "DEPLOYMENT", "POST DEPLOYMENT"
  - Timeline arrows between phases: thin #888888 lines + dots
  - Program boxes: two groups (MONETARY / NON-MONETARY)
    Box style: border 1px #FFE900, bg transparent, #FFFFFF text
    ~10–11px uppercase bold
    Stacked vertically, full-width within their phase column
  - Section labels: vertical text on left, "MONETARY" in #888888

### COMPONENT 13 — CONNECT WITH US / CTA SLIDE
Visual reference: Slide 40
Use for: final CTA slide only
Structure:
  - Title: "CONNECT WITH US" centered, bold, #FFE900, ~28px
  - QR code: centered, large (~200x200px), in dark rounded card
  - Social icons: circle icons left and right of QR
    Left: X (Twitter), YouTube
    Right: Telegram, Discord
    Icon size: ~48px circles, dark bg
    Label below each: #FFE900, 14px
  - CTA button: "JOIN OUR COMMUNITY" dark pill, centered below QR
  - Background: dark grid, subtle
  - BNB Chain logo: bottom-left as always

### COMPONENT 14 — BUILD WEB3 CLOSING SLIDE
Visual reference: Slide 31 (BUILD WEB3 ON BNB CHAIN)
Use for: closing/thank you slide
Structure:
  - Background: dark sphere/circle motif with 3D elements
  - BNB Chain logo icon: centered, ~40px, above text
  - Title line 1: "BUILD WEB3" — very large, bold, #FFE900
  - Title line 2: "ON BNB CHAIN" — very large, bold, #FFFFFF
  - Both lines centered, ~80–96px equivalent

### COMPONENT 15 — FULL-BLEED SECTION DIVIDER
Visual reference: Slides 1 (cover), 2 (SLIDE BACKGROUNDS),
  18 (BENTO INFO CONTAINERS), 30 (SLIDES EXAMPLES)
Use for: section transition slides
Structure:
  - Background: full dark with hexagon pattern right (same as cover)
  - Two-line text bottom-left:
    Line 1: bold, #FFE900, ~60–72px
    Line 2: bold, #FFFFFF, ~60–72px
    e.g. "BENTO INFO" / "CONTAINERS"
  - BNB Chain logo: top-left (NOT bottom-left on this variant)

---

## PRE-BUILD QUESTIONNAIRE
# Claude Code MUST ask ALL questions before writing any code.
# Do not skip. Do not assume any answer.

Q1 — EVENT BASICS
"What is the name, date, location and venue of the event?"

Q2 — AUDIENCE TYPE
"Who is the audience?
  A) University students (tech/dev focus)
  B) University students (general/non-tech)
  C) Retail / general public
  D) Founders and startup people
  E) Developers and builders
  F) Mixed — give approximate % per group"

Q3 — WEB3 KNOWLEDGE LEVEL
"What is the Web3 knowledge level of the audience?
  A) Mostly basic (new to crypto/blockchain)
  B) Mostly medium (know basics, have used crypto)
  C) Mostly advanced (builders, investors, founders)
  D) Mixed — give % breakdown"

Q4 — SPEAKING TIME
"How long is your speaking slot?
  A) 15 min → 12–15 slides
  B) 30 min → 22–28 slides
  C) 45 min → 35–40 slides
  D) Workshop / no fixed time"

Q5 — MAIN TOPIC
"What is the primary topic?
  A) BNB Chain intro (what it is, ecosystem, BNB token)
  B) Technical workshop (smart contracts, dev tools)
  C) Web3 for LatAm (remesas, payments, stablecoins)
  D) Builder programs (MVB, YZi Labs, hackathons)
  E) Custom — describe in one sentence"

Q6 — LIVE BNB CHAIN DATA
"Paste current BNB Chain stats using this prompt on the
BNB Chain website chatbot:

'Give me current BNB Chain metrics: block time BSC,
block time opBNB, average gas fee BSC, gas fee opBNB,
opBNB TPS, TVL DeFi, daily active users, daily transactions,
total unique addresses, BNB market cap rank, latest
quarterly burn amount, any recent milestone or upgrade.'

Paste the full chatbot response here."

Q7 — IRL PHOTOS
"Do you have IRL event photos to include?
If yes: confirm files are in ~/bnb-projects/v0/events/
and list the exact filenames you want to use."

Q8 — CTA
"What is the final call to action?
  A) @BNBChainLatAM X account (default)
  B) Specific URL or QR code
  C) Both"

Q9 — LANGUAGE
"What language for the presentation?
  ES / EN / PT / Bilingual (specify which combo)"

Q10 — SPECIAL REQUIREMENTS
"Anything else specific to this event?
(co-branding, topics to include or avoid, speaker
intro slide needed, partner logos to include, etc.)"

---

## POST-QUESTIONNAIRE BUILD RULES

After collecting all 10 answers, apply these rules:

SLIDE COUNT → determined by Q4 answer

CONTENT DEPTH → determined by Q2 + Q3:
  - Basic audience: lead with analogy (email of money),
    use remesas hook, avoid technical jargon,
    more visuals fewer numbers
  - Technical audience: skip basics, lead with dev tools,
    programs, code examples, testnet
  - Mixed: Artu Grande technique — many slides, one idea
    per slide, switch fast. Keep all levels engaged.

LAYOUT SELECTION → match component to content type:
  - Big number/stat → Component 5 or 6 (bento card)
  - Comparison → Component 7 (bar chart) or 8 (split)
  - List of items → Component 10 (bullet diamond)
  - Process/flow → Component 12 (pipeline diagram)
  - Table of data → Component 11
  - IRL photos → full-bleed with gradient overlay
  - Section break → Component 15 (divider)
  - CTA final → Component 13
  - Closing → Component 14

ANIMATIONS (required):
  - CountUp on all numeric stats (trigger on slide enter)
  - Duration: 1.5s easeOut
  - Animate numeric portion only, symbols stay static

PHOTOS:
  - Always include minimum 2 IRL photo slides if available
  - object-fit: cover, full bleed
  - Overlay: linear-gradient(transparent 40%, rgba(0,0,0,0.92))
  - Label: 12px uppercase bold #FFE900 letter-spacing 0.15em
  - Sub: 22–24px bold #FFFFFF

DEPLOY:
  - Vercel name: [event-name-kebab-case].vercel.app
  - Confirm URL + slide count in terminal after deploy

---

## REPO STRUCTURE
~/bnb-projects/bnb-chain-v0/
├── brand-system.md       ← colors, typography (DOM-verified)
├── slides-master.md      ← THIS FILE
├── logos/                ← BNB Chain SVG logos
└── events/               ← IRL photos by event folder
    ├── binance-peru/
    ├── crecimiento/
    ├── vendimiatech/
    └── university-tour/