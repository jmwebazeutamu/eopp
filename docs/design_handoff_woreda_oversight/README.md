# Handoff: "Woreda Oversight" Dashboard

## Overview
Design reference for the "Woreda oversight" screen on the EOPP platform — the manager-facing view of team caseload, partner responsiveness, and data quality, reached via the "Woreda" tab/nav item. Recreated directly from a screen capture of the existing implementation; layout was already visually even, so this is a like-for-like rebuild (no structural redesign), done so it's available as an HTML reference alongside the My Work and Partners screens.

## About the Design Files
The bundled file (`Woreda Oversight Dashboard.dc.html`) is a **design reference built in HTML** — a static prototype of look and layout, not production code to copy directly. Recreate it in the target codebase's existing environment and component library.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and layout are final. Shares the sidebar shell with the My Work and Partners screens (see `design_handoff_my_work_dashboard`, `design_handoff_partners_page`) — reuse that sidebar implementation. Note: on this screen the sidebar also shows an "All woredas" scope-selector pill directly under the search field (not present on the My Work screen) — confirm with product whether this selector is specific to Woreda/Programme/Results tabs or should appear everywhere.

## Screens / Views

### Woreda Oversight (single screen, includes sidebar shell)

**Layout**: same shell as My Work (272px sidebar + flexible content, padding 32px 40px 56px). Content: title + subtitle → tabs ("Woreda" active) → 5-up KPI row → full-width "Team caseload by case manager" card → full-width "Partner response time" table card → full-width "Data completeness" table card (with an "Unassigned youth" sub-section beneath its table).

**Page header**
- Title "Woreda oversight": 26px weight 700.
- Subtitle: "Which staff and which cases need you. · All woredas · As of 18 Aug 2026, 22:15" — the date/time is a live "as of" stamp, not static copy.

