# Build prompt: public landing page with sign-in

**Target:** `web/src/pages/LandingPage.tsx` (React + TypeScript, Ant Design), replacing the current bare login form. Unauthenticated route `/`, redirect to the role's home on successful auth.

**Reference mock:** `design_handoff_youth_employment/Landing_Page_Redesign_v1.html`. High fidelity for structure, spacing, copy and colour. Open it, do not re-derive it.

---

## Rules

1. **Reuse existing tokens.** Every colour, radius and spacing value in the mock already exists in `web/src/styles/base.css` (`--green-*`, `--gold-*`, `--terra-*`, `--ink-*`, `--line`, `--paper`, `--surface`, `--r-card`, `--r-control`, `--s1`–`--s5`). Add no new colour variables. Font stack stays `'Archivo','Noto Sans Ethiopic'`.
2. **Do not invent numbers or thresholds.** Every figure on the page comes from a source below. If you cannot trace one, leave a `# TODO(source)` and ask.
3. **Copy is part of the spec.** Pull the strings into `i18n/strings.ts` with Amharic and Afaan Oromoo keys stubbed. Do not paraphrase the English while wiring it up.
4. **Nothing behind auth leaks.** The page is public. It states what the platform does, never any group, member or woreda data.

## Sections, in order

| # | Section | Content source |
|---|---|---|
| 1 | Top bar: wordmark, language switcher, sign-in anchor | mock |
| 2 | Hero: headline, lede, three trust chips, sign-in card | mock |
| 3 | Stat strip: 15–25 / 8 / 10 / 33 | `DEFINITIONS.md` §3, `LINKAGE_WORKFLOWS.md` |
| 4 | Phase rail: Forming → P1 → P2 → P3 CLA → P4 federation, with gate conditions | `DEFINITIONS.md` §2 phase gates |
| 5 | Module grid: 12 cards | `wlt_module_handoff-2/README.md` §1 scope |
| 6 | Role cards: 6 roles with scope and landing screen | `README.md` §2.2, `DECISIONS.md` |
| 7 | Field conditions: offline, in-country storage, low literacy | `WLT_Build_Spec_v2` §1.2 |
| 8 | Roadmap: Now WLT / Next youth / Later federation | this decision, confirm with FSCO |
| 9 | Footer | mock |

## Sign-in form requirements

- Visible `<label>` on every input. No placeholder-only fields.
- `autocomplete="username"` and `autocomplete="current-password"`. **Do not block paste** — WCAG 2.2 accessible authentication.
- Show/hide password toggle, `aria-pressed`, minimum 44×44px hit area.
- Errors render next to their field, not in a summary at the top. Focus moves to the first invalid field on submit.
- Submit shows a loading state, then success or a single error message. Never fail silently.
- Visible focus ring on every control. Do not remove outlines.
- Field workers use the mobile app, not this form. Keep the note pointing them there.

## Responsive and theme

- Breakpoints at 640, 1000, 1440. No horizontal scroll at 375px.
- Dark mode via the existing token overrides. Every colour comes from a token, never a literal inside a media query.
- `prefers-reduced-motion` respected. Hover transitions 150–300ms.

## Before you start, confirm with the product owner

1. **Wordmark.** The mock uses "Temsalet", taken from the pilot handbook. Confirm whether that is the platform name or only the programme name.
2. **Languages.** English, Amharic, Afaan Oromoo. Confirm against the pilot woredas.
3. **Stat strip figures.** Structural constants, not live counts. Confirm they should not be wired to real data.

---

## Sources

All paths relative to the `Youth Case Management` folder.

| File | What to take from it |
|---|---|
| `design_handoff_youth_employment/Landing_Page_Redesign_v1.html` | the mock itself: layout, spacing, copy, colour usage |
| `wlt_module_handoff-2/DEFINITIONS.md` | §2 phase gate conditions, §3 glossary (CLA, FSCO, ELS, SHG, PAR30, service charge) |
| `wlt_module_handoff-2/README.md` | §1 module scope, §2.2 what the module consumes from core, RBAC boundary |
| `wlt_module_handoff-2/START_HERE.md` | programme framing: PSNP 6, Women's Livelihoods Transformation |
| `wlt_module_handoff-2/workflows/LINKAGE_WORKFLOWS.md` | structural vs service linkage, the 33 steps |
| `WLT_Build_Spec_v2_Registry_Formation_Linkage.md` | §1.2 selection criteria: literacy, device, digital literacy |
| `dashboard_handoff_wlt/prototype/WLT_Dashboard_Prototype_v2.html` | the token set the mock reuses |
| `web/src/styles/base.css` | the live tokens, the authority over the prototype |

Where the mock and `base.css` disagree, `base.css` wins. Where the mock and a spec disagree on a number, the spec wins and the mock is the bug.
