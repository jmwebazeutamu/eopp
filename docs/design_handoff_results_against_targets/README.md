# Handoff: "Results Against Targets" Dashboard

## Overview
Design reference for the "Results against targets" screen on the EOPP platform — the M&E/reporting view showing framework indicators, cumulative placements over time, and demographic disaggregation, reached via the "Results" tab. Recreated from a screen capture of the existing implementation as an HTML reference alongside the My Work, Woreda, and Partners screens. No structural changes made — this is a like-for-like rebuild.

## About the Design Files
The bundled file (`Results Against Targets Dashboard.dc.html`) is a **design reference built in HTML** — a static prototype of look and layout, not production code to copy directly. Recreate it in the target codebase's existing environment and component library.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and layout are final. Shares the sidebar shell (with the "All woredas" scope selector) and design tokens with `design_handoff_woreda_oversight` and `design_handoff_my_work_dashboard` — reuse those implementations rather than rebuilding.

## Screens / Views

### Results Against Targets (single screen, includes sidebar shell)

**Layout**: same shell as Woreda Oversight (272px sidebar incl. "All woredas" selector + flexible content, padding 32px 40px 56px). Content: title + subtitle → tabs ("Results" active) → "Results framework" table card → 2-column row (Cumulative placements chart + Retained-after-exit card) → "Disaggregation" card (2 rows × 3 columns of mini-tables) → "What is uncertain" caveats card.

**Page header**
- Title "Results against targets": 26px weight 700.
- Subtitle: "All woredas · As of 18 Aug 2026, 22:34" — live "as of" timestamp, not static copy.

