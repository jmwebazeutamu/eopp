# UI layer handoff: what the coder gets, and what they owe back

Companion to `README.md`. The README owns what each card means. This file owns how it looks and behaves.

`prototype/WLT_Dashboard_Prototype_v2.html` is the reference implementation. It is accessibility-clean and passes at 320px. Copy its CSS and its tab JS rather than re-deriving them.

---

## Paste this to a coding agent

> Build the WLT dashboards per `dashboard_handoff_wlt/README.md`. Read `wlt_module_handoff/DEFINITIONS.md` first: every formula is defined there and none of them may be recomputed inline in a card. Start with section 3 of the README, the reporting-layer fixes, and do not build a card on a view listed there until its fix is merged. Then build Tier 1 in Django per section 4. Tiers 2 to 4 are Metabase and come after. Card IDs (FC-, WO-, PG-, ME-) are the ticket vocabulary; quote them.
>
> For the UI layer, `prototype/WLT_Dashboard_Prototype_v2.html` is the reference, not v1. Lift its `:root` token block, its component CSS and its tab JS verbatim into the Django template layer. Do not restyle. Read `UIUX_HANDOFF_PROMPT.md` for the six rules that survive the port and the six items the prototype deliberately leaves to you. Every one of them is a definition of done, same weight as the card's data being correct.
>
> `UIUX_AUDIT_v1.md` records why each rule exists. Read it before you argue with one.

---

## Six rules that survive the port

Break any of these and the card ships wrong regardless of whether the number is right.

**1. No hex in a template. Ever.**
Every colour comes from a `:root` variable. Two palettes, never mixed: `--s1` to `--s4` for series, the status set (`--green-*`, `--gold-*`, `--terra-*`, `--red-*`) for state. A status colour used as a series is a defect. A series colour meaning failed is a defect.

**2. Heatmap and ramp cells use the `.l1` to `.l4` classes, not inline backgrounds.**
The classes carry the text colour that keeps the cell readable. `.l1`, `.l2`, `.l3` take dark ink; `.l4` takes white. Setting the background inline reintroduces a 2.1:1 contrast failure.

**3. Every chart graphic is `aria-hidden="true"` and every chart has a text equivalent beside it.**
The prototype pattern: a `.bv` value next to each bar, a `.den` line under each stack, or a legend with counts. Ship the graphic hidden and the numbers visible. If a card has no text equivalent, it is not done.

**4. Every table gets `scope="col"` on each `<th>` and an `sr-only` `<caption>` carrying the card title.**
In Django this is one include, not a per-card decision.

**5. Any interactive control keeps the 2px `:focus-visible` ring and a 44px minimum target.**
The ring switches colour by surface: `--gold-300` on the dark topbar, `--green-700` on light. Do not remove it to make a control look tidier.

**6. Thresholds render from `wlt.policy_parameter`. Never typed into a template.**
This is a README rule, restated because it is the one most likely to be broken by someone copying prototype markup that has the number hardcoded as illustrative data.

---

## Six things the prototype leaves to you

These were deliberately not built into a static file. They are Django work and each needs a ticket.

| ID | What | Why it is yours |
|---|---|---|
| **B3** | Hover and cursor states on every drillable card, plus a visible pressed state | The prototype has no drill-downs. Yours does. Without a hover state users will not find them. |
| **B4** | `aria-live="polite"` status line that announces the tab change and the row count after any filter | The prototype swaps a `hidden` attribute silently. A real filter changing 40 rows to 3 must say so. |
| **E1** | Pattern or direct label on stacked segments, not fill alone | Currently only the legend distinguishes segments. Add a label to any segment over 15% width. |
| **E2** | Focusable data table beside every chart, with sortable headers and `aria-sort` | The accessible fallback. Chart-only is not shippable. |
| **D1** | Decide the base type size | Prototype is 15px, one step under the 16px standard. It reads as a deliberate density choice. Confirm it or move to 16px, but do it once, before cards are built. |
| **D4** | Decide dark mode | No `prefers-color-scheme` block exists. Field use in low light will produce the request. Decide now so tokens are structured for it. |

---

## Two states the prototype cannot show, and you must build

**Loading.** Every card reads a materialised view. Reserve the card's height before data arrives so the grid does not shift. Skeleton, not a spinner.

**Empty and suppressed.** These are different and must look different. A kebele with zero groups is empty. A kebele with three groups is suppressed under the small-count band in README section 2.2. Rendering suppressed as "0" reports a collapse that has not happened. The prototype's hatched `matures Sep` cell is the pattern for "not zero, not yet knowable"; reuse it.

---

## Acceptance, UI layer

Per card, in addition to the README's definition of done:

- [ ] No hex literal in the template
- [ ] Chart graphic `aria-hidden`, numbers visible as text
- [ ] Table headers scoped, caption present
- [ ] Keyboard reachable, focus ring visible, no trap
- [ ] Loading and empty and suppressed states all render
- [ ] No horizontal page scroll at 360px
- [ ] Contrast 4.5:1 for text under 24px, measured not eyeballed

Automate the last two. A headless Chromium check over every card at 360px catches both, and it is the check that found two defects the manual audit of v1 missed.
