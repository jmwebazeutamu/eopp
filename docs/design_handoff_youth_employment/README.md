# Handoff: Youth Employment Case Management (Oromia, Ethiopia)

## Overview
A case management web app for a World Bank funded youth employment programme in Oromia region, Ethiopia. Field staff register unemployed youth, open a case, refer them to training providers, employers, finance institutions and support services, then track whether the referral turned into a real job, a completed TVET course or a running enterprise.

The design's organising principle: **the visible goal is a young person in paid work six months later, not paperwork completion.** Every screen surfaces a next action and an outcome, not a form status.

Live sites: Adama, Bishoftu, Lume woredas. Geography model is woreda (district) → kebele (ward).

## About the design files
The file in this bundle (`Youth Employment Case Management.dc.html`) is a **design reference created in HTML** — a prototype showing intended look and behaviour. It is **not production code to copy**. It uses a small in-house streaming component runtime (`support.js`), a template dialect and inline styles; none of that should be ported.

The task is to **recreate these designs in the target codebase** (stated stack: React 18 + TypeScript + Vite) using its established patterns. Concretely:

- Lift the token values from the tables below into a real CSS custom property layer (`:root` in a global stylesheet, or the project's theme file).
- Build each component listed under *Component specs* as a real React component with the props implied by its states.
- The prototype's inline styles map 1:1 to the token values; where a literal hex appears in the prototype, it is one of the tokens below.

If you want to run the prototype for reference: open the `.html` file directly in a browser (it needs `support.js` next to it and network access for Google Fonts).

## Fidelity
**High fidelity.** Colours, type sizes, spacing, radii, copy and interaction states are all final and intentional. Recreate pixel-for-pixel using the codebase's own primitives. The only deliberately loose areas:

- No photography or illustration is included (none was available). The design is complete without imagery; if photos are added later, the brief calls for young people working — welding, tailoring, driving, coding, running a shop — never outstretched hands or despair framing.
- The dashboard charts are hand-built bars, deliberately, to keep bundle weight low on 3G. If you swap in a chart library, keep the visual result identical and check the added kB.

## Hard constraints that drove the design (please preserve them)
- **Bandwidth**: users are on 3G or worse. No icon fonts, no image libraries, no chart libraries by default. All icons are inline SVG stroke paths (24×24 viewBox, `stroke-width:1.7`, `currentColor`).
- **Devices**: 360px-wide low-end Android is the common case. Mobile-first; touch targets **48px minimum** (nav tab bar 56px).
- **Sunlight**: contrast must hold at low brightness. Body text AAA where possible, AA minimum everywhere. Contrast ratios are documented per token below.
- **Language**: English, Amharic (Ge'ez) and Afaan Oromo (Latin). Typeface: **Archivo** (Latin) + **Noto Sans Ethiopic** (Ge'ez). Ge'ez runs at `line-height: 1.75` against Latin's `1.5`, and the font stack swaps order per language.
- **Data density**: case managers carry 80–200 youth. List views must stay scannable at that volume.
- **Offline**: queued / syncing / failed-to-sync states are part of the UI, not a toast.
- **Personal data**: shared offices and shoulder-surfing. Phone numbers are masked by default (`+251 9•• •• 22 07`) with an explicit Reveal action.
- **Never colour alone**: every status pairs a colour with a **label** and a **geometric mark**. This survives monochrome screens and colour-blind readers.

## Screenshots
`screenshots/` — 1440px unless noted.

| File | Screen |
|---|---|
| `01-laptop.png` | Case detail (the core screen) |
| `02-laptop.png` | Cases list |
| `03-laptop.png` | Referrals queue |
| `04-laptop.png` | Alerts |
| `05-laptop.png` | Programme dashboard |
| `06-laptop.png` | Partners and providers |
| `07-laptop.png` | Design tokens / component specs / rationale |
| `01-variant.png` | Cases list in Amharic (Ge'ez) |
| `02-variant.png` | Case detail at 360px |
| `03-variant.png` | Cases list at 360px |
| `04-variant.png` | Referrals queue at 360px |

Youth registry and Users have no screenshot; both are simple card lists described below.

---

## Design tokens

### Colour
Ratios are against `#FFFFFF` unless the note says otherwise. `--green-700` is the primary; **blue is deliberately absent** and **red is reserved for genuine failure**, never brand.

| Token | Hex | Contrast | Use |
|---|---|---|---|
| `--green-900` | `#0A3A2C` | 15.4:1 | Goal panel, top utility bar, dashboard hero |
| `--green-700` | `#0F4F3C` | 10.6:1 | Primary buttons, nav rail, active filter fill, Completed chip fill |
| `--green-500` | `#1C7A5B` | 4.9:1 | Active referral bar, active nav item, woreda bars |
| `--green-100` | `#E4EFE9` | 12.9:1 with `--ink-900` | Active/verified chip background |
| `--green-border` | `#9CC4B4` | — | Border on green-100 chips |
| `--green-ink` | `#0B4A38` | 8.9:1 | Text on green-100 |
| `--gold-700` | `#7A5308` | 7.6:1 | Waiting/due text, gold chip text |
| `--gold-500` | `#C98A15` | 2.6:1 | **Fill only, never behind text** — pending bars, gold progress |
| `--gold-300` | `#E9C877` | — | Accent on dark green (logo mark, eyebrow labels, hero progress) |
| `--gold-100` | `#FBF1DC` | 13.9:1 with ink | Next-action banner, pending chip background |
| `--gold-border` | `#E0BC72` | — | Border on gold-100 |
| `--terra-700` | `#8A3A1E` | 7.9:1 | Stalled text, barrier warnings, slot-limit chip text |
| `--terra-500` | `#A84B2A` | 5.6:1 | Replaced state bar, stall alert tone |
| `--terra-100` | `#F7E7DF` | 13.1:1 with ink | Stalled chip background |
| `--terra-border` | `#DBA98F` | — | Border on terra-100 |
| `--red-700` | `#8C1D18` | 9.2:1 | Failed text, destructive button fill, overdue badge text |
| `--red-500` | `#B3261E` | 6.3:1 | Failed state bar |
| `--red-100` | `#FAE6E4` | 13.7:1 with ink | Failed chip background, overdue badge background |
| `--red-border` | `#DCA6A2` | — | Border on red-100, destructive secondary button |
| `--ink-900` | `#1A1915` | 15.9:1 on paper | Body text, toast background |
| `--ink-600` | `#4E4A42` | 8.7:1 | Secondary text |
| `--ink-400` | `#7A7568` | 4.6:1 | Labels, meta, muted text |
| `--line` | `#E3DED2` | — | Card and control borders |
| `--line-soft` | `#F4F1EA` | — | Row rules inside cards |
| `--paper` | `#F7F4EE` | — | App background |
| `--surface` | `#FFFFFF` | — | Cards, tables |
| `--surface-alt` | `#FCFBF8` | — | Table header, closed/inactive cards |
| `--fill-muted` | `#F1EEE7` | — | Neutral badge, bar tracks |
| `--fill-muted-2` | `#EDEAE1` | — | Cancelled chip, count badge |

Dark-surface text colours: `#FFFFFF` for primary, `#D8E4DE` for secondary on `--green-700`/`--green-900`, `#B9CFC6` for tertiary.

### Type
`Archivo` for Latin, `Noto Sans Ethiopic` for Ge'ez. Stack order swaps with language:

```css
/* en, om */ font-family: 'Archivo', 'Noto Sans Ethiopic', sans-serif; line-height: 1.5;
/* am     */ font-family: 'Noto Sans Ethiopic', 'Archivo', sans-serif; line-height: 1.75;
```

Weights loaded: 400, 500, 600, 700. All numerals in tables and metrics use `font-variant-numeric: tabular-nums`.

| Role | Size / line-height | Weight | Notes |
|---|---|---|---|
| Display (case name) | 28 / 1.2 | 700 | `letter-spacing: -.01em` |
| Screen title | 24 / 1.25 | 700 | |
| Metric | 44 / 1.05 | 700 | tabular numerals |
| Metric small | 32 / 1 | 700 | alert counters |
| Card title | 17 / 1.35 | 600 | |
| Body / phone list title | 15–16 / 1.5 | 400–600 | 16px on inputs to stop iOS zoom |
| Table + meta | 13 / 1.45 | 400–700 | |
| Label caps | 11 / 1.3 | 700 | `letter-spacing: .06em; text-transform: uppercase; color: --ink-400` |
| Micro (tab bar) | 9 | 600 | |

### Spacing, radii, elevation
- Spacing scale: **4 · 8 · 12 · 16 · 24 · 32**. Card padding 14–16px; laptop page padding `28px 32px`; phone page padding `14px`.
- Radii: **6** controls · **8** buttons · **10** chip groups and banners · **12** cards · **14** modal · **999** chips.
- Elevation: flat `1px solid --line` (default for cards — no shadows in the content area) · raised `0 1px 2px rgba(26,25,21,.08), 0 2px 6px rgba(26,25,21,.06)` · overlay `0 8px 24px rgba(26,25,21,.28)` (modal, toast).
- Breakpoint: **780px**. Below it, phone layout (cards + bottom tab bar); at or above, laptop layout (nav rail + tables).

### Status system
Every status = colour + label + mark. Marks are text glyphs, not icons.

| Case status | Mark | Text | Background | Border |
|---|---|---|---|---|
| Active | `●` U+25CF | `--green-ink` | `--green-100` | `--green-border` |
| Referral Pending | `◔` U+25D4 | `--gold-700` | `--gold-100` | `--gold-border` |
| Stalled | `▲` U+25B2 | `--terra-700` | `--terra-100` | `--terra-border` |
| Placed | `✓` U+2713 | `#FFFFFF` | `--green-700` | `--green-700` |
| Closed | `■` U+25A0 | `--ink-600` | `--fill-muted-2` | `#D2CCBE` |

| Referral state | Mark | Text | Background | Border | Timeline bar |
|---|---|---|---|---|---|
| Pending confirmation | `◔` | `--gold-700` | `--gold-100` | `--gold-border` | `--gold-500` |
| Active | `●` | `--green-ink` | `--green-100` | `--green-border` | `--green-500` |
| Completed | `✓` | `#FFFFFF` | `--green-700` | `--green-700` | `--green-700` |
| Failed | `✕` U+2715 | `--red-700` | `--red-100` | `--red-border` | `--red-500` |
| Replaced | `↻` U+21BB | `--terra-700` | `--terra-100` | `--terra-border` | `--terra-500` |
| Cancelled | `⊘` U+2298 | `--ink-600` | `--fill-muted-2` | `#D2CCBE` | `#9B9587` |

---

## Screens

### 1. Case detail — the core screen
**Purpose**: a case manager decides what to do next for one young person, and records what partners said.

Layout (laptop): single column, max content width = viewport minus nav rail, `28px 32px` padding.
1. **Header row** (`flex`, wrap, gap 16): left block — eyebrow label `Case YE-OR-AD-04821 · Adama woreda`, 28px name, then a status chip and pathway line. Right block — **goal panel**, `min-width:230px`, `--green-900` fill, radius 12, padding `14px 16px`: gold eyebrow `Goal: paid work retained at 6 months`, target dates, a 6px progress track (`rgba(255,255,255,.2)`) filled 62% in `--gold-300`, then `Step 3 of 5 · TVET done, employment pending`.
2. **Next action banner**: `--gold-100` on `--gold-border`, radius 10, padding `14px 16px`. Caps label `NEXT ACTION`, 16px/600 action sentence, 13px `--gold-700` meta (`Referral RF-9127 · waiting 22 days · overdue by 8 days`), and a 48px primary button `Send reminder`. No left accent rail.
3. **Two cards side by side** (`grid`, `repeat(auto-fit, minmax(280px,1fr))`, gap 16): *Youth identity* (2-col grid of label/value pairs; phone row with mask + Reveal button; consent line) and *Profiling & eligibility* (5 criteria rows, label left, verified state right — `✓ Verified` green, `◔ Self-reported` gold, `◯ Not required` muted — then a barrier note).
4. **Parallel referral slots card**: caps heading + a terracotta chip reading `2 of 2 parallel referrals in use`; a `repeat(auto-fit,minmax(200px,1fr))` grid of slot cards (Slot 1, Slot 2, then a dashed-border Exempt card); footer row with the sentence *Complementary Service referrals are exempt — they never use a slot* and a disabled-looking `+ New referral (blocked)` button that toasts why. Each slot card shows an 8px state dot next to its state word.
5. **Referral timeline 2026**: horizontal scroll container, inner `min-width:660px`. Month labels Jan–Oct across the top offset by the 70px track-label gutter. Three fixed tracks — **Slot 1, Slot 2, Exempt** — each row: 70px caps label, then a 22px lane with `repeating-linear-gradient(90deg,#F7F4EE 0 1px,transparent 1px 10%)` month gridlines and absolutely positioned 18px bars (`left`/`width` in %, radius 5, state colour, centred mark glyph, `title` = full label). **Under each lane, the full labels render as text** (`mark + name + date span`, 12px/600 in the state ink colour) — bars are never relied on to carry text. Legend row underneath.
6. **Referral history**: stacked cards, gap 10. Each card: flat `1px --line` border (no accent rail), radius 12, padding `14px 16px`. Top row — caps `KIND · RF-ID`, 17px partner name, state chip right. Meta row — slot badge (`Slot 1` / `No slot used`) on `--fill-muted`, period text, and, when overdue, `waiting 22 days` in `--red-700` on `--red-100`. Body — one detail sentence. Overdue cards additionally show three 48px buttons: `Partner confirmed` (primary), `Partner declined` (destructive secondary), `Withdraw referral` (secondary).
7. **`Show 3 closed referrals`** toggle revealing Failed / Replaced / Cancelled cards on `--surface-alt`.

Phone: same order, single column, 14px padding; the timeline scrolls sideways; cards stack.

### 2. Cases list
**Purpose**: find a youth in a caseload of 80–200 and see what each needs next.

- Header: 24px `Caseload`, `12 results · Chaltu Tadesse`.
- **Sticky filter bar** (`--paper` background, `z-index:3`): 48px search input (`Search by name, phone or ID`, 16px text), then two horizontally scrolling chip rows — woreda (All / Adama / Bishoftu / Lume) and status (All + the four case statuses with their marks). Active chip = `--green-700` fill, white text. Chips, not dropdowns, on phone.
- **Laptop**: table in a card. 13px, tabular numerals, `1px --line-soft` row rules, **no zebra striping**, header on `--surface-alt`. Columns: Name (name 14/600 + `ID · age · sex` in `--ink-400`), Status (chip), Woreda (`Adama · Kebele 04`), Case manager, Last activity, Next action. Whole row is the click target.
- **Phone**: cards, gap 8, `min-height:48px`, padding `12px 14px`. Name 16/600 with the status chip right; `ID · age · woreda kebele` meta; a rule, then `Next action: …`; then `Last activity: …`. This is a purpose-built card, not a shrunken table.

### 3. Referrals queue
**Purpose**: decision inbox — clear waiting referrals in batches.

Three groups in this order: **Needs a decision**, **Awaiting confirmation**, **Active**. Group heading = caps label + count badge on `--fill-muted-2`. Each row card: youth name 16/600, `Kind → Partner`, `RF-ID · woreda`, and a **waiting-time badge** right-aligned whose tone escalates: `over` = `--red-700` on `--red-100`, `warn` = `--gold-700` on `--gold-100`, `ok` = `--ink-600` on `--fill-muted`. Below, three equal 48px buttons that wrap on phone: `Partner confirmed`, `Partner declined`, `Withdraw referral`.

### 4. Alerts
- Six **counter cards** in a `repeat(auto-fit,minmax(160px,1fr))` grid: 32px count in the tone colour, 13px name, 11px reason line (`No activity for 30 days`). Flat border; the active filter card borders `--green-700`. Tapping filters the list and toggles off on second tap. Types and tones: Stall Alert (terracotta, 14), Referral Confirmation Overdue (gold, 9), Follow-Up Due (green, 22), Onward Referral Prompt (green, 6), Replacement Referral Prompt (terracotta, 3), Retention Check Due (gold, 11).
- **List** below: rows with a caps kind label in the tone ink, youth name 16/600, meta line, and an age badge (`22 days`, `due 14 Sep`, `today`).
- **Empty state** (shown when a filter has no rows): centred card with a habesha-border-derived pattern at **12% opacity** (`repeating-linear-gradient` in green and gold, `pointer-events:none`), a 44px green check, `No alerts of this type`, one sentence of explanation, and a `Show all alerts` button. Pattern appears here and nowhere under data.

### 5. Youth registry
`repeat(auto-fill,minmax(280px,1fr))` card grid. Each: name 16/600, a pill reading `Open case` (green) or `No case` (muted), meta line `ID · age · sex · woreda kebele`, then a rule and two lines — `Phone: +251 9•• •• •• ••` (always masked here) and `Consent: 14 Jan 2026`. Header line: `4,812 registered · 3,940 with an open case. Phone numbers hidden by default.`

### 6. Partners and providers
Stacked cards. Caps type label (TVET institution, Employer, Finance institution, Health centre, Enterprise agency), 17px name, **MOU chip** right (`Signed` green / `Draft` gold / `No MOU` terracotta), then a `repeat(auto-fit,minmax(180px,1fr))` grid: Coverage woredas, Contact, Live referrals, and accepting state (`● Accepting referrals` green / `○ Paused` muted).

### 7. Users
Stacked rows: name 16/600, role, geographic scope; right-aligned load (`132 cases`) and last-seen (`active now`, `offline · 6 queued`). Roles present: Youth case manager, Outreach worker, Woreda supervisor, Partner staff, System administrator.

### 8. Programme dashboard (new screen, designed here)
For supervisors and the donor.
- **Three metric cards**: *Placements this quarter* on `--green-900` (44px `148`, `of 180 target · 82%`, gold progress bar); *Retained at 6 months* on white (44px `742` in `--green-700`); *Gender split of placements* — a single 34px stacked bar, 46% `--gold-500` / 54% `--green-700` with inline labels, plus the note that registration is 51% women.
- **Registration → placement funnel**: six labelled rows, each a 16px track with a fill; colours step from `--green-900` through `--green-500` to `--gold-500` as the funnel narrows. Registered 4,812 (100%) → Case opened 3,940 (82%) → Referred 3,102 (64%) → Partner confirmed 2,455 (51%) → Placed or completed 1,286 (27%) → Retained at 6 months 742 (15%).
- **Confirmation lag by partner**: 12px gold bars, days from referral sent to partner decision, with the note *Programme standard is 14*. Values 2 / 4 / 6 / 11 / 15 days.
- **Woreda comparison**: per woreda, name + placement rate, a 20px `--green-500` bar, and `registered · placed` beneath. Adama 29%, Bishoftu 27%, Lume 22%.

### 9. Design tokens screen (in-app reference)
Swatch grid with hex and contrast ratio per token, the type scale rendered in both scripts, spacing/radii/elevation specimens, the component spec list, and the rationale. Keep it or drop it — it is documentation, not product.

---

## Interactions & behaviour

- **Navigation**: laptop = 236px `--green-700` rail, 44px items, active item `--green-500` fill; footer block with the signed-in user and caseload count. Phone = 56px bottom tab bar, `position: sticky; bottom: 0` **inside the main column** (not `position: fixed` — fixed escapes a constrained shell), icon-only, active item `--green-500`.
- **Language toggle** (`EN` / `አማርኛ`) swaps every string, the font stack and the line-height. Youth and staff names have Ge'ez forms; `Next action` and `Last activity` values are localised too — a half-translated row is a bug, since that column is the scanning target. Afaan Oromo uses the Latin stack and needs a third string table.
- **Offline / sync**: a full-width strip under the header, tinted per state and pulsing its 8px dot (`@keyframes pulse`, 1.6s). States: **queued** — gold, `3 changes queued — will send when online`; **syncing** — green, `Syncing 3 changes…`; **failed** — red, `2 changes failed to sync — retry`. In the prototype the strip cycles on tap; in production it reflects the real queue and the failed state must offer a retry.
- **Privacy**: phone numbers render as `+251 9•• •• 22 07` until Reveal is pressed; the registry never reveals. Treat reveal as a per-view, non-persistent toggle.
- **The parallel-referral rule**: at most **2** referrals may run at once; **Complementary Service referrals are exempt**. This is expressed three ways, none of them a paragraph: the slot cards, the `2 of 2 parallel referrals in use` chip, and the third timeline track literally labelled *Exempt*. When the limit is reached, `+ New referral` stays visible but blocked and toasts `Parallel limit reached — close or withdraw a referral first`.
- **Partner decline** opens a modal: title `Record partner decline?`, body stating the consequence — *RF-9127 closes as Failed, the slot frees up, and a Replacement Referral Prompt is created for this youth. The partner is notified.* — and two buttons, `Record decline` (`--red-700` fill) and `Keep waiting`. Consequences go in the body, never the title. Max two actions.
- **Toast**: `--ink-900`, radius 10, overlay shadow, centred above the tab bar, ~3s, `@keyframes rise` (`translateY(10px)` → 0, 180ms ease-out). Always paired with a state change already visible on screen.
- **Filters** are AND-combined (woreda AND status AND query). Search matches name, ID and phone. Alert counters toggle.
- **Responsive**: single 780px breakpoint. Tables → cards, rail → tab bar, page padding 28/32 → 14. The prototype also has a `360 / 1440 / Auto` chrome for reviewing both widths; **do not port that** — it is a review affordance.
- **Hover/focus**: the prototype leaves these to the platform. Add them in code: rows and cards hover to `--surface-alt`, primary buttons darken to `--green-900`, and every interactive element needs a visible focus ring (2px `--green-500`, 2px offset) — field staff use shared laptops with keyboards.

## State
Prototype-level state, to be re-homed appropriately (URL, server cache, local component state):

| State | Values | Belongs in |
|---|---|---|
| `screen` | dash · cases · case · queue · alerts · registry · partners · users | Router |
| `caseId` | case identifier | Route param |
| `lang` | en · am · om | App-level, persisted |
| `woreda`, `status`, `q` | filters on the cases list | URL query params (shareable, survives back) |
| `alertFilter` | alert type or All | URL query param |
| `reveal` | boolean, phone unmasked | Component state, never persisted |
| `closedOpen` | boolean, closed referrals shown | Component state |
| `sync` | queued · syncing · failed + queue length | Offline queue (service worker / IndexedDB) |
| `toast`, `modal` | transient | UI layer |
| `density` | comfortable · compact (row padding 14px vs 8px) | User preference |
| `parallelLimit` | number, default 2 | **Server-side programme rule**, not a client constant |

Data fetching: the cases list must paginate or virtualise at 80–200+ rows on a low-end Android. Referral state changes (confirm / decline / withdraw) must be queueable offline and idempotent on replay — the same `RF-` decision replaying twice cannot create two outcomes.

## Assets
- **Fonts**: Archivo and Noto Sans Ethiopic, Google Fonts, weights 400/500/600/700. Self-host both for the 3G case; subset Latin and Ethiopic separately.
- **Icons**: inline SVG only, nine nav glyphs plus a check and a chevron, all in the prototype markup — copy the `d` attributes straight out.
- **Logo mark**: a placeholder — 30×30 rounded square in `--gold-300` with a `--green-900` mountain path. Replace with the real programme mark.
- **No images**. The habesha-border pattern in the empty state is pure CSS gradient.

## Files
- `Youth Employment Case Management.dc.html` — the design reference, all nine screens, both languages, both breakpoints. Values live in the markup's inline styles and in the two data blocks in its script (sample data, status maps).
- `support.js` — the prototype's runtime. Reference only; do not port.
- `screenshots/` — see the table above.

Sample data in the file is realistic and safe to reuse for fixtures: Getachew Tolera Wakjira, Chaltu Tadesse, Hanna Girma, Bishoftu Automotive Plc, Adama Polytechnic College, Oromia Credit & Saving S.C., Adama Health Centre 03, Lume Enterprise Development Agency.

## Rationale, in brief
Deep programme green at 10.6:1 stays readable on a cheap LCD at half brightness outdoors. Gold carries waiting and due states because it reads as time passing rather than danger, and it never sits behind text below 7.6:1. Terracotta, from highland building clay, carries stalled cases — intervention without red's alarm. Red is reserved for genuine failure, so a failed placement still stands out on a screen that already has colour on it. Archivo pairs with Noto Sans Ethiopic because the two share a wide, low-contrast skeleton, so a bilingual table does not change weight when the language changes.

Rejected: a blue primary (generic government software, clashes with the gold); the flag palette used literally; woven pattern behind content; and status signalled by colour alone.
