# UI/UX backlog register

Findings from the review of 2026-08-18. Four parallel review agents — visual
rendering, design-system conformance, accessibility, content and information
design — each read the screens as rendered screenshots plus the source. Their
reports were consolidated here; roughly a third of what came back was either
already correct, or a matter of taste, and is recorded under
[Considered and rejected](#considered-and-rejected) so it is not re-litigated.

## Where it stands

67 findings. 20 fixed (`033c171`, `1f875b3`), 5 partially, **42 open**.

| | P1 | P2 | P3 | total |
|---|---:|---:|---:|---:|
| **done** | 10 | 7 | 3 | 20 |
| **open / part** | **9** | **23** | **15** | **47** |
| total | 19 | 30 | 18 | 67 |

23 findings were verified independently (`✔`); the remaining 44 are carried on
the reviewing agent's word (`○`) and should be confirmed before work starts —
several agent claims did not survive checking, and those are listed under
[Considered and rejected](#considered-and-rejected).

The nine open P1s, in the order I would take them:

1. **DS-04** — ~185 hardcoded strings; five form components entirely un-i18n'd.
   Blocks translation of every screen field staff type into. Largest by effort.
2. **LAY-01** — the donor-facing Results table overflows its card on a phone.
3. **COPY-06** — sign-in failure shows the auth library's sentence.
4. **COPY-05** — registry subtitle claims "open case" over a count of any case.
5. **COPY-08** — "Programme rate: —%".
6. **COPY-07** — one case manager, two caseload numbers, neither qualified.
7. **COPY-09** — "Open case" is a status and an action with identical text.
8. **DS-02** — an unsanctioned five-step chart ramp in literal hex.
9. **VIS-04**/**A11Y-08** — phone tab bar active state at 1.81:1, badge colour-only.

## How to read this

| Column | Meaning |
|---|---|
| **ID** | Stable. Quote it in commits and in follow-up work. |
| **Sev** | P1 looks broken / unreadable / wrong. P2 real inconsistency or barrier. P3 polish. |
| **Status** | `done` (commit noted) · `open` · `part` (partially addressed, remainder described). |
| **V** | `✔` verified independently — contrast computed, code read, or driven in a browser. `○` agent-reported, **not** re-verified; confirm before acting. |

Screens were photographed with `scripts/shoot.mjs`, which mints a JWT through
`manage.py` and injects it into `localStorage` — no password, no account
mutation. Re-run it before and after any fix here.

---

## 1. Contrast and visibility

Everything in this section was measured, not judged by eye. The brief's hard
constraint is a cheap LCD at half brightness in Ethiopian sunlight.

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| VIS-01 | P1 | done `1f875b3` | ✔ | Funnel coverage stages drew `--fill-muted-2` on a `--fill-muted` track: **1.04:1**. The two largest non-gating counts (538 each) read as empty rows. Now a green hatch. `--green-100` was rejected as a fix — 1.02:1. | `components/dashboard/panels.tsx` |
| VIS-02 | P1 | done `1f875b3` | ✔ | Focus ring `--green-500` is 5.3:1 on paper but **1.81:1** on `--green-700` and **2.41:1** on `--green-900`, under the 3:1 minimum — and the shell is where a keyboard user lands first. White is 9.5:1. | `styles/base.css` |
| VIS-03 | P1 | done `1f875b3` | ✔ | Timeline bar labels: `--gold-700` on `--gold-500` is **2.32:1**, white on `--cancelled-bar` **2.98:1**. Gold also breaks the token file's own "fill only, never behind text". Ink is ~5.9:1 on both. | `components/referrals/ReferralStackTimeline.tsx` |
| VIS-04 | P2 | **open** | ○ | Phone tab bar: the active tab is `--green-500` on a `--green-700` bar — **1.81:1**, colour alone. The rail deliberately adds a 3px white rule for this reason; the tab bar never got it. | `components/shell/MobileTabBar.tsx` |

## 2. Keyboard and screen reader

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| A11Y-01 | P1 | done `1f875b3` | ✔ | Table rows were mouse-only — Tab went from the last filter chip straight to pagination, skipping all 145 rows. The operable card list is `display:none` above 780px, so on the shared laptop the table was the only rendering. Name cell is now a link (button on Youth). | `pages/{CaseListPage,ReferralsPage,YouthListPage}.tsx` |
| A11Y-02 | P1 | done `1f875b3` | ✔ | No skip link. Ten stops between arriving and page content, on every navigation. | `components/AppLayout.tsx` |
| A11Y-03 | P2 | done `1f875b3` | ✔ | Woreda scope selector had no focus ring. antd moves focus to a hidden inner input; this build names its parts `.ant-select-content`, **not** `.ant-select-selector` — a first fix targeting the latter did nothing. | `styles/base.css` |
| A11Y-04 | P2 | done `1f875b3` | ✔ | Density toggle announced "Comfortable rows, **pressed**" while the table was compact — label was the action, `aria-pressed` the state. | `components/ListPage.tsx` |
| A11Y-05 | P2 | **open** | ✔ | `GlobalSearch` declares `role="combobox"`/`listbox`/`option` with hard-coded `aria-selected={false}`, a `<div>` breaking listbox→option ownership, no arrow keys and no `aria-activedescendant`. `role="option"` on a `<button>` also replaces the button role. **Recommended:** drop the ARIA for `role="search"` + an `aria-live` result count — two lines, and Tab already works. Escape also blurs to `<body>`; it should keep focus in the field. | `components/shell/GlobalSearch.tsx` |
| A11Y-06 | P2 | **open** | ○ | `UserMenu` uses `role="dialog"` but never moves focus in, and the panel precedes the trigger in the DOM — so sign-out and the language switch are reachable only by **Shift+Tab**. Escape and focus-return are already correct. Either make it a menu (`aria-haspopup`, focus first item) or add `aria-modal` and a real trap. | `components/shell/UserMenu.tsx` |
| A11Y-07 | P2 | part | ○ | Dashboard tables lack `scope`, captions and accessible names. Fixed on the headers touched in `WoredaPage`/`MyWorkPage`; **still open** in `ResultsPage` (incl. an empty `<th />`) and `components/dashboard/analytics.tsx`. Worst case: the outcome matrix is a real cross-tab whose row labels are `<td>`, so cells associate with neither axis — the `title` carrying that context is not announced. | `pages/dashboard/ResultsPage.tsx`, `components/dashboard/analytics.tsx` |
| A11Y-08 | P2 | **open** | ○ | Phone alert badge is an 8px gold dot marked `aria-hidden` — colour alone, no number, invisible to a screen reader. The rail renders the count. | `components/shell/MobileTabBar.tsx` |
| A11Y-09 | P2 | part | ○ | `YouthListPage` card is `role="button"` containing a real button (`CasePill`). Nested interactive content, and the `stopPropagation` guard is click-only — Enter on the pill fires **both** the navigation and `openRecord`. The name-cell button (A11Y-01) covers the table; the phone card is unchanged. | `pages/YouthListPage.tsx` |
| A11Y-10 | P2 | **open** | ○ | `lang` is set to `am`/`om` over content that is still English (the tables are deliberately empty and fall back). A screen reader then pronounces English with Amharic phonetics. Set `documentElement.lang` from whether the table has entries; keep each button's own `lang`. | `i18n/LanguageContext.tsx` |
| A11Y-11 | P3 | **open** | ○ | No `aria-live` anywhere. Filtering, searching and paging replace the table silently. A `role="status"` on the result-count line in `PageHeader` would cover all six list screens at once. | `components/ui/index.tsx` |
| A11Y-12 | P3 | **open** | ○ | No `<h2>`/`<h3>` anywhere in the app — every section title is a `CapsLabel` div. Levels are absent rather than skipped, so heading navigation gets one stop per screen. Worst on `CaseDetailPage` (440 lines of cards). Let `CapsLabel` take an `as` prop. | `components/ui/index.tsx` |
| A11Y-13 | P3 | **open** | ○ | Touch targets under the 48px `--touch` token, several phone-facing: `.chip-filter` 40px, `.btn--sm` 34px (pagination), `LanguageSwitch` 36px, `GlobalSearch` input 36px, `.table--compact tbody tr` 36px, tier tabs 44px. | `styles/base.css`, `components/shell/*` |
| A11Y-14 | P3 | **open** | ○ | Smaller: `.table tbody tr { cursor: pointer }` is global, so non-clickable dashboard tables show a hand cursor; the More button lacks `aria-haspopup="dialog"`; `LoginPage` uses `Typography.Title level={4}` as its only heading. | various |

## 3. Wrong or misleading on screen

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| COPY-01 | P1 | done `1f875b3` | ✔ | A column headed **"Woreda"** listed partner names. | `pages/dashboard/MyWorkPage.tsx` |
| COPY-02 | P1 | done `1f875b3` | ✔ | `t("ws.missing", {missing:"", of:""})` rendered **"of  missing"** as a header; the `\|\| "Missing"` fallback could never fire. Two neighbouring headers borrowed another screen's page title, one was a bare `n`. | `pages/dashboard/WoredaPage.tsx` |
| COPY-03 | P1 | done `1f875b3` | ✔ | Gender card read **"51 of 51"** — a denominator restating its numerator. | `components/dashboard/MetricCards.tsx` |
| COPY-04 | P1 | done `1f875b3` | ✔ | Case screen stated "retained at **6 months**". OQ-9 settled on 3 months from exit and dropped the six-month anchor explicitly. | `pages/CaseDetailPage.tsx` |
| COPY-05 | P1 | **open** | ○ | Registry subtitle claims **"with an open case"** but the backend counter is `case__isnull=False` — any case, including exited. The chip beside it says "With a case". Second fault: `count` is the filtered count while `uncased` is unfiltered, so with a search active the subtitle reports search hits as "registered". | `pages/YouthListPage.tsx`, `i18n/strings.ts` |
| COPY-06 | P1 | **open** | ○ | Sign-in failure surfaces simplejwt's **"No active account found with the given credentials"**, and on a 5xx surfaces **"Request failed with status code 500"**. Developer phrasing, and it conflates a typo with a suspended account. | `pages/LoginPage.tsx`, `api/client.ts` |
| COPY-07 | P1 | **open** | ○ | The same case manager is "132 cases" on Users (open only) and "Caseload 145" on Woreda (all statuses). Neither says which. | `pages/UsersPage.tsx`, `pages/dashboard/WoredaPage.tsx` |
| COPY-08 | P1 | **open** | ○ | **"Programme rate: —%"** — a withheld rate rendered as an em dash with a percent sign glued to it. Should go through `RateValue`, which already says "— too few to assess". | `components/dashboard/analytics.tsx` |
| COPY-09 | P1 | **open** | ○ | "Open case" is both a status chip (*this youth has one*) and a button (*navigate to it*), same text, same feature — while elsewhere "open a case" means *create*. | `i18n/strings.ts` |
| COPY-10 | P2 | done `1f875b3` | ✔ | "Waiting" headed a column of medians; "Vs programme" headed a column of costs. | `pages/dashboard/WoredaPage.tsx` |
| COPY-11 | P2 | done `1f875b3` | ✔ | Referrals queue rendered **two empty states at once** — `ListPage`'s and its own leftover card. Regression from the item-6 conversion. | `pages/ReferralsPage.tsx` |
| COPY-12 | P2 | **open** | ○ | Alerts empty state says "No alerts of this type" even with no filter selected, and offers a "Show all alerts" button that does nothing. | `pages/AlertsPage.tsx` |
| COPY-13 | P2 | **open** | ○ | Funnel loss annotation reads backwards: "68 lost (11%) **reaching** Case opened" parses as *lost while reaching*. Use "before {stage}". | `i18n/strings.ts` |
| COPY-14 | P2 | **open** | ○ | Confirmation-lag footnote reads as a contradiction: "from 7 confirmed referrals · 108 recorded by staff" — 108 > 7, with nothing saying staff-recorded ones are deliberately excluded from the median. | `components/dashboard/panels.tsx` |
| COPY-15 | P2 | **open** | ○ | Raw enum codes on screen: `SUSPENDED`, `MALE`, and one panel lowercases alert types from the code (`referral confirmation overdue`) while every other screen uses `*_display`. | `pages/UsersPage.tsx`, `pages/CaseListPage.tsx`, `components/dashboard/panels.tsx` |
| COPY-16 | P2 | **open** | ○ | Three modals ship antd's default **"OK"**; the referral modal says **"Save"** for every §6.2 move, so withdrawing a referral is confirmed by a button labelled Save. Success toast reads "Partner confirmed recorded." | `components/{PartnerFormModal,ReferralActions}.tsx`, `pages/UsersPage.tsx` |
| COPY-17 | P2 | **open** | ○ | "{count} results" on a screen titled Caseload, where every neighbour names its unit; the referrals queue is the only list with no count and its subtitle repeats a heading directly below it. | `i18n/strings.ts` |
| COPY-18 | P3 | **open** | ○ | Terminology drift: overdue alerts are "Needs action today" / "Overdue actions" / "110 overdue" / "Alerts". Title Case status labels ("Referral Pending", "Stall Alert") against a sentence-case UI — note `alerts/models.py` claims §4.13 verbatim, so that is a spec-transcription decision. | `i18n/strings.ts`, backend models |
| COPY-19 | P3 | **open** | ○ | Duplicated text: "Not measurable yet" printed as a heading over a reason that opens with the same words; tile label and panel subtext repeated verbatim on My work and Woreda. | `components/dashboard/panels.tsx` |
| COPY-20 | P3 | **open** | ○ | Unlabelled numbers: `[35–62]` with nothing saying it is a 95% interval; `(+3)` on cumulative rows; "Oldest" over "112d". Dead strings: `empty.alerts*`, `cases.none`, `shell.caseload`. | dashboards, `i18n/strings.ts` |

## 4. Layout and rendering

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| LAY-01 | P1 | **open** | ○ | **Donor-facing.** The Results framework table overflows its card and the viewport at 390px — the Framework column is unreachable past the right edge. Two causes: no `overflowX: auto` wrapper (the two panels in `analytics.tsx` have one), and `whiteSpace: nowrap` on a whole `<td>` that also holds multi-sentence notes. The disaggregation tables below have the same missing wrapper. | `pages/dashboard/ResultsPage.tsx` |
| LAY-02 | P2 | done `1f875b3` | ✔ | `.page` had a max-width and no auto margins, so collapsing the rail freed 176px the content never used — the control appeared to do nothing. | `styles/base.css` |
| LAY-03 | P2 | part | ✔ | Confirmation-lag reference mark sat at exactly 100% and was clipped by the track's overflow — **fixed**. Still open: an empty track is drawn under every "too few to assess" row, which is a chart of nothing. | `components/dashboard/panels.tsx` |
| LAY-04 | P2 | **open** | ○ | The `▲` and its count wrap apart on the Woreda team row — the mark is stranded on one line, the number on the next. Needs `white-space: nowrap` on that span. | `pages/dashboard/WoredaPage.tsx` |
| LAY-05 | P2 | **open** | ○ | Partner response table is crushed into a third of the row: every column wraps, one data row takes ~90px, while the card beside it has empty space. Give it `gridColumn: span 2` as the team and completeness cards already do. | `pages/dashboard/WoredaPage.tsx` |
| LAY-06 | P2 | **open** | ○ | My work KPI numbers do not share a baseline — one tile's caps label wraps to two lines and drops its number 14px. Reserve two label lines in `Tile` and `StatTile`. | `pages/dashboard/{MyWorkPage,WoredaPage}.tsx` |
| LAY-07 | P2 | **open** | ○ | Users on phone: one card puts its caseload below the woreda chips while its siblings put it top-right — `flexWrap` with a `minWidth: 200` left block reflows when the right-hand string is ~20px wider. | `pages/UsersPage.tsx` |
| LAY-08 | P2 | **open** | ○ | **Alerts is the one list screen not on `ListPage`** — no search box, no density toggle, `.stack`'s 16px gaps instead of `.list-page`'s 12px. `ListPage` exists precisely to stop this drift. If alerts has no searchable field, that argues for adding server-side search, not for a second frame. | `pages/AlertsPage.tsx` |
| LAY-09 | P3 | done `1f875b3` | ✔ | Phone cards ran two place names together — "Adama Adama 12". | `pages/{CaseListPage,YouthListPage}.tsx` |
| LAY-10 | P3 | done `1f875b3` | ✔ | Gender bar's 16% segment was silently unlabelled at an 18% threshold, though it measured 50px. | `components/dashboard/MetricCards.tsx` |
| LAY-11 | P3 | **open** | ○ | Referral arrows point two ways — leading `→` on the laptop, trailing on the phone card — and the wrapped partner name has no hanging indent. | `pages/ReferralsPage.tsx` |
| LAY-12 | P3 | **open** | ○ | The Reveal button is vertically centred across the PHONE label and its value, so it reads as attached to neither. | `pages/CaseDetailPage.tsx` |
| LAY-13 | P3 | **open** | ○ | Two warnings on one Woreda row get different treatments — `▲ over ceiling` is a chip, `▲ 110 overdue` is bare red bold text. | `pages/dashboard/WoredaPage.tsx` |
| LAY-14 | P3 | **open** | ○ | On a phone the alerts filter row costs ~240px before the first alert — six long chips, roughly one per line. | `pages/AlertsPage.tsx` |
| LAY-15 | P3 | **open** | ○ | **Latent.** The Woreda caseload bar decides whether a count fits from its share of the manager's own total, while the bar's rendered width is scaled against the largest caseload. A small caseload therefore puts a number inside a few-pixel segment, and the outside-label fallback is keyed off the same threshold so it never fires. `overflow: hidden` currently clips it, so the shipped fault has not returned — it is one CSS property away. | `pages/dashboard/WoredaPage.tsx` |

## 5. Design system conformance

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| DS-01 | P1 | done `1f875b3` | ✔ | `ALERT_TYPE_COLOURS` used antd preset names outside the token layer — including a **blue** the handoff says is deliberately absent, and **red on STALL** where the handoff assigns terracotta and reserves red for genuine failure. | `api/types.ts`, `components/CaseAlerts.tsx` |
| DS-02 | P1 | **open** | ✔ | `HEAT` in the outcome matrix is a **five-step sequential green ramp invented on the spot**, in literal hex, applied as a cell background. CLAUDE.md records that the prototype's `--seq-1..5` chart palette is *not adopted and needs sign-off*. Rebuild from existing steps or get the ramp sanctioned. | `components/dashboard/analytics.tsx` |
| DS-03 | P1 | part | ○ | `CaseAlerts` is the one case-screen component never rebuilt on the token layer — antd `Card`, `Button`, `Space`, `Typography` used **visually**, against "antd keeps behaviour, not looks". The status chip is migrated; the rest is not. It renders directly above `ReferralPanel`, which was rebuilt. | `components/CaseAlerts.tsx` |
| DS-04 | P1 | **open** | ○ | **~185 hardcoded user-facing strings.** Five components are entirely un-i18n'd: `ReferralActions`, `YouthFormModal`, `CaseFormModal`, `PartnerFormModal`, `LocationPicker` — every form label, `extra`, validator message and modal title. As it stands a translator delivering Amharic still gets English on every screen field staff type into. Also the option lists in `api/types.ts` and both pagination controls. Full inventory in the agent report. | many |
| DS-05 | P2 | part | ○ | Status indicators carrying colour + label but **no geometric mark**: `WAIT_TONE`, `VERDICT_TONE` (whose own comment claims a mark that is not in the JSX), `MOU_TONE`, `STATUS_TONE`, the `AlertPanel` chips, and the collapsed-rail dot (which distinguishes "needs attention" by colour alone and is `aria-hidden`). `ALERT_TONE` now has marks in `CaseAlerts` only. | `design/status.ts` and consumers |
| DS-06 | P2 | **open** | ○ | **A second and third breakpoint via antd's grid.** `Row`/`Col` with `xs`/`sm` uses antd's 576px, not the project's single 780px, across `LocationPicker`, `YouthFormModal`, `PartnerFormModal`. Between 576 and 780px every form modal is in its two-column laptop layout while the rest of the app is still phone. Replace with the existing `auto-fit` grids. | form modals |
| DS-07 | P2 | **open** | ○ | Nine `rgba(255,255,255,.x)` overlays on dark green, at five different alpha values, for three jobs — three of them (`.18`, `.18`, `.2`) are the *same* progress track. Add `--on-dark-rule` / `--on-dark-fill` / `--on-dark-track`. | shell + dashboards |
| DS-08 | P2 | done `1f875b3` | ✔ | `.only-laptop` composed onto `.chip-filter` won the cascade and turned the density button into `display: block`. It also slipped past `responsive.test.ts`, which matched the class attribute exactly — guard now widened. | `components/ListPage.tsx`, `styles/responsive.test.ts` |
| DS-09 | P2 | **open** | ○ | `@ant-design/icons` pulled in for three glyphs, when `ICON_PATHS` exists and the rule is inline SVG. Matters for a 3G audience. | `pages/LoginPage.tsx`, `components/CaseAlerts.tsx` |
| DS-10 | P3 | done `1f875b3` | ✔ | `.chip-row` and `.table--compact td` each declared twice; the dead `.chip-row` left a latent `overflow-x: auto` scroller the brief ruled out. `d3-scale`, `@types/d3-scale` and `@fontsource-variable/archivo` declared with zero imports. | `styles/base.css`, `package.json` |
| DS-11 | P3 | **open** | ○ | `ALERT_REASON` is exported, holds six hardcoded English strings and is referenced nowhere. | `design/status.ts` |
| DS-12 | P3 | **open** | ○ | Off-scale inline spacing against the 4·8·12·16·24·32 scale: `gap:10` ×14, `marginTop:10` ×14, `marginTop:6` ×12, and others. ~58 further on-scale values written as numbers where tokens exist. | many |
| DS-13 | P3 | **open** | ○ | `en-GB` hardcoded without the written justification the two documented cases carry — will keep printing Latin dates under an Amharic UI. Two hardcoded radii on legend swatches. | `components/UserDetailModal.tsx`, `pages/UsersPage.tsx` |

## 6. Fixed before the review

| ID | Sev | Status | V | Finding | Where |
|---|---|---|---|---|---|
| ENV-01 | P2 | done `033c171` | ✔ | antd deprecation warnings on every render — `Space direction` → `orientation`, `Alert message` → `title`, seven call sites. Noise that buries real errors; found because `shoot.mjs` now reports console errors on every capture. | five components |

---

## Considered and rejected

Recorded so they are not re-opened.

- **SVG focus ring on timeline bars.** Flagged as uncertain — browsers differ on outlines on SVG `<g>`. Driven in Chromium: the ring **does** paint. No change. Firefox untested.
- **`aria-current={undefined}` on the tier tabs.** Looks like it suppresses the active state; React Router defaults the parameter, so the link does announce as current. The existing comment is correct.
- **antd `Select` missing its `aria-label`.** It is applied — antd lifts `aria-*` onto the inner input.
- **"Sortable headers announce sort state".** Not violated: there is no sorting in the app at all. `aria-sort` has nothing to describe until sorting exists.
- **Bottom padding under the phone tab bar.** The brief asks for it, but the bar is `sticky` inside the main column, not `fixed`, so it already reserves its space — measured at max scroll the last card ends 60px above it. Only `env(safe-area-inset-bottom)` was needed.
- **Modal focus traps.** All eight antd `Modal`/`Drawer` usages inherit antd's trap, Escape and focus return. No change needed.
- **Dashboard bar charts relying on colour.** Every bar carries its count and label as text. Not a violation.
- **The banded-figure copy** — "too few to assess", the provisional asterisk, the `NotYet` reasons, `empty.casesLinked`. Reviewed and deliberately left alone; it is the strongest writing in the app.

## Known limits of this review

- Only **Chromium** was available. No Firefox, Safari or a real Android device.
- Amharic and Afaan Oromoo string tables are empty, so no translated string was
  ever measured for fit. What was tested is the font-stack and leading swap:
  `lang=am` applies the Ge'ez stack at 1.75 leading with no overflow or clipped
  labels at 1440 or 360. **Label fit must be re-checked when a translator
  delivers** — see A11Y-10 and DS-04.
- Screens behind an interaction — most modals, the import flow, the referral
  action dialogs — were reviewed as source, not as pixels.
