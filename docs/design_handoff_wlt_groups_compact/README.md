# Handoff: WLT Savings Group screens — compact layout

## Overview
Tighter layout for the `wlt` module's group screens (`GroupsPage`, `GroupReadinessPage`, `GroupRoster`). No data model, routing, or permissions changes — this is spacing, card consolidation, and roster markup only. Reviewed against `docs/UI_UX_BACKLOG.md` and the live source in `web/src/pages/wlt/`.

## What changed and why
Vertical budget on `GroupReadinessPage` was the problem: header → readiness card (one condition per full-width row) → roster card (flex list, each member its own wrapping row) → three separate Savings/Meetings/Lending cards stacked or wrapped → risk card → linkages card. On a 1440 screen that's 1300–1500px before linkages are visible; on a phone it's several screens of scrolling to reach the roster.

Four changes, same data:
1. **Readiness conditions** — full-width `<li>` rows become a `grid-template-columns: repeat(auto-fit, minmax(150px, 1fr))` tile grid. Same "actual (need threshold)" text, same three-state tone, just not one-per-row.
2. **Savings / Meetings / Lending** — three `Card`s become one card with three flex columns (`indicator-cols`). Each `Field` (label line + value line, ~40px) becomes a single `indicator-row` (label left, value right, ~22px).
3. **Roster** — the `<ul>` of flex `<li>` rows (name, joined-date, exit button, each wrapping independently) becomes a `<table>`. Same rule this screen was built to convey (a membership is a dated range, not a flag) — former members still list below, unchanged.
4. **Card padding** — `18px 20px` → `12px 14px` on these three screens only (`.card--tight`), not a global token change. `--r-card`, colors, and the rest of the app are untouched.

Net: roughly 1300px of vertical content becomes ~750px at 1440px width. No screen this touches had a "too few to assess" or empty-state path changed.

## Fidelity
**High-fidelity for spacing and structure.** Colors, tones, and copy are unchanged — pulled directly from `design/wltStatus.ts` and `i18n/strings.ts`, not reinvented. Confirm before merging:
- Whether `.card--tight` should also apply to `BeneficiariesPage` and the other WLT list screens, or stay scoped to the three group screens above.
- Whether the roster table should keep a phone-card fallback (`.only-phone`) the way `GroupsPage`/`BeneficiariesPage` do — the mock below renders the table at all widths, which may be too dense under 780px.

## CSS additions (`web/src/styles/base.css`)
Append near the existing `.card` rules — reuses `--line`, `--surface-alt`, `--ink-600`, `--green-100`/`--green-ink` tokens, no new colors:

```css
.card--tight {
  padding: 12px 14px;
}

.condition-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--s2);
  margin-top: var(--s3);
}

.condition-tile {
  border: 1px solid var(--line);
  border-radius: var(--r-control);
  background: var(--surface-alt);
  padding: 8px 10px;
}

.condition-tile__label {
  font-size: 11.5px;
  color: var(--ink-600);
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.condition-tile__value {
  font-size: 12.5px;
  font-weight: 700;
  margin-top: 2px;
}

.indicator-cols {
  display: flex;
  gap: var(--s5);
  flex-wrap: wrap;
}

.indicator-col {
  flex: 1;
  min-width: 170px;
}

.indicator-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 12.5px;
}

.roster-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: var(--s2);
}

.roster-table td {
  padding: 5px 4px;
  border-bottom: 1px solid var(--line-soft);
  vertical-align: middle;
}

.officer-tag {
  background: var(--green-100);
  color: var(--green-ink);
  border-radius: var(--r-chip);
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
}
```

## Files
- `GroupReadinessPage.tsx` — full replacement. Same props, same two API calls (`/wlt/groups/:id/readiness/`, `/wlt/linkages/`), same `ConditionLine`/`summarise`/`freshness` helpers from `readinessLayout.ts` — only the JSX below `PageHeader` changed.
- `GroupRoster.tsx` — full replacement. Same props (`group`, `onChanged`), same `AddMemberModal`/`ExitMemberModal`, same candidate-pool and exit-reason logic — only the current-roster list becomes a table.
- `GroupsPage.tsx` — unchanged; it was already table-based. If `.card--tight` is approved for the module, add the class to its `table-card` too.
- Reference mock: `../../Savings Group Module (Compact).dc.html` in the project root — static HTML preview of the same layout with sample data, for a quick look before wiring these files in.
