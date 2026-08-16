# Youth Employment Case Management and Referral Platform

Guidance for Claude Code working in this repository.

## What this is

Case management and referral engine for the World Bank Ethiopia youth employment
pilot (500–1,000 youth, ~20 users, 2–3 woredas). Custom-built Django application.

**`docs/YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md` is the authoritative specification.**
Read it before writing code. Section references throughout this file point at it.

Its own rules, which take precedence over anything here:

1. Build in the sprint order of spec §10. Do not create a later sprint's entities
   before an earlier sprint's foundations exist.
2. Spec §4 is the source of truth for the schema.
3. Spec §6 is the source of truth for referral business logic. Unit test every
   transition in the §6.2 table before calling a sprint done.
4. The stack in §2 is fixed. Do not substitute a framework, database, or hosting
   approach without asking.
5. Do not silently resolve anything in §11 (Open Questions). Either ask, or
   implement the stated working default and leave `# TODO(open-question)`.
6. The referral state machine is explicit application code in the domain layer —
   never database triggers or stored procedures.

## Stack (fixed by spec §2)

Django 5.2 + DRF · PostgreSQL 16 · Celery + Redis · MinIO · Traefik · JWT
(simplejwt) · drf-spectacular · React + TypeScript + Ant Design (`web/`, Sprint 3+)
· Flutter + Drift (`mobile/`, Sprints 8–9) · Metabase (Sprint 7) · Docker Compose.

## Commands

All backend commands run inside the container. There is no host virtualenv.

```bash
cd infra
C="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

$C up -d --build            # start the stack
$C ps                       # service status
$C logs -f web              # tail a service
$C down                     # stop (add -v to drop volumes)

$C exec web python manage.py migrate
$C exec web python manage.py makemigrations
$C exec web python manage.py createsuperuser
$C exec web python manage.py shell

$C exec web pytest                                   # all tests
$C exec web pytest apps/users -k rbac -v             # one area
$C exec web pytest --cov=apps --cov-report=term-missing

$C exec web black . && $C exec web isort .           # format
$C exec web flake8 .                                 # lint
```

Reference data:

```bash
$C exec web python manage.py seed_locations          # Ethiopian admin hierarchy, idempotent
$C exec web python manage.py seed_referral_taxonomy  # §5 starter lists
```

Demo data (development only — it writes youth and case records, and refuses to
run with `DEBUG` off unless forced):

```bash
$C exec web python manage.py seed_demo_referrals            # six backdated cases
$C exec web python manage.py seed_demo_referrals --refresh  # delete and rebuild
$C exec web python manage.py seed_demo_referrals --reset    # delete only
```

One case per shape the §6.4 timeline has to draw — sequential chain, parallel
pair plus an exempt third stream, failure and replacement, three onward hops,
pending and cancelled, and an empty case. Referrals go through `services` and
`transition_to`, so the rows are the ones the application would produce; only
the dates are seeded. Case ids are `uuid5`-derived, so `--refresh` keeps the
same URLs.

Frontend (`web/`, runs on the host, not in a container):

```bash
cd web
npm install
npm run dev        # Vite on 8100, proxies /api -> localhost:8007
npm run build      # tsc -b && vite build — this is the typecheck gate
npm test           # vitest, jsdom — layout logic and component rendering
npm run lint       # oxlint
```

`scripts/bootstrap.sh` does first-run setup end to end (generates `infra/.env`,
builds, migrates). Idempotent.

**Always pass both `-f` files.** `docker-compose.yml` alone is the deployed
configuration and carries no development defaults — a bare `docker compose up`
in `infra/` would try to run production settings.

## Ports

Registered in `~/PORTS.md` (VM-wide allocation — add a row there BEFORE exposing
a new port).

| Port | What |
|---|---|
| 8007 | Traefik → Django (API, admin, docs) |
| 8008 | MinIO console |
| 8009 | Metabase (Sprint 7, not yet running) |
| 8100 | Vite dev server (`web/`) |
| 5407 | Postgres |
| 6307 | Redis |

Entry points: `/admin/`, `/api/docs/`, `/api/schema/`, `/healthz/`, `/api/v1/`.

## Layout

```
backend/     Django + DRF
  config/      settings/{base,development,production}.py, celery.py, urls.py
  apps/        one app per entity group, in spec §10 sprint order
web/         React + TypeScript + Ant Design
mobile/      Flutter
infra/       compose files, traefik/, multipass/ cloud-init
docs/        the spec
scripts/     bootstrap.sh
```

