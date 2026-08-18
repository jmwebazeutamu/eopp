# Handoff: "My Work Today" Dashboard Redesign

## Overview
Redesigned the "My work today" landing dashboard for the EOPP platform (youth employment/case-management admin tool), including the left navigation shell. The original screen had uneven column heights in the card grid (mismatched card heights left large dead-space gaps below shorter cards). This redesign reflows the same content into a layout with consistent, non-gappy column heights. No content, copy, or data was changed — only layout structure.

## About the Design Files
The bundled file (`My Work Dashboard.dc.html`) is a **design reference built in HTML** — a working prototype showing intended look and layout (static; no live interactions beyond default link/hover behavior). It is not production code to copy directly. The task is to **recreate this design in the target codebase's existing environment** (React, Vue, etc., using its established component patterns, state management, and styling approach).

## Fidelity
**High-fidelity.** Colors, typography, spacing, and layout are final. Recreate pixel-perfectly using the codebase's existing libraries/design system where equivalents exist (existing Card, Table, Badge/Pill, Tabs components) rather than introducing new one-off components. This screen shares the sidebar/nav shell with the Partners page redesign (see `design_handoff_partners_page`) — reuse that same sidebar implementation rather than rebuilding it twice; colors/spacing here match it.

## What changed vs. the original
- **Original layout**: 3-column grid below the KPI row — Needs-action-today + Youth-at-risk stacked in column 1, Referrals-awaiting-partner-response alone in column 2, My-caseload-by-status alone in column 3. Column 3 ended far short of column 2's height, leaving a large empty gap.
- **New layout**: 2-column grid — Referrals-awaiting-partner-response (left, tall) sits next to a stacked column of My-caseload-by-status + Needs-action-today (right), which together roughly match its height. Youth-at-risk-of-dropping-out moves to its own full-width section below, laid out as a 2-column list (3 rows × 2 columns) so it reads as a compact block rather than a single long list.
- KPI row (top 5 stat cards) is unchanged in content; all 5 cards now stretch to equal height via grid auto-stretch.

## Screens / Views

### My Work Today (single screen, includes sidebar shell)

**Layout**
- Full-height flex row: fixed-width sidebar (272px) + flexible main content area.
- Main area padding: 32px 40px 56px.
- Structure top to bottom: page title + subtitle → tab row → 5-up KPI card grid (gap 16px) → 2-column grid (1.4fr / 1fr, gap 20px) → full-width "Youth at risk" card.

