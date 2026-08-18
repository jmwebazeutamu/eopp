# Handoff: Partners and Providers Page Redesign

## Overview
Redesigned "Partners and providers" list screen for the EOPP platform (youth employment/case-management admin tool), including the left navigation shell and top bar. The redesign fixes an oversized, inconsistent type scale in the original screen and tightens spacing throughout.

## About the Design Files
The bundled file (`Partners Page.dc.html`) is a **design reference built in HTML** — a working prototype showing intended look, layout, and basic interaction (filter pill selection). It is not production code to copy directly. The task is to **recreate this design in the target codebase's existing environment** (React, Vue, etc., using its established component patterns, state management, and styling approach) — or, if no frontend environment exists yet, choose the most appropriate framework and implement it there.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and component layout are final. Recreate pixel-perfectly using the codebase's existing libraries/design system where equivalents exist (e.g. an existing Button, Badge/Chip, Input, Tag component) rather than introducing new one-off components.

## Screens / Views

### Partners and Providers (single screen, includes app shell: sidebar + top bar)

**Layout**
- Full-height flex row: fixed-width sidebar (232px) + flexible main content area.
- Sidebar: flex column, dark green background, full height.
- Main area: flex column — top bar (56px fixed height) then scrollable content area (padding 28px 32px 40px).
- Content: header row (title + "Add partner" button) → search input → filter pill row (wraps, gap 8px) → vertical list of partner cards (gap 12px).