**Results framework** (white card)
- Micro-label "RESULTS FRAMEWORK", no subtitle.
- 3-column table: Indicator / Value / Framework. Header row 13px weight 700.
- Indicator column: 16px weight 700 name, optional 13px muted note below explaining a caveat or exclusion.
- Value column: 15px weight 600 (or "Not measurable yet" in muted #847e6f when data isn't tracked), optional smaller muted subvalue line showing the raw fraction (e.g. "375 of 699").
- Framework column: 13.5px, cites the source methodology/framework the indicator is adapted from.
- Rows (indicator — value — framework):
  1. Youth clients with business plans financed or enrolled in wage employment — 51 — PSNP 5 / SEASN (P172479)
  2. Share of beneficiaries completing training — Not measurable yet (note: training enrolments aren't recorded) — World Bank Jobs M&E Toolkit (2017)
  3. Number of self- and/or wage employed beneficiaries — 51 (note: gross, not net of deadweight/displacement, not "jobs created") — Jobs M&E Toolkit, PDO-level
  4. Referrals confirmed within threshold — 54% / 375 of 699 (note: referrals from the last 30 days excluded) — Adapted from PSNP "% of transfers within 45 days"
  5. Referral loop closure rate — 39% / 121 of 309 (note distinguishes "verified by someone other than the youth" from a separately-cited 54%/166-of-309 "recorded" rate — both numbers are intentional and different metrics, not a typo) — Adapted from CMS50 "Closing the Referral Loop"

**Cumulative placements** (left card in the 2-col row)
- Micro-label + two subtitle lines: "Counts youth. A youth placed twice enters once, on their first placement. · 2 carried in from before this window" and "Placements to date, by month."
- Horizontal bar-per-month list, Aug 2025 → Aug 2026 (13 months): month label (13px) + track (14px tall, radius 7px, bg #ece7d9) + filled bar (#1f5c3f) proportional to cumulative total against the max (51) + trailing "**{total}** (+{delta})" text, where delta is that month's net new placements.
- Data: 2025-08:4(+2), 09:6(+2), 10:9(+3), 11:10(+1), 12:12(+2), 2026-01:15(+3), 02:17(+2), 03:21(+4), 04:26(+5), 05:30(+4), 06:34(+4), 07:37(+3), 08:51(+14).

**Retained 3 months after exit** (right card)
- Micro-label, then large "Not measurable yet" (20px weight 700) + explanatory sentence: placements and follow-up checks aren't recorded in the system. Same non-metric pattern as "Unassigned youth" on the Woreda screen — render as a statement, not a stat tile with a dash.

**Disaggregation** (white card, full width)
- Micro-label "DISAGGREGATION", no subtitle.
- Two rows of 3 mini-tables each (3-col grid, 28px gap): row 1 = Sex, Age band, Woreda; row 2 = Disability, Settlement type, PSNP status. Each mini-table: bold 16px group title, then a 4-column table (label / Registered / Placed / Rate) with a 12.5px muted header row.
- Sex: Female 274/25/9%, Male 234/18/8%, Other 106/8/8%.
- Age band: 18-24 290/28/10%, 25-29 211/12/6%, 15-17 112/11/10%, under 15 1/0/"— too few to assess" (render as muted italic text, not "0%" — sample size too small to be meaningful).
- Woreda: Adama 212/20/9%, Bishoftu 202/13/6%, Lume 200/18/9%.
- Disability: No disability 433/43/10%, Not disclosed 47/1/2%, Physical/mobility 42/5/12%, Visual 40/0/0%, Hearing 39/0/0%, Not recorded 13/2/15%* (the asterisk in source flags this rate as based on a very small n — carry the asterisk through, and if the codebase supports footnotes, attach a footnote explaining low sample size).
- Settlement type: Rural 320/29/9%, Peri-urban 115/12/10%, Urban 112/5/4%, Not recorded 67/5/7%.
- PSNP status: Enrolled 376/31/8%, Graduated 191/16/8%, Not PSNP 39/3/8%, Not recorded 8/1/"— too few to assess".
- Footer note (12.5px muted): "Rural/urban is not available: nothing in the record says which a youth lives in." — this refers to a rural/urban split elsewhere in the source data model that isn't populated; keep as a data-quality caveat, not dead copy.

**What is uncertain** (white card, full width, final section)
- Micro-label + a 3-item bulleted list (14px, generous 12px gap between items) of plain-language methodological caveats:
  1. Placements are gross, not net of deadweight/displacement — not "jobs created".
  2. The headline placement count includes every recorded outcome, not just externally-verified ones — report the verified subset separately.
  3. Retention isn't yet measurable — nothing records whether a youth stays in their placement.
- This card functions as a permanent methodology disclaimer, not a dismissible warning — keep it always visible, not behind a toggle or collapsed accordion.

## Interactions & Behavior
- Tabs (My work / Woreda / Programme / Results): "Results" active here — wire to routing.
- "All woredas" scope selector: visual only in the prototype — should filter all data on the page.
- No hover/focus/loading/error states beyond default — apply the codebase's standard interactive states.
- Desktop-only design (no responsive/mobile layout specified).
- This is a read-only reporting screen — no inputs, filters, or CTAs beyond the scope selector and tabs.

## Data Shape (for reference — real app should fetch, not hardcode)
- Framework indicator: `{ name, value: string | number | null, subvalue?: string, note?: string, frameworkSource, notMeasurable: boolean }`
- Placement month: `{ month: 'YYYY-MM', cumulativeTotal, monthDelta }`
- Disaggregation row: `{ groupName, label, registered, placed, rate: string | 'too_few_to_assess', flagged?: boolean }` (flagged marks the asterisked low-n row)

## Design Tokens
Shares the palette/type/spacing scale documented in `design_handoff_woreda_oversight/README.md` and `design_handoff_my_work_dashboard/README.md` (sidebar #1b3a30, page bg #f7f2e7, card border #e6e1d3, 26px title, no shadows). No new accent colors introduced on this screen — placement bar uses the same #1f5c3f "on track" green as the Woreda screen's stacked bars; track background #ece7d9.

## Assets
No image assets — icons are inline SVG placeholders, replace with the app's real icon set.

## Files
- `Results Against Targets Dashboard.dc.html` — full design prototype (HTML), inline styles and sample data included.