`apps/common` is not a spec entity — it holds the abstract base models
(`UUIDModel`, `TimeStampedModel`, `BaseModel`) and the health endpoint.

## Conventions

- **UUID primary keys on every entity.** Spec §4 maps `System ID` to
  `UUIDField(primary_key=True, default=uuid4, editable=False)`. Inherit
  `apps.common.models.BaseModel`.
- **Enums are `TextChoices`**, never bare strings or integer codes.
- **`created_at` / `updated_at` on everything.** The mobile client's
  `updated_since` delta sync (Sprint 8) reads `updated_at`.
- **Audit via `django-simple-history`.** Add `history = HistoricalRecords()` to
  any entity carrying case data. Spec §9 requires date, actor, and rationale on
  every status or pathway change — not only case reviews.
- **RBAC reads `apps/users/models.ACCESS_MATRIX`**, transcribed from spec §7.
  Never test roles inline at a call site. Viewsets use `ScopedQuerySetMixin` and
  declare `woreda_field` / `case_manager_field` / `partner_field`.
- **Scoping fails closed.** A viewset that omits a field its user's scope needs
  gets an empty queryset, never an unfiltered one. These are personal case
  records; an over-broad filter is a data protection incident, not a bug.
- **Taxonomy is configuration, not code** (spec §9). `referral_category`,
  `outcome_type`, and `failure_reason_code` must be editable through the admin
  by the system administrator, with changes logged.
- **Line length 120.** black + isort (black profile) + flake8. Migrations excluded.
- **Timezone `Africa/Addis_Ababa`**, stored UTC.
- Every user-facing string goes through `gettext`, including the English baseline.

## Open questions (spec §11)

Working defaults are implemented and flagged `# TODO(open-question)`. Do not
resolve these silently — they need Phase 1 sign-off:

- Complementary Service referrals sit **outside** the two-referral parallel cap
  (`COMPLEMENTARY_SERVICE_EXEMPT_FROM_PARALLEL_CAP = True`, spec §6.3).
- `STALL_ALERT_THRESHOLD_DAYS = 30`, `REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7`,
  `CASELOAD_CEILING = 50` — placeholders, not agreed values.
- `vulnerability_index_score` methodology undefined (spec §4.3).
- `failure_reason_code` list is a starter, pending frontline validation (§5.4).
- Offline conflict resolution rules undecided (§9, blocks Sprint 9).
- `YOUTH_AGE_MIN = 15` / `YOUTH_AGE_MAX = 29` — §4.1 requires an age band but
  never states it. Out-of-band registration warns rather than blocks, so staff
  are not pushed into falsifying a date of birth.
- The seeded woredas in `seed_locations` are illustrative. The actual 2-3 pilot
  woredas are a programme decision.

Marked `# TODO(spec-gap)` rather than `# TODO(open-question)`: values the spec
names but never enumerates — `education_level` and `disability_status` (§4.1).
These need validation, but they are not on the §11 list.

## Sprint status

- **Sprint 0 — done.** Monorepo, Compose stack, Django skeleton, User + the ten
  roles, RBAC scaffolding, JWT, CI.
- **Sprint 1 — done.** Youth (§4.1) with consent capture and age-band check,
  Case (§4.2) with denormalised woreda and `last_activity_date`, location
  reference data, admin, and the React case list / case detail screens.
- **Sprint 2 — done.** Profiling and Eligibility (§4.3), Pathway Assignment with
  revision history and a one-current-per-case database constraint (§4.4),
  Partner (§4.11), `User.partner` FK with partner-institution scoping, user
  management and partner screens.
- **Sprint 3 — done.** Referral entity (§4.6), taxonomy as admin-editable lookup
  tables (§5, §9), the state machine with every §6.2 transition tested, the §6.3
  parallel cap, the §6.4 stack query, and the case-screen referral timeline.
- **Sprint 4 — done.** Alert entity (§4.13), the four detection jobs, auto
  resolution, Celery beat schedule, alert inbox and case-screen alerts.
- **Sprint 3 addendum.** `ReferralStackTimeline` (§6.4 as Figure 4) on the case
  screen, with vitest added to `web/` for its layout tests.
- **Design handoff applied.** Every web screen rebuilt on the token layer; see
  the design system section below. Added `/referrals/rules/` (the §6.3 cap as a
  server rule), `Youth.has_open_case` and `User.caseload_count`.