**KPI row** (6 equal cards, same visual treatment as My Work dashboard: white/amber/mint variants, 30px number, 11px micro-label)
1. Total registered youth — white — 614 — "All woredas" (matches the "614" record total referenced in the Data Completeness table below — same underlying count, surfaced as a headline KPI)
2. Open cases — white — 496 — "All woredas"
3. Overdue actions — amber (bg #f6e6c2 / border #e8c877) — 407 — "across the team"
4. Registered, no case yet — white — 68 — "registered but never opened"
5. Median days to confirm — white — "—" (em dash placeholder, no data) — "6 overdue for confirmation"
6. Outcomes verified — mint (bg #dcece2 / border #b7d8c6) — 35 — "of 53 recorded, this month"

**Team caseload by case manager** (white card, radius 10px, padding 20px 22px)
- Micro-label + subtitle "Caseload size and mix, with open alerts past their threshold."
- Legend row: 4 color-coded dot+label pairs — On track (#1f5c3f), Awaiting partner (#d9a441), Stalled (#a83a2a), Placed or exited (#a39a89).
- One block per case manager (name 18px weight 700, right-aligned "Caseload {n}" text + two red pills "▲ over ceiling" and "▲ {n} overdue"), followed by a single horizontal stacked bar (height 28px, radius 7px) with 4 proportional segments in the legend colors. Each segment shows its count centered in white/dark text **only when wide enough to fit** — when the "Stalled" segment is too narrow (roughly <6% of total, e.g. counts of 7-8 against caseloads of 130+), its count is dropped from inside the bar and shown instead as a plain-text label "Stalled {n}" to the right of the whole bar.
- Sample data (name — on track / awaiting / stalled / placed / caseload / overdue):
  1. Case Manager One — 77 / 24 / 7 / 37 — Caseload 145 — 110 overdue (stalled shown as external label)
  2. Case Manager Four — 56 / 35 / 16 / 30 — Caseload 137 — 97 overdue (stalled shown inline)
  3. Case Manager Two — 65 / 25 / 8 / 36 — Caseload 134 — 95 overdue (stalled shown as external label)
  4. Case Manager Three — 50 / 24 / 23 / 33 — Caseload 130 — 105 overdue (stalled shown inline)
- All 4 managers are flagged "over ceiling" in the sample data — confirm with product what the ceiling threshold is and whether the pill should only appear when actually exceeded.

**Partner response time** (white card)
- Micro-label + subtitle "Median days from referral sent to partner decision."
- 4-column table: Partner / Median days / Confirmed referrals / Recorded by staff.
- All 6 rows show "— too few to assess" (italic, muted #9b9282) in Median days in the sample data — this is a real empty/insufficient-data state, not a missing value, and should render distinctly from a numeric median.
- Rows: Adama Polytechnic College (7 confirmed / 108 recorded), Adama Skills Hub (5 / 107), Bishoftu Automotive Plc (5 / 83), Oromia Credit and Savings (3 / 109), Adama Health Centre (3 / 85), Rift Valley Enterprise Agency (1 / 103).
- Footer note (12.5px, muted): explains why partner-entered vs. staff-recorded confirmations are split, and how a non-responding partner could otherwise appear to "score" the same as an immediate responder.

**Data completeness** (white card)
- Micro-label + subtitle "Required fields missing on records in scope."
- 3-column table: Indicator / Missing / What it costs.
- "Missing" column is a pill: amber pill (bg #f6e6c2, text #8a6a1f) reading "{n} of 614 missing" when incomplete, neutral pill (bg #ece7d9, text #5c584e) reading "Complete" when fully populated.
- Rows: Phone number (11 of 614 missing), Consent date (Complete), Profiling record (76 of 614 missing), Outcome type on a completed referral (Complete), Failure reason on a failed referral (Complete). "What it costs" column carries a plain-language consequence sentence per indicator — copy is final, keep verbatim.
- **Unassigned youth** sub-section directly beneath the table (not a separate card): micro-label + large bold "Not measurable yet" + explanatory sentence. This is a deliberate non-metric state (the app's data model doesn't allow unassigned youth to exist) — render as a statement, not as a stat tile with a dash.

## Interactions & Behavior
- Tabs (My work / Woreda / Programme / Results): "Woreda" active here — wire to routing; content for other tabs is out of scope for this file.
- "All woredas" scope selector (sidebar): visual only in the prototype — should filter all data on the page by woreda when wired up.
- No hover/focus/loading/error states defined beyond default — apply the codebase's standard interactive states to the selector and any future clickable rows.
- Desktop-only design (no responsive/mobile layout specified).

## Data Shape (for reference — real app should fetch, not hardcode)
- KPI stats: `{ openCases, overdueActions, registeredNoCaseYet, medianDaysToConfirm, overdueForConfirmation, outcomesVerified, outcomesRecordedTotal, asOfTimestamp }`
- Case manager row: `{ name, onTrackCount, awaitingPartnerCount, stalledCount, placedOrExitedCount, caseloadTotal, overCeiling: boolean, overdueCount }`
- Partner response row: `{ partnerName, medianDays: number | null, confirmedReferrals, recordedByStaff }`
- Data completeness row: `{ indicator, missingCount: number | null, totalRecords, costDescription }`

## Design Tokens
Shares the palette/type/spacing scale documented in `design_handoff_my_work_dashboard/README.md` (sidebar #1b3a30, page bg #f7f2e7, card border #e6e1d3, amber/mint/red accent triads, 26px title / 30px KPI number / 11-12px micro-labels, no shadows). Additional colors introduced on this screen:
- Stacked-bar segment colors: on-track #1f5c3f, awaiting-partner #d9a441, stalled #a83a2a, placed-or-exited #a39a89.
- Muted/insufficient-data text: #9b9282 (italic).

## Assets
No image assets — icons are inline SVG placeholders / unicode glyphs, replace with the app's real icon set.

## Files
- `Woreda Oversight Dashboard.dc.html` — full design prototype (HTML), inline styles and sample data included.
