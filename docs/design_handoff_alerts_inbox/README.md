# Handoff: Alerts Inbox Redesign (Two Directions)

## Overview
Redesign of the "Alerts" screen for the EOPP platform as a mail/inbox-style interface, replacing the original single-column card list. Two directions were explored and presented to the product owner for selection — **no final pick has been made yet**. Build whichever the team confirms (see below), or ask if unclear.

## About the Design Files
The bundled file (`Alerts Redesign Options.dc.html`) is a **design reference built in HTML** — static mockups showing two layout directions, not production code to copy directly. The task is to **recreate the chosen direction in the target codebase's existing environment** (React, Vue, etc., using its established patterns and components) — or choose the most appropriate framework if none exists yet.

## Fidelity
**High-fidelity** for visual style (colors, type, spacing match the rest of the app). **Structural/exploratory** for interaction — these are static mockups with sample data; no click-through logic was built. Treat row selection, drawer open/close, and filter switching as behavior to implement fresh, following the patterns below.

## Directions

### Option 1a — Split view: label rail + message list + reading pane (Gmail-style)
Three-column layout inside the content area (to the right of the app's main sidebar):
1. **Label rail** (190px): "Alerts" heading, then a vertical list of alert-type filters styled like Gmail labels — each row shows a small colored icon, the label name, and a count, right-aligned. The active label has a highlighted background. Labels: All (408), Stall Alert (57, amber ▲), Referral Confirmation Overdue (6, red ⟲), Follow-Up Due (0, slate ●), Onward Referral Prompt (184, blue ●), Replacement Referral Prompt (161, red ▲, shown active/selected in the mock), Retention Check Due (0, teal ⟲).
2. **Message list** (430px): search field at top, then a scrollable list of alert rows. Each row: small colored type icon, alert subject (person's name, bold), one-line preview text (truncated with ellipsis) combining the alert description and location, and a relative timestamp top-right ("today", "2d", "1d", "3d"). Selected row has a tinted background (#f1ece0).
3. **Reading pane** (flexible width, off-white background #fdfcf9): shows the full selected alert — category label (colored, uppercase, small), person's name (large, bold), location + timestamp, full description text, and two action buttons: "Mark actioned" (primary, dark green fill) and "Dismiss" (secondary, outlined).

**Interaction model**: clicking a row in the message list loads its content into the reading pane (no page navigation) — standard master-detail. Clicking a label filters the message list. Search filters by name/description.

### Option 1b — Dense table with bulk select + side preview drawer
Single main list area with a slide-out detail drawer:
1. **Header**: "Alerts" title + "408 open · All woredas" subtitle, then a horizontal row of pill filters (All, Stall, Overdue, Onward, Replacement, Retention) — same filter set as 1a but as top pills instead of a side rail.
2. **Bulk action bar** (appears when ≥1 row is checked): shows "{n} selected" plus "Mark actioned" and "Dismiss" buttons that apply to all checked rows at once.
3. **Table list** (flexible width): dense rows in a 6-column grid — checkbox, type icon (colored, matches 1a's color/icon coding), name (bold), one-line description (truncated), location, relative time (right-aligned, muted). Rows are checkable individually; row background highlights when checked or selected.
4. **Detail drawer** (360px, fixed right side, off-white background): same content structure as 1a's reading pane — category label, name, location/time, description, action buttons — but sized for a narrower panel.

**Interaction model**: checkboxes drive multi-select and the bulk action bar; clicking a row (not the checkbox) opens/updates the detail drawer for that single alert. Filter pills narrow the table list.

## Shared Visual Language (both options)
- Reuses the app's existing shell: dark green sidebar (#173629), cream page background, white content surfaces.
- **Alert type color/icon coding** (consistent across both directions — carry this token set into whichever is built):
  - Stall Alert: amber #a1701f, icon ▲
  - Referral Confirmation Overdue: red #b3452f, icon ⟲
  - Follow-Up Due: slate #5b6b63, icon ●
  - Onward Referral Prompt: blue #2f5fb3, icon ●
  - Replacement Referral Prompt: red #b3452f, icon ▲
  - Retention Check Due: teal #1f7a6a, icon ⟲
  (Icons are placeholder unicode glyphs in the prototype — replace with the app's real icon set, keeping the color coding.)
- Typography: name/title 13-21px depending on context (bold/700 for emphasis), body/description 12.5-14px, meta/timestamp 11-12.5px muted (#9b9282), category label 10.5-11px uppercase with letter-spacing.
- Primary action button: dark green (#173629) fill, white text, radius 7-8px. Secondary: white fill, #e2dbc8 border, #4a4438 text.
- Card/row radius: 6-8px on containers; rows are flush (divided by 1px #f0ebdd borders) rather than individually carded, unlike the original design's stacked-card list.

## Design Tokens
- Sidebar bg: #173629 · active nav item: #2a5240
- Page/app bg: #f6f2ea / #efece4 (canvas) · content surface: #ffffff, #fdfcf9 (reading pane/drawer), #faf7f0 (rails/toolbars)
- Borders/dividers: #ece6d6, #f0ebdd, #e2dbc8
- Text: primary #1c2118, secondary #4a4438, muted #8c8474 / #9b9282
- Selected/active row tint: #f1ece0
- Status colors: see alert type coding above
- Radius scale: 6px, 7px, 8px · Spacing scale: 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28px

## Assets
No image assets. All icons are unicode placeholders — swap for the app's real icon library, preserving the color-per-alert-type coding above.

## Open Decisions for the Team
1. **Pick a direction** — 1a (three-pane, label rail) suits scanning by alert type; 1b (dense table, bulk actions) suits triaging large volumes quickly. A hybrid (1a's label rail + 1b's bulk-select toolbar) was also suggested and may be worth prototyping.
2. Whether "Mark actioned" / "Dismiss" need confirmation dialogs or are one-click + undo.
3. Real-time behavior: does the list update live as alerts resolve, or is it poll/refresh-based?

## Files
- `Alerts Redesign Options.dc.html` — both directions as an HTML canvas doc (pan/zoom to compare 1a and 1b side by side).