**Sidebar** (width 232px, background #173629, text #eef2ea)
- Header row: "EOPP" wordmark (15px, weight 700, white, letter-spacing 0.04em) + 24×24px collapse button (1px border rgba(255,255,255,0.25), radius 6px, chevron icon, icon color rgba(255,255,255,0.6)). Padding 18px 18px 14px 20px.
- Global search field: pill-ish rounded rect (radius 8px), background rgba(255,255,255,0.08), padding 8px 10px, search icon + placeholder text "Search youth, cases, partners" at 13px, color rgba(255,255,255,0.55).
- Section label "WORK": 11px, weight 600, letter-spacing 0.08em, color rgba(255,255,255,0.4), padding 18px 20px 6px (first) — this pattern repeats for "DIRECTORY" with padding 2px 20px 6px.
- Nav items (both sections): flex row, gap 10px, padding 8px 10px, border-radius 7px, font-size 13.5px. Default state: icon + label at color rgba(255,255,255,0.82), weight 400, transparent background. Active state (e.g. current page "Partners"): background #2a5240, color #ffffff, weight 600.
  - WORK items: My work, Woreda, Programme, Results, Cases, Referrals, Alerts (icons are simple unicode glyphs in the prototype — replace with the app's actual icon set, ~15-16px, roughly: grid, bar-chart, trending-up/chart, star, folder/case, swap/arrows, bell).
  - DIRECTORY items: Youth registry, Partners (active on this screen), Users.
- 1px divider (rgba(255,255,255,0.1)) with 12px vertical / 20px horizontal margin between WORK and DIRECTORY sections.
- Footer profile row (pinned to bottom via flex:1 spacer above it): 30×30px circular avatar (background #d9a441, initials "PA", color #173629, 12px weight 700) + name "Platform Admin" (13px weight 600, white) / role "System administrator" (11.5px, rgba(255,255,255,0.5)). Top border 1px rgba(255,255,255,0.1), padding 14px 18px.

**Top bar** (height 56px, background #f6f2ea matching page, border-bottom 1px #e9e2d3)
- Right-aligned "All woredas" scope selector: white pill, border 1px #e2dbc8, radius 8px, padding 6px 12px, 13px text (#4a4438) + dropdown chevron (10px, #9b9282).

**Content header**
- Page title "Partners and providers": 22px, weight 700, letter-spacing -0.01em, color #1c2118.
- Subtitle "{count} partners": 13px, color #8c8474, margin-top 3px.
- "Add partner" button (top right): background #173629, white text, no border, radius 8px, padding 9px 16px, 13.5px weight 600.

**Search input**
- Full width, background white, border 1px #e2dbc8, radius 9px, padding 10px 14px, 13.5px, placeholder "Search by name, contact or email" (placeholder color #9b9282).

**Filter pills row** (flex, gap 8px, wraps, margin-bottom 20px)
- Each pill: padding 7px 14px, radius 999px (full pill), 13px weight 600, white-space nowrap, flex-shrink 0.
- Inactive: background #ffffff, text #4a4438, border 1px #e2dbc8.
- Active (currently selected filter, e.g. "All"): background #173629, text #ffffff, border 1px #173629.
- Count shown inline after label at 65% opacity, weight 500.
- Filters: All (6), Accepting referrals (6), Paused (0), No MOU (2), Draft (1), Signed (3).

**Partner card** (repeated per partner; white background, border 1px #ece6d6, radius 12px, padding 18px 20px, 12px gap between cards)
- Header row: category label (11px, weight 600, letter-spacing 0.07em, color #9b9282, e.g. "HEALTH SERVICE") above partner name (16px, weight 700, color #1c2118). MOU status badge top-right: pill, padding 3px 11px, radius 999px, 12px weight 600 — "No MOU" (bg #fbe6e2, text #b3452f), "Signed" (bg #e2f0e6, text #1f7a4d), "Draft" (bg #fbeed9, text #a1701f).
- Detail row: 3-column grid (equal widths, 20px gap), top border 1px #f0ebdd, padding-top 12px:
  1. **Coverage** — label "COVERAGE" (10.5px, weight 600, letter-spacing 0.06em, color #a39a89) + wrapped tag chips (background #f1ece0, radius 999px, padding 3px 10px, 12px, color #4a4438) — one per covered area (e.g. "Adama", "Lume").
  2. **Contact** — label "CONTACT" + contact name (13.5px, weight 600, color #1c2118) + phone number below (12.5px, color #8c8474).
  3. **Status** — label "STATUS" + status row: 6px green dot (#1f7a4d) + text "Accepting referrals" (13px weight 600, color #1f7a4d).

**Sample data (6 partners shown in prototype)**
1. Adama Health Centre — Health Service — No MOU — Coverage: Adama — Contact: Dr Hailu, +251911000003
2. Adama Polytechnic College — TVET Institution — Signed — Coverage: Adama, Lume — Contact: Tigist Bekele, +251911000000
3. Adama Skills Hub — TVET Institution — No MOU — Coverage: Adama — Contact: Test Contact, +251911999999
4. Bishoftu Automotive Plc — Employer — Signed — Coverage: Bishoftu — Contact: Solomon Girma, +251911000001
5. Oromia Credit and Savings — Finance Institution — Draft — Coverage: Adama, Bishoftu — Contact: Almaz Tesfaye, +251911000002
6. Rift Valley Enterprise Agency — Enterprise Development Agency — Signed — Coverage: Adama, Bishoftu, Lume — Contact: Bekele Wolde, +251911000004

All 6 partners have status "Accepting referrals" in the sample data (the "Paused" filter has 0 matches).

## Interactions & Behavior
- **Filter pills**: clicking a pill sets it as the active filter and re-filters the partner card list. "All" shows every partner. "Accepting referrals" filters by status. "No MOU" / "Draft" / "Signed" filter by MOU badge value. Only one filter active at a time (single-select).
- **Search input**: present in the design but not wired to filtering logic in the prototype — implement client-side (or server-side) search across name, contact, and email per the placeholder text.
- **Add partner button**: no destination defined in the prototype — should open a create-partner flow (modal or new screen), consistent with the rest of the app.
- **Sidebar nav items**: static in the prototype; should route to their respective sections. "Partners" is shown in the active state for this screen.
- **Collapse chevron** (top of sidebar): visual only in the prototype — wire to the app's existing sidebar collapse/expand behavior if one exists.
- No hover/focus states, loading states, or error states were defined beyond default browser/button behavior — apply the codebase's standard interactive states (hover, focus-visible, disabled, loading) to buttons, inputs, and pills.
- No responsive/mobile behavior was designed; this is a desktop admin-console screen (designed at 1440px wide).

## State Management
- `activeFilter`: string, one of All / Accepting referrals / Paused / No MOU / Draft / Signed. Drives which partners render.
- `partners`: array of partner records (see fields below) — in a real app this is fetched data, not hardcoded.
- `searchQuery`: string (to be wired up; not implemented in the prototype).
- Partner record shape: `{ category, name, mouStatus: 'no-mou'|'signed'|'draft', coverage: string[], contactName, contactPhone, referralStatus }`.

## Design Tokens

**Colors**
- Sidebar background: #173629
- Sidebar active item background: #2a5240
- Page background: #f6f2ea
- Card / surface background: #ffffff
- Card border: #ece6d6
- Divider (light): #f0ebdd
- Border (inputs/pills, light surfaces): #e2dbc8
- Top bar border: #e9e2d3
- Primary text: #1c2118 / #22281f
- Secondary/muted text: #8c8474, #9b9282, #a39a89
- Sidebar text (default): rgba(255,255,255,0.82); muted: rgba(255,255,255,0.4-0.55)
- Primary action (buttons, active pill): #173629 background / #ffffff text
- Tag chip background: #f1ece0, text #4a4438
- Status green (accepting referrals, signed badge): #1f7a4d text, badge bg #e2f0e6
- Status red (no MOU): text #b3452f, badge bg #fbe6e2
- Status amber (draft): text #a1701f, badge bg #fbeed9
- Avatar accent: #d9a441

**Typography** (font stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif)
- Page title: 22px / weight 700 / letter-spacing -0.01em
- Card name: 16px / weight 700
- Body / contact name: 13.5px / weight 600
- Body default: 13-13.5px / weight 400-600
- Small/meta (phone, subtitle): 12.5-13px
- Micro labels (COVERAGE, CONTACT, STATUS, category): 10.5-11px / weight 600 / letter-spacing 0.06-0.07em, uppercase
- Sidebar section labels (WORK, DIRECTORY): 11px / weight 600 / letter-spacing 0.08em

**Spacing scale used**: 3, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24, 28, 32, 40 (px)

**Radius**: 6px (small controls), 7-9px (nav items, inputs, buttons), 12px (cards), 999px (pills/badges/chips), 50% (avatar)

**Shadows**: none used — the design relies on borders and background contrast, not elevation shadows.

## Assets
No image assets — all icons in the prototype are placeholder unicode glyphs and should be replaced with the app's real icon set (e.g. an existing icon library already in the codebase). No logos beyond the "EOPP" wordmark (text, not an image).

## Files
- `Partners Page.dc.html` — the full design prototype (HTML). Contains the complete layout, all inline styles, and the sample data/filtering logic (in a `<script>` block at the bottom) referenced above. Open it in a browser to view/interact with the design directly.