- **Sprint 5 — next.** Training Enrolment (§4.5) and Placement (§4.7) with the
  30/60/90-day retention checkpoints, plus trainer and employer-liaison screens.

Later sprints: 6 enterprise/follow-up/grievance · 7 dashboards ·
8–9 mobile · 10 hardening.

## The referral engine (spec §4.6, §5, §6)

The core of the platform. Read §6 before touching `apps/referrals`.

- **`TRANSITIONS` in `referrals/models.py` is the §6.2 table, transcribed.**
  `Referral.transition_to()` validates every move against it and raises
  `TransitionError` on anything absent. It is the *only* supported way to change
  `status` — the serializer marks the field read-only for that reason.
- **Taxonomy is data, not code.** `ReferralCategory`, `OutcomeType` and
  `FailureReasonCode` are lookup tables in `referrals/taxonomy.py`, because §9
  makes them configuration the system administrator owns and §10.1 requires new
  terms entered through the admin. Seeded by `seed_referral_taxonomy`. By
  contrast `ReferralTrigger` and `ReferralStatus` stay `TextChoices` — each
  value carries state machine behaviour, so a new one needs code anyway.
- **The parallel cap keys off a flag, not a code.** `exempt_from_parallel_cap`
  on the category row drives §6.3, so the pending policy decision can be
  reversed in the admin rather than in a deploy.
- **`transition_to` re-reads its row under `select_for_update`.** Activation
  stamps the parallel group onto *sibling* rows, so a caller's instance can be
  stale; and without the lock two concurrent confirmations could both pass the
  cap check. Do not remove it.
- **The stack is a query.** `build_referral_stack()` rebuilds it from
  `parent_referral` each call. Never cache or denormalise it (§6.4).
- **Prompts are conditions, not rows.** `awaiting_onward_prompt()` and
  `awaiting_replacement_prompt()` are querysets; the Sprint 4 jobs materialise
  them into Alerts. Keep the queryset as the single definition.
- **The stack timeline colours status only.** `web/src/components/referrals/`
  renders §6.4 as the Concept Note's Figure 4, per
  `docs/REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`. That mockup's legend spent
  two of five colours on "parallel", conflating status with structure —
  `parallel_group_id` is independent of `status`, so a parallel referral can also
  be Failed. Concurrency is a bracket, not a colour. Do not reintroduce it as one.
  Layout arithmetic lives in `timelineLayout.ts`, apart from the component and
  free of pixels, because that is the part worth unit testing.

## Alerts (spec §4.13)

- **Detection jobs never create case data.** §5.2 requires the case manager to
  confirm before an onward or replacement referral exists, so the jobs raise a
  prompt and stop.
- **Stall detection does not set `case_status = STALLED`.** §6.2's System Action
  column lists alerts only; moving a case to Stalled is a judgement, not an
  observation about the clock.
- **Every job is idempotent**, backed by two partial unique indexes rather than
  by trust. Two are needed because Postgres treats NULLs as distinct, so the
  three-column index does not constrain case-level (referral IS NULL) alerts.
- **Auto-resolution re-checks against `alert.threshold_days`**, the value
  recorded when the alert was raised — not today's setting. An alert raised
  under a 30-day rule must not be silently re-judged at 90.
- **A system-closed alert has `actioned_by = NULL`.** That is how the §9 audit
  trail distinguishes the resolution sweep from a person.
- **Never name a DRF viewset method `action`.** It shadows the imported
  `@action` decorator for every route below it in the class body and fails at
  class-creation time. Use `url_path` to keep the REST path.

## The design system (`docs/design_handoff_youth_employment/`)

The web UI follows that handoff, which is high-fidelity and final on colour,
type, spacing and interaction states. Its README is the source of truth; the
`.dc.html` prototype is reference only and must not be ported.

**Run `/design` before writing UI code.** `.claude/skills/design/` carries the
working summary — the rules below plus the screen recipes and the rendering
faults that have already shipped here once.

- **Tokens are `web/src/styles/tokens.css`.** Every colour, radius and spacing
  step comes from there. No literal hex in a component except in
  `design/status.ts` and the antd theme, which cannot take a custom property.
- **Ant Design keeps behaviour, not looks.** Modal, Select, DatePicker, Form and
  message stay antd, themed to the tokens in `App.tsx`. Everything visual —
  chips, cards, buttons, tables, nav — is in `components/ui`. This is what §2's
  fixed stack and the handoff's fidelity bar both allow.
