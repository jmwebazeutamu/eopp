# UI/UX audit: WLT_Dashboard_Prototype_v1.html

Audited 26 Aug 2026 against the ui-ux-pro-max rule set (119 UX guidelines, 10 priority categories). Contrast ratios computed from the token values in `:root`, WCAG 2.x relative luminance.

24 findings. 8 are blocking, 9 should be fixed before build, 7 are polish.

---

## Priority 1 · Accessibility (blocking)

### A1. No focus indicator anywhere in the file
882 lines, zero `:focus` or `:focus-visible` rules. Every tab, subtab and future interactive control falls back to the browser default outline. On `--green-900` (#0A3A2C) that outline is close to invisible.

Fix:
```css
:focus-visible{outline:2px solid var(--gold-300);outline-offset:2px;border-radius:4px}
.tabs button:focus-visible{outline-color:var(--gold-300)}
.subtabs button:focus-visible{outline-color:var(--green-700)}
```
WCAG 2.4.7. Skill rule: *Focus States, severity High.*

### A2. Tab pattern is half-built and misleads screen readers
`role="tablist"` and `role="tab"` are set. Missing: `role="tabpanel"` on the five sections, `aria-controls`, `aria-labelledby`, roving `tabindex`, arrow-key handling.

A screen reader announces "tab 1 of 5", the user presses Right Arrow, nothing happens. Declaring the role without the keyboard contract is worse than plain buttons.

Two options:
1. Complete it. Add `id` pairs, `aria-controls`, set `tabindex="-1"` on unselected tabs, handle ArrowLeft/ArrowRight/Home/End.
2. Drop the roles. Use plain buttons and `aria-current="page"`. Tab key then walks all five, which is correct default behaviour.

Option 2 is 6 lines. Option 1 is ~30 and is the right answer if this becomes the production shell.

### A3. Heatmap text fails contrast on three of four ramp steps

| Cell background | Ratio vs white text | Verdict |
|---|---|---|
| `--q1` #84BEAC | 2.11:1 | fail |
| `--q2` #5FA890 | 2.80:1 | fail |
| `--q3` #3D9078 | 3.85:1 | fail |
| `--q4` #0C5346 | 8.97:1 | pass |

The survival heatmap (ME-2) is the card a World Bank reviewer looks at. Its numbers are the least readable on the page.

Fix: switch cell text colour by ramp step. `--q1`, `--q2` take `--ink-900`; `--q3`, `--q4` take white. Or darken `--q1`/`--q2` and keep white throughout, which weakens the sequential read.

### A4. `--ink-400` fails at the size it is used

`--ink-400` #7A7568 gives 4.59:1 on white, 4.18:1 on `--paper`, 3.96:1 on `--fill-muted`. It is applied at 11px to `.lab`, `.cid`, `.src`, `table.tbl th` and `.heat th`.

Small text needs the full 4.5:1. Two of three backgrounds miss it.

Fix: darken to about #6B6659 (5.4:1 on paper), or move these labels to `--ink-600` #4E4A42, which passes everywhere at 8.82:1.

### A5. Series colour `--s2` fails as text
#D08A0A on white is 2.87:1. Safe as a bar fill, fails if it is ever used for a value label, a 1px rule or a legend swatch border. The palette card at the bottom prints the hex in `--ink-600`, so the prototype itself is fine. Flag it as a build-time constraint.

### A6. Bars, stacks and heatmap carry no programmatic text alternative
`.stack` segments are `<span>` with inline `width` and `background`. Nothing else. Same for `.bar-row .fill`.

The design already solves this visually: every stack has a `.den` line under it repeating the counts, and every `.bar-row` has a `.bv` value. The numbers exist. They are just not associated with the graphic.

Fix, minimal:
```html
<div class="stack" role="img" aria-label="Forming 2, P1 5, P2 4, P3 or later 1">…</div>
```
Skill rule for stacked bars: *never encode category solely by fill; provide a data-table fallback.*

### A7. Tables have no header scope and no caption
Nine `table.tbl` instances. None use `scope="col"`. None have a `<caption>`, and the card `<h3>` above them is not linked with `aria-labelledby`.

Fix: add `scope="col"` to every `<th>`, and `<caption class="sr-only">` repeating the card title. Two-minute change, removes a whole class of screen-reader ambiguity.

### A8. No skip link
Five tabs then a long scroll of cards. A keyboard user has no way past the chrome.

Fix: `<a href="#main" class="skip">Skip to dashboard</a>` as the first body element, visible on focus only.

---

## Priority 2 · Touch and interaction

### B1. Zero transitions in the entire stylesheet
Tab switch, subtab switch, hover, selection state: all flip at 0ms. The skill lists instant state changes as an anti-pattern under *Touch and Interaction, CRITICAL.*

Fix: `transition:background-color .15s ease, color .15s ease` on `.tabs button` and `.subtabs button`. Pair it with a `prefers-reduced-motion: reduce` block that zeroes duration.

### B2. Subtab buttons are 40px, under the 44px minimum
`.subtabs button{min-height:40px}`. The main `.tabs` buttons are correctly 44px. Raise the subtabs to match.

### B3. Only one hover state exists
`.tabs button:hover`. Table rows, `.row`, `.gate .gr` and cards have none. In the prototype nothing else is clickable, so this is not a live defect. In the Django build, every drillable card needs hover plus a cursor change, or users will not find the drill-down.

### B4. Tab change is silent
`window.scrollTo(0,0)` fires, focus stays on the button, and nothing announces that the panel content changed. Add `aria-live="polite"` on a status line, or move focus to the panel heading with `tabindex="-1"`.

---

## Priority 5 · Layout and responsive

### C1. One breakpoint in the file
`@media(max-width:900px)` on `.span2`. That is the only media query. The auto-fit grid at `minmax(330px,1fr)` covers most of the reflow, which is why it mostly holds up. Three components do not.

### C2. `.bar-row` crushes below about 380px
`grid-template-columns:120px 1fr auto`. At 360px viewport with 24px padding either side, the track gets about 130px. Bar values below 20% become invisible slivers.

Fix: at `max-width:420px`, stack to `grid-template-columns:1fr auto` with the label on its own line above.

### C3. `.gate .gr` has four columns and no stacking rule
`1fr auto auto 74px`. Group name, actual, threshold, status. On a phone this compresses the name column to nothing. The facilitator tier is the one most likely to be used on a phone.

### C4. Tab bar scrolls horizontally with no affordance
`.tabs{overflow-x:auto}`. At 360px, tabs 4 and 5 are off-screen with no fade, arrow or scrollbar cue. Users will not know they exist.

Fix: a right-edge gradient mask that hides when scrolled to the end.

### C5. `.wrap` is applied inconsistently
Tables at lines 276 and 342 have no `.wrap` parent. The heatmap and others do. Both unwrapped tables are 5 to 6 columns and will force horizontal page scroll on a phone.

---

## Priority 6 · Typography and colour

### D1. Base font-size is 15px
`body{font-size:15px}`. The skill's rule is 16px base. 15px reads as a deliberate density choice for a dashboard, which is defensible, but it pushes every derived size down one step and is what produces the 11px labels below.

### D2. 11px text in seven places
`.lab`, `.cid`, `.src`, `.src code`, `table.tbl th`, `.heat th`, `.heat .cens`. The floor for body-adjacent text is 12px.

`.lab` and table headers are uppercase with `.06em` tracking, which helps legibility, but 11px uppercase at 4:1 contrast is the worst combination on the page. Raising these to 12px costs almost no vertical space.

### D3. What is already right
Worth stating, because it is unusual:

- Token architecture is semantic, not literal. `--ink-900`, `--line-soft`, `--fill-muted` rather than `--gray-3`.
- Two palettes held strictly apart, status versus series, and the rule is written into the Rationale tab. Most dashboards leak these into each other within a quarter.
- Sequential ramp for phase because phase is ordered. Categorical for series. Correct mapping.
- At risk is gold, not red, with the reasoning stated. Right call.
- `font-variant-numeric:tabular-nums` on every number.
- Source attribution on every card via `.src`.
- The "these rows do not sum to a group count" note on the gate-block card. That note prevents a real misreading.

### D4. No dark mode
No `prefers-color-scheme` block. Not a defect if light-only is the decision. Worth writing down, because a field dashboard used in low light will get asked for it.

---

## Priority 10 · Charts and data

### E1. Stack segments are distinguished by fill only
Legend swatches are colour plus text label, which is correct. The segments in the bar are not. Skill guidance: add a pattern or an outline to at least one segment, or direct-label segments above 15% width.

### E2. No tooltips or focusable data points
Acceptable for a static prototype. For the Django build the skill's accessible fallback is a visible data table alongside each chart, with focusable column headers and `aria-sort`.

### E3. Chart type choices are sound
Horizontal bars for ranked block reasons, stacked bars for phase composition, heatmap for cohort survival by month. All three match the skill's recommendation for those data shapes. Categories stay under 15 in every case.

---

## Suggested order

**Before any Django work** (these change the token file, so doing them later means touching every card again)
A3, A4, D2 · contrast and small-text sizes
A1 · focus ring
B2 · touch target

**In the prototype, ~1 hour**
A2 · decide tab pattern
A6, A7 · aria-label on graphics, scope on tables
A8 · skip link
B1 · transitions plus reduced-motion
C2, C3, C4, C5 · four responsive fixes

**Write into the build spec, not the prototype**
A5 · s2 as fill only
B3, B4 · hover and live-region on drillable cards
E1, E2 · segment labelling and table fallback
D4 · dark mode decision

---

# v2 changelog

`prototype/WLT_Dashboard_Prototype_v2.html`, written 26 Aug 2026. Original untouched.

## Applied

| ID | Change |
|---|---|
| A1 | `:focus-visible` ring, 2px, `--green-700` on light surfaces and `--gold-300` on the dark topbar. Selected tab overrides to green because its background is `--paper`. |
| A2 | Tab pattern completed. `id` / `aria-controls` / `aria-labelledby` pairs on all 7 tabs and 7 panels, roving `tabindex`, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, Home, End. JS rewritten as one reusable `wire()` for both tab levels. |
| A3 | Heatmap cells moved from inline `style="background:var(--qN)"` to classes `.l1`–`.l4`. `l1`–`l3` take `--ink-900` text, `l4` keeps white. Lowest ratio is now 4.57:1, was 2.11:1. |
| A4 | `--ink-400` #7A7568 → #6B6659. Worst case 4.76:1, was 3.82:1. |
| A6 | `aria-hidden="true"` on 25 `.track` and 5 `.stack` graphics. Each already has an adjacent text equivalent (`.bv` value or `.den` line), so hiding the graphic removes the duplicate rather than removing information. Legends stay exposed. |
| A7 | `scope="col"` on 68 `<th>`. `<caption class="sr-only">` on all 16 tables, taken from the card's own `<h3>`; the two Rationale tables have no `<h3>` so they take their section heading. |
| A8 | Skip link, visible on focus only. `<main id="main">`. |
| B1 | 150ms background and colour transitions on both tab levels, with a `prefers-reduced-motion: reduce` block that zeroes all durations. |
| B2 | Subtab buttons 40px → 44px. |
| C2 | `.bar-row` stacks below 430px: label on its own line, full-width track. |
| C3 | `.gate .gr` reflows below 560px: name on row 1, actual / threshold / status on row 2. |
| C4 | Tab strip wraps below 760px instead of scrolling off-screen. |
| D2 | All 11px text raised to 12px, 8 CSS rules and 4 inline styles. |

## Found during the fix, not in the original audit

| ID | Change |
|---|---|
| C6 | Long `<code>` identifiers forced horizontal page scroll at 360px and 320px, worst case 53px on tab 3. Fixed with `code{overflow-wrap:anywhere;word-break:break-word}`. This is a real phone-width defect and the audit missed it. |
| C7 | `.grid` used `minmax(330px,1fr)`, which cannot shrink below 330px. Changed to `minmax(min(330px,100%),1fr)`. `min-width:0` added to `.card` and `.wrap` so scroll containers can actually shrink. |

## Correction to the audit

**C5 was wrong.** The audit said tables at lines 276 and 342 had no `.wrap` parent. All 16 tables were already wrapped. The 320px overflow came from C6 and C7 above, not from unwrapped tables. No change was needed and none was made.

## Verified

Headless Chromium, all 5 tabs, viewports 320 / 360 / 390 / 430 / 560 / 768 / 1280.

- 0 contrast failures. Every text node measured against its painted background, 4.5:1 for normal text and 3:1 for large.
- Smallest rendered text anywhere: 12px.
- 0 horizontal page overflow at every width including 320px.
- 0 JS errors. Arrow keys, Home and End move selection and panel together; roving tabindex correct after each move.
- 16 tables, 0 without a caption, 0 `<th>` without scope.
- 7 tabs and 7 panels, 0 broken `aria-controls` or `aria-labelledby` references.

## Still open, deliberately

B3 hover states on drillable cards · B4 live-region announcement on panel change · D1 15px base type · D4 dark mode · E1 pattern or direct label on stack segments · E2 focusable data-table fallback for charts. All belong in the Django build, not in a static prototype.