**Sidebar** (width 272px, background #1b3a30, text ~#c3d2c9 default / white active)
- Header: "Economic Opportunities Pathway Platform" wordmark (17px weight 700) + collapse chevron button (26×26px, border 1px #3d5f52, radius 6px).
- Search field: background #234a3d, border 1px #33594a, radius 8px, padding 9px 12px, placeholder "Search youth, cases, par..." at 13px, color #a9bcb2.
- Section label style: 11px weight 700, letter-spacing 0.06em, color #7fa091.
- Sections/items: DASHBOARD (My work [active], Woreda, Programme, Results), WORK (Cases, Referrals, Alerts), DIRECTORY (Youth registry, Partners, Users).
- Nav item: flex row gap 10px, padding 9px 10px, radius 7px, 14px text. Active ("My work"): background #2f5c4c, white text, weight 600. Inactive: color #c3d2c9, no background.
- Footer (pinned to bottom): 34×34px circular avatar (background #e0a933, initials "PA", color #1b3a30, 13px weight 700) + name "Platform Admin" (13.5px weight 600, white) / role "System administrator" (12px, #93a89c). Top border 1px #2d4e42.

**Page header**
- Title "My work today": 26px weight 700.
- Subtitle "What needs doing next. · Live · refreshed just now": 14px, color #6b6559.

**Tabs** (border-bottom 1px #e2dccc)
- My work (active — 2px underline #1f4d3f, weight 600, color #1c1c1a), Woreda, Programme, Results (inactive — no underline, color #847e6f). 14.5px, gap 28px.

**KPI card row** (grid, 5 equal columns, gap 16px, all cards stretch to equal height)
Each card: radius 10px, padding 16px 18px, micro-label (11px weight 700 letter-spacing 0.05em) → big number (30px weight 700) → helper text (12.5px).
1. Needs action today — white bg / border #e6e1d3 — "0" — "Alerts assigned to you, past their threshold."
2. Referrals awaiting partner response — amber bg #f6e6c2 / border #e8c877, label+helper text #8a6a1f/#7a6533 — "15" — "6 older than 14 days"
3. Active referrals — white — "266" — "across 222 youth"
4. Opened this week — white — "1" — "10 closed this week"
5. Outcomes verified — mint bg #dcece2 / border #b7d8c6, label/helper #1f5c3f/#2f6b4d — "35" — "of 53 recorded, this month"

**Referrals awaiting partner response** (left column, white card, radius 10px, padding 20px 22px)
- Micro-label + "Longest wait first." subtitle.
- 3-column table (Youth / Partner / Waiting), header row 12px weight 700 color #847e6f, row border-bottom 1px #f1ede1, row padding 12px 0.
- Waiting column: red pill (bg #f8dede, text #a83a2a, 12px weight 700, radius 20px, padding 4px 9px) showing "▲ {n}d".
- Rows (all "Adama"/"Rift Valley" partner records), longest wait first:
  1. Meseret Dinku — Adama Health Centre — 37d
  2. Nardos Girma — Adama Skills Hub — 35d
  3. Almaz Nagawo — Adama Health Centre — 33d
  4. Hawi Mekonnen — Rift Valley Enterprise Agency — 32d
  5. Abebe Roba — Adama Skills Hub — 17d
  6. Girma Bekele — Adama Skills Hub — 17d
- Footer link "View all 15 →"; note text below top border: "Threshold: partner confirmation overdue after 14 days. Configurable per alert type."

**My caseload by status** (right column, top card)
- 3-column table (Status / Cases / Oldest).
- Status shown as pill with icon glyph + label, white-space:nowrap (do not let labels wrap — this broke in QA on the "Referral Pending" pill and must stay single-line):
  - Active — mint pill (bg #e4efe8, text #2f6b4d) — 248 — 112d
  - Referral Pending — amber pill (bg #f6e6c2, text #8a6a1f) — 108 — 25d
  - Stalled — red pill (bg #f8dede, text #a83a2a) — 54 — 120d
  - Placed — solid dark-green pill (bg #1f4d3f, text white) — 86 — 25d
  - Exited — neutral pill (bg #ece7d9, text #5c584e) — 50 — 25d

**Needs action today** (right column, bottom card — short by design, no forced min-height)
- Micro-label + "Alerts assigned to you, past their threshold." subtitle.
- Body text: "No alerts are assigned to you. 407 are open on cases you can see."

**Youth at risk of dropping out** (full-width card below the 2-column row)
- Micro-label + "Longest without contact first." subtitle.
- 2-column grid of rows (3 per column), each row: bold name (14.5px weight 700) + "No activity for {n} days" (12.5px, color #847e6f) on the left, neutral day-count pill (bg #ece7d9, text #4c473d, radius 20px) on the right.
- Rows: Obsa Feyisa 120d, Kalkidan Assefa 117d, Selam Bekele 112d, Nardos Abera 111d, Meseret Nagawo 110d, Chaltu Mekonnen 109d.
- Footer link "View all 57 →".
- Note box below (bg #f4f0e5, radius 8px, padding 14px 16px, 13px text): "This list checks one of four conditions. Not yet instrumented:" followed by a bulleted list — 3 conditions were visible in source material (training absences, exit-reason-less placement, failed contact attempts); confirm the 4th condition with the product owner before implementing, since the source only enumerated three.

## Interactions & Behavior
- **Tabs** (My work / Woreda / Programme / Results): static in the prototype (only "My work" content was in scope for this redesign) — wire to real routing/content per tab.
- **"View all 15 →" / "View all 57 →"**: link placeholders — should navigate to the full Referrals and full At-Risk-Youth lists respectively.
- **Sidebar nav**: static in the prototype; wire to routing. "My work" is active for this screen.
- No hover/focus/loading/error states defined beyond default — apply the codebase's standard interactive states.
- Desktop-only design (no responsive/mobile layout specified).

## Data Shape (for reference — real app should fetch, not hardcode)
- KPI stats: `{ needsActionToday, referralsAwaitingResponse, referralsOlderThan14d, activeReferrals, activeReferralsYouthCount, openedThisWeek, closedThisWeek, outcomesVerified, outcomesRecordedTotal }`
- Referral row: `{ youthName, partnerName, waitingDays }`
- Caseload status row: `{ status: 'active'|'referral_pending'|'stalled'|'placed'|'exited', count, oldestDays }`
- At-risk youth row: `{ name, daysSinceContact }`

## Design Tokens

**Colors**
- Sidebar background: #1b3a30; sidebar active item background: #2f5c4c
- Page background: #f7f2e7
- Card / surface background: #ffffff; card border: #e6e1d3
- Divider (light): #f1ede1 / #ece7d9
- Primary text: #1c1c1a; secondary/muted text: #6b6559, #847e6f
- Amber accent (referrals-awaiting card, pending pill): bg #f6e6c2, border #e8c877, text #8a6a1f/#7a6533
- Mint accent (outcomes-verified card, active pill): bg #dcece2/#e4efe8, border #b7d8c6, text #1f5c3f/#2f6b4d
- Red accent (waiting/stalled pills): bg #f8dede, text #a83a2a
- Neutral pill (day-count, exited): bg #ece7d9, text #4c473d/#5c584e
- Avatar accent: #e0a933

**Typography** (font stack: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif)
- Page title: 26px / weight 700
- KPI number: 30px / weight 700
- Card name / at-risk name: 14.5px / weight 700
- Table header / micro-labels: 11-12px / weight 700, letter-spacing 0.05-0.06em, uppercase
- Body default: 13-14px

**Spacing scale used**: 2, 4, 6, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 28, 32, 40, 56 (px)

**Radius**: 6-8px (inputs, small controls), 10px (cards), 20px/999px (pills)

**Shadows**: none — borders and flat background contrast only.

## Assets
No image assets — icons are inline SVG placeholders / unicode glyphs and should be replaced with the app's real icon set. No logos beyond the text wordmark.

## Files
- `My Work Dashboard.dc.html` — the full design prototype (HTML), all inline styles and sample data included. Open in a browser to view directly.