- **Never colour alone.** Every status renders as colour *plus* a label *plus* a
  geometric mark (`design/status.ts`), so it survives a monochrome screen, a
  colour-blind reader and a cheap LCD at half brightness. Do not add a status
  that is only a colour.
- **Blue is absent and red is reserved for genuine failure.** Gold carries
  waiting, terracotta carries stalled. `--gold-500` is fill only, never behind
  text — it is 2.6:1.
- **One breakpoint, 780px.** Below it: cards and a bottom tab bar sticky *inside*
  the main column, never `position: fixed`. At or above: nav rail and tables.
  Touch targets 48px, tab bar 56px.
- **Phone numbers are masked by default** (`maskPhone`). The case screen has a
  per-view, never-persisted Reveal; the registry has none at all.
- **Strings go through `i18n/`.** English is populated; Amharic and Afaan Oromo
  are empty tables awaiting a translator, and fall back to English rather than
  showing a key. The language switch swaps the font stack and the leading
  together — Ge'ez leads at 1.75, Latin at 1.5.
- **No icon fonts or chart libraries.** Users are on 3G or worse: icons are
  inline SVG paths in `components/ui`, fonts are self-hosted via `@fontsource`.
- **Every list screen carries a counter row that is also its filter.**
  `GET /<resource>/summary/` returns `{total, counters: [{param, value, label,
  count}]}`, and `MiniDashboard` renders any of them: the server names the query
  parameter, so a counter cannot drift from the list it filters to. Counts cover
  the whole *scoped* set — never the loaded page — and narrow with the search
  box. Build them with `apps/common/summaries.counters_for`, which counts through
  a subquery on the primary keys: grouping a viewset's own queryset picks up its
  annotations in the GROUP BY and silently splits or inflates every count.

Screens not built, and why: the **programme dashboard** is Sprint 7 and its
funnel needs Placement (Sprint 5), so there is nothing truthful to plot; the
**offline/sync strip** is Sprint 8; the **design-tokens screen** is documentation
the handoff itself marks optional.

## Definition of Done (spec §10.1)

1. Automated tests cover the referral transitions and RBAC boundaries touched.
2. Code reviewed before merge.
3. Deployed and demonstrated on the staging Compose stack.
4. New configuration data entered through the admin, not hardcoded.

## Gotchas

- **Traefik must be v3.6+.** Earlier v3.x pin their Docker client to API v1.24,
  which Docker 29 rejects; the provider silently fails and every route 404s.
- **Only `web` has a build block.** `celery` and `celery-beat` reference the
  image by tag. Three services building one tag makes buildx race on export.
- **`User.partner` scopes partner staff to their own institution** (§4.12), and
  `User.clean` requires it on a `PARTNER_STAFF` account. Note that `CaseViewSet`
  and `YouthViewSet` declare no `partner_field`, so partner staff see referrals
  but no case or youth records — that fails closed, but it does contradict §7's
  "View, linked cases only". A Phase 1 question, not a bug to widen away.
- **Test doubles in `test_rbac.py`** — the mixin's decision logic is tested
  against a recording queryset. `apps/cases/tests/test_cases.py` covers the same
  boundaries against real rows; keep both.
- **`development.py` must override `STORAGES["staticfiles"]`.** base.py uses
  manifest static storage, which raises on any file missing from a collectstatic
  manifest — that breaks the admin, DRF's browsable API, and every test that
  renders HTML.
- **Never capture `DEBUG` in a settings lambda.** pytest-django sets
  `DEBUG=False` at runtime; a closure over the module-level literal stays True
  and makes debug_toolbar render during tests. Read `settings.DEBUG` inside the
  function.
- **`registering_worker` and `Case.woreda` are read-only in their serializers.**
  The first comes from `request.user` (§4.1 accountability), the second is
  denormalised from Youth by `Case.save`. Making either writable lets a client
  desynchronise them.
- **Out-of-scope records 404, they do not 403.** The API does not confirm that a
  record the caller cannot see exists.
- **`SpectacularAPIView` needs `api_version="v1"`.** `DEFAULT_VERSIONING_CLASS`
  is `NamespaceVersioning` and the schema view sits outside the `v1` namespace.
  Without it the generator matches nothing and serves an *empty* schema with a
  200 — check `/api/schema/` is tens of KB, not a few hundred bytes.
