---
name: design
description: How to build or change any screen in web/ so it matches the design handoff. Use before writing UI code — a new screen, a new component, a layout change, a status colour, a filter, a modal, or anything that renders in the browser. Covers the token layer, the non-negotiable rules from the field brief, the established screen recipes, and the rendering faults that have already shipped here once.
---

# Building UI in this repo

`docs/design_handoff_youth_employment/README.md` is the source of truth. It is
high fidelity and final on colour, type, spacing and interaction states. The
`.dc.html` prototype beside it is reference only — never port it. This skill is
the working summary; open the README when you need a value it does not name.

## Where things are

| What | Where |
|---|---|
| Colour, spacing, radii, elevation tokens | `web/src/styles/tokens.css` |
| Type roles, card/button/chip/table/input classes, `.only-phone` / `.only-laptop` | `web/src/styles/base.css` |
| Chips, buttons, cards, fields, icons, `maskPhone` | `web/src/components/ui/` |
| Status → colour + mark, wait levels, alert tones | `web/src/design/status.ts` |
| Strings and the language switch | `web/src/i18n/` |
| Counter row shared by every list screen | `web/src/components/MiniDashboard.tsx` |
| antd theme mapping | `ANTD_THEME` in `web/src/App.tsx` |

## Non-negotiables

These come from the field brief — 3G or worse, 360px Android, sunlight, shared
offices, personal case data. Breaking one is a defect, not a preference.

1. **No literal hex outside `design/status.ts` and `ANTD_THEME`.** Everything
   else reads a token. Those two are exempt because SVG and antd's theme
   algorithm cannot take a CSS custom property.
2. **Never colour alone.** Every status renders as colour **plus** a label
   **plus** a geometric mark. It has to survive monochrome, colour blindness and
   a cheap LCD at half brightness. When a label truncates, the mark leads it so
   it cannot be the part that is dropped.
3. **Blue is absent. Red is genuine failure only.** Gold carries waiting, terra
   cotta carries stalled. `--gold-500` is fill only, never behind text (2.6:1).
4. **One breakpoint, 780px.** Tables + nav rail above, cards + bottom tab bar
   below. The tab bar is `position: sticky` inside the main column, never
   `fixed`. Touch targets 48px, tab bar 56px.
5. **Personal data is masked by default.** `maskPhone` everywhere; the case
   screen has a per-view, never-persisted reveal, the registry has none.
6. **No icon fonts, no chart libraries, no CDN fonts.** Inline SVG paths,
   `@fontsource` self-hosting. Check the added kB before adding a dependency.
7. **Every user-facing string goes through `t()`.** English is populated;
   `am`/`om` fall back to English rather than showing a key. Adding a language
   is a table, not a screen change.
8. **Ant Design keeps behaviour, not looks.** Modal, Select, DatePicker, Form,
   message stay antd and themed. Anything visual is bespoke in `components/ui`.
   Do not substitute the stack — spec §2 fixes it.

## Screen recipes

**A list screen** (see `CaseListPage`, `YouthListPage`, `ReferralsPage`):

```tsx
<div className="page stack">
  <PageHeader title={t("…")} subtitle={…} action={…} />
  <SearchBox placeholder={t("…")} />
  <MiniDashboard resource="/cases" />        {/* counters that are also filters */}
  <div className="only-laptop">…table…</div>
  <div className="only-phone">…cards…</div>
</div>
```

Filters live in the URL (`useSearchParams`), so a filtered view is shareable and
the back button returns to it. Any filter change clears `page`.

**A counter row** needs a `summary` action on the viewset returning
`{total, counters: [{param, value, label, count}]}`. Build it with
`apps/common/summaries.counters_for`. The server names the query parameter, so a
counter cannot drift from the list it filters to. Counts cover the whole
**scoped** set, never the loaded page.

**A record** opens read-only with an explicit edit step — see
`YouthDetailModal`, `PartnerDetailModal`, `UserDetailModal`. Opening a record is
not the same as changing it, and these records carry a §9 audit trail. Reading
is open to any role that can see the row; only writing is gated.

## Faults that have already shipped here

Check for these before calling UI work done. Each one reached the browser once.

- **An inline `display` beats a media query.** `.only-phone` carried
  `style={{display:"flex"}}`, so on a laptop the table *and* the cards rendered
  and every row appeared twice. Those two classes own their `display` in
  `base.css`; `src/styles/responsive.test.ts` fails if anything sets it inline.
- **A label that does not fit must not escape.** Place it inside the bar
  truncated, else beside it bounded by the next element on that row, else drop
  it and leave the tooltip. An overlapping label is worse than no label. Axis
  labels thin out for the same reason.
- **An object literal prop in a `useCallback` dependency refetches forever.**
  Serialise it (`MiniDashboard`'s `paramKey`).
- **Grouping an annotated queryset corrupts counts.** Prior annotations join the
  `GROUP BY`, splitting or multiplying every count. Count through a subquery on
  the primary keys.
- **`annotate()` drops `Meta.ordering`**, which makes paginated pages overlap.
  Restate `order_by` on any aggregate queryset.
- **Zero-length intervals collide even though the dates say otherwise.** Two
  same-day items land on the same pixel; pack them as though each occupies its
  whole day.

## Before you call it done

```bash
cd web && npm run build   # tsc — the typecheck gate
npm test                  # vitest
npm run lint              # oxlint
```

Then look at it at **both** 360px and 1440px. jsdom applies no stylesheet, so
tests cannot see a responsive-visibility fault — every collision listed above
was found by measuring geometry or by eye, not by a passing suite.

Prefer testing layout arithmetic as a pure module (`timelineLayout.ts` is the
pattern) over asserting on rendered pixels.
