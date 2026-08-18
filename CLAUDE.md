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

$C exec web python manage.py seed_pilot_scale               # ~600 youth, pilot scale
$C exec web python manage.py seed_pilot_scale --youth 1000  # the acceptance-criteria size
$C exec web python manage.py seed_pilot_scale --refresh     # delete and rebuild
```

`seed_pilot_scale` is the one to use when a number has to be believable rather
than illustrative: six cases cannot exercise a suppression band, a caseload
budget or a median. It registers into the brief's three live sites (Adama,
Bishoftu, Lume), backdates registration across 18 months so cohorts and
maturation windows bite, and runs the **real** §4.13 detection tasks rather than
inventing alert rows. Deterministic — same `--seed`, same database.

`seed_demo_referrals`: one case per shape the §6.4 timeline has to draw — sequential chain, parallel
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
| 8101 | nginx serving `docs/` read-only (`docs` service, dev overlay only) |
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

## The dashboard handoff (`docs/dashboard_handoff_youth_employment/`)

Authoritative for spec §8, which it replaces: four tier-specific dashboards
instead of nine in a flat table. README §3 is the build order. The v1 prototype
HTML below is its design reference.

**All four tiers are built in the app, as submenus under `/dashboard`.** This
overrides the handoff's placement of tiers 2-4 in Metabase, at the programme's
request. Metabase is out of scope for now; the consequence is that the §7
boundary stays in the ORM where it is tested, and every rate goes through
`rules.py` — which makes the handoff's own "no inline percentage arithmetic"
rule enforceable rather than aspirational.

| Tier | Route | Endpoint | For |
|---|---|---|---|
| 1 Operational | `/dashboard/my-work` | `/api/v1/dashboard/my-work/` | Case manager |
| 2 Tactical | `/dashboard/woreda` | `/api/v1/dashboard/woreda/` | Supervisor |
| 3 Analytical | `/dashboard/programme` | `/api/v1/dashboard/programme/` | Programme manager |
| 4 Strategic | `/dashboard/results` | `/api/v1/dashboard/results/` | M&E / donor |

Tabs are gated by §7 scope (`visibleTiers`), and `/dashboard` lands each role on
its own tier — a case manager must not open the programme's conversion rates,
which is the cream-skimming pressure §4 warns about. **The tab gate is not the
security boundary**: every tier is scoped server-side and a LINKED scope gets
403 on all four.

Tier 1 exists twice on purpose — a server-rendered Django page at
`/dashboard/` on the 8007 origin (the handoff's contract: one request, works
with CSS disabled, ≤12 queries) and a React tab reading the same `queues`
module. One definition of "needs action today", two renderings, so they cannot
drift.

Statistics ported from `sql/002` into `rules.py`: Wilson score intervals,
Spiegelhalter funnel verdicts, and medians. `funnel_verdict` returns `too_few`
for anything below the *report* band, not merely below the suppression floor — a
verdict is a comparison, and the provisional band is defined as never compared.
At pilot scale that means every partner currently reads "too few to assess",
which is the machinery working, not a bug.

**Also built: step 1 and step 2 of the SQL layer.**

- **Steps 1-2 — the SQL reporting layer, verified.** `sql/000`…`005` run clean
  and `sql/900` prints `ALL REPORTING LAYER ASSERTIONS PASSED` (A-Q). Wired into
  CI as the `reporting-sql` job, a blocking gate, per README §3. It runs against
  a scratch database seeded by `sql/000`, which is the only way it can run —
  see below.
- **Tier 1 server-rendered page** at `GET /dashboard/` on the Django origin,
  with drill-downs at `/dashboard/queue/<slug>/`. `apps/dashboard/scoping.py`,
  `queues.py`, `case_manager.py`, `templates/dashboard/`. One request, ~26 KB,
  no percentages, no charts, works with CSS disabled.

**Cards still absent, and why.** Retention, the 90-day disposition and training
completion need Placement (§4.7) and Training Enrolment (§4.5), both Sprint 5.
They report `available: false` with a reason rather than a zero. `WS-2 unassigned
youth` is absent for a different reason: §4.2 makes `case_manager` required, so
it is a state the schema cannot hold (OQ-12).

**Not built, and why.** Step 3 and the Metabase steps are blocked, not skipped:

- **The `rpt` schema cannot be built against the real database.** Verified, not
  assumed: `001` and `002` apply cleanly, `003` fails with
  `column y.youth_id does not exist` and `relation "placements_placement" does
  not exist`. The bundle's `sql/000` fixture models an idealised schema —
  `youth_id`/`case_id`/`referral_id` primary keys where Django uses `id`, text
  columns where Django has taxonomy FKs, lowercase status codes where Django
  uses uppercase — plus five tables from Sprints 5-6 that do not exist. The
  fixture says "if a column here disagrees with the Django model, the Django
  model wins", so the adaptation is a compatibility layer of source views under
  `rpt`, feeding `dim_youth` and `fct_referral`. Those two are the only seams:
  everything downstream reads `rpt.*`.
- **Metabase (steps 5-8)** is not deployed; port 8009 is reserved and idle.

**Tier 1 decisions worth keeping:**

- **`scoping.py` delegates to `permissions.scope_queryset`.** The contract
  sketches scoping as a chain of `if user.role ==` branches; CLAUDE.md forbids
  inline role tests. Delegating gives the contract its single entry point and
  keeps `ACCESS_MATRIX` the only description of §7. It also means the
  administrator widening of 2026-08-16 is not silently reverted by a handoff
  that restates §7 as written — a test pins that.
- **`scoped_referrals` is not `case__in=scoped_cases()`.** One youth can hold
  referrals to several partners; case-level scoping alone hands Partner A the
  referral sent to Partner B. That exact case is tested.
- **CM-4 checks one of its four conditions** and says so on screen. The other
  three need Training Enrolment, Placement and Follow-Up. A card that silently
  checks one of four while calling itself the at-risk list is worse than one
  that names what it cannot see.
- **A 12-query budget and a no-percentage assertion** are tests, not comments.
  The budget is what forces the counts to be separate cheap queries rather than
  `len()` over a fetched page.

**`PUNCH_LIST_v1.md` v3 (17 Aug 21:25) is answered.** Its Tier 3 findings are
fixed except G-7 (filter row), G-9 (small multiples) and G-11 (needs OQ-9).
Two of its P1s were misdiagnosed in a way worth recording:

- **G-1, "the matrix is a tautology"** — correct observation, wrong cause. The
  build does not derive `outcome_type` from `referral_category`; §5.3's
  `applies_to` admits exactly one specific outcome per category plus Other, so
  the crossover PM-3 exists to expose is **forbidden by the taxonomy**, not
  merely unrecorded. The card now says so (`crossovers_possible`). Widening it
  is an admin decision — taxonomy is configuration (§9).
- **G-3, "56% Other"** — a seed artefact (uniform choice over `[specific,
  Other]`), now weighted. The underlying point stands, so a high Other share is
  surfaced on the card as a data-quality warning.

**Funnel stages are `gating` or coverage.** Profiling and pathway assignment are
not prerequisites — the referral engine raises a referral without either — so
counting them as funnel stages put "Referred 168" above "Profiled 0" and read as
a broken programme rather than a profiling gap. Drop-off is annotated only
between gates, and the nesting invariant is only claimed where it holds.

**`PUNCH_LIST_v1.md` v2 (17 Aug 20:40).** v2 withdrew P1-1 and
restated P1-3 in the same direction found here independently. Its Tier 1 P2s and
Tier 2 W-items are fixed, except W-4 (filter row) and W-6 (woreda pipeline,
which the handoff admits is missing from its own prototype).

**`REFERRAL_ABANDONMENT_DAYS` closes a real gap in §6.2.** Pending Confirmation
has only two exits — the partner answers, or a case manager cancels — so a
referral nobody answers sits there forever, holding a slot against the §6.3 cap
and staying in the loop-closure denominator. `alerts.fail_abandoned_referrals`
closes it as `PARTNER_NON_RESPONSIVE` (§5.4, a code nothing previously set).
**Off by default**: failing a referral is a decision about a real young person
and the threshold is programme management's (OQ-13).

**Settled 2026-08-18:**

- **`CASELOAD_CEILING` is 50.** The handoff's `reporting_parameters` default of
  120 is superseded. Tier 2 flags against 50.
- **A case manager may record a partner's confirmation** (§8.1). `confirmed_by`
  still names who at the partner gave the answer; `Referral.confirmation_recorded_by`
  is the account that typed it, stamped by `transition_to` and **null when the
  partner confirmed through their own login**. The two must never be merged:
  partner response medians count only the partner's own answers, and
  staff-recorded ones sit beside them as a separate number. Fold them together
  and a partner who never replies scores like one who replies the same day.
- **P1-2 stands.** The administrator's case access is the deliberate
  `ACCESS_MATRIX` widening, confirmed rather than a defect. Do not "fix" it to
  §7-as-written.

Still open: `referral_abandonment_days` (the sweep is built and disabled), the
7-vs-14-day confirmation threshold, and OQ-9's retention anchor.

**`PUNCH_LIST_v1.md` v1 background.** Its nine P2 items on the My Work
tab are fixed and tested. Its three **P1s are not code defects** — each was an
artefact of reviewing the screen signed in as `admin`, and the diagnosis is
worth keeping because it will recur:

- **P1-1** "the alert engine is not firing": 113 confirmation-overdue alerts
  existed and all were assigned. CM-1 shows alerts assigned to *me*, and the
  administrator has none. The card now says "No alerts are assigned to you.
  N are open on cases you can see" rather than "Nothing is overdue" — the
  second is a claim about the programme, and it was false.
- **P1-2** "RBAC is not scoping": the administrator seeing case content is the
  deliberate `ACCESS_MATRIX` widening of 2026-08-16, pinned by a test. Do not
  "fix" it back to §7 as written without reversing that decision first.
- **P1-3** "confirmation never advances": the state machine spreads across all
  six statuses. The 500-day pending referrals were a seed defect, since fixed.

**Open questions OQ-1…OQ-12 are unresolved**, and six of them are schema
changes that must land *before* Sprint 5 records its first placements or that
cohort is permanently unreportable: `service_start_date` (OQ-1),
`verification_source` (OQ-2), `is_subsidised` (OQ-3), `psnp_client_category`
(OQ-4), `Placement.exit_reason` as an enum (OQ-5), `Case.case_manager` nullable
(OQ-12).

## The dashboard prototype (`docs/Youth_Employment_Dashboard_Prototype_v1.html`)

A four-tier role-based dashboard proposal — case manager · supervisor ·
programme manager · M&E/donor — plus a method panel that proposes **replacing
spec §8**. Reference only, like the design handoff's `.dc.html`: read panel 5,
do not port the markup (it loads Google Fonts, which the brief forbids).

What is adopted: the reporting rules above. What is **not** adopted and needs
your sign-off:

- Replacing §8 and resequencing Sprint 7 (§10 sprint order is rule 1 here).
- The four-tier split, and moving tiers 2–4 into Metabase. The dashboard that
  exists serves tiers 2–4 mixed together, in React.
- Its new nine-colour chart palette (`--cat-1..4`, `--seq-1..5`), which is not in
  the handoff's token tables — the handoff is final on colour.

Its claim that "nothing here requires a new form" does not hold. Verified
against the models, it needs at least: a **service-attended** referral state
(none exists — the 52-day median it calls the most actionable number cannot be
computed), `verification_source` as an enum (`outcome_verification_method` is
free text), a **placement exit taxonomy** (left for better job / involuntary /
lost to follow-up), and **rural/urban** on Youth. The first three must exist
*before* Sprint 5 records its first placements, or that cohort is permanently
unreportable. It also assumes six case statuses; `CaseStatus` has five.

It does supply sourced answers to two §11 questions: youth age band **15–29**
(Ethiopia's definition, not 15–24) and **7-day** referral confirmation — both
matching the current defaults.

## Open questions (spec §11 and the dashboard handoff)

**Closed 2026-08-18.** Every one below now has an implemented default and a
reason. They remain *decisions*, not facts: each is a one-line change, and the
Phase 1 workshops can overturn any of them. What has gone is the state where the
code had no answer at all.

| Question | Settled at | Why |
|---|---|---|
| Confirmation threshold (§11) | **14 days** | Partners answer in a median of 8-10 days, so 7 flagged four cases in five and a queue where everything is overdue prioritises nothing. 14 flags roughly the slowest quartile. Also removes a contradiction: the dashboards said 14 while the alert engine used 7. |
| `REFERRAL_ABANDONMENT_DAYS` (OQ-13) | **60 days**, sweep on | Six times the median response and four times the standard, so it cannot catch a merely slow partner; inside a quarter, so a stranded referral frees its §6.3 slot within the reporting period. Recoverable: the case keeps its history and a replacement referral is allowed immediately. |
| `CASELOAD_CEILING` (§11) | **50** | Confirmed by the programme. The handoff's `reporting_parameters` default of 120 is superseded. |
| Partner confirmation by staff (§8.1) | **Allowed**, recorded separately | `Referral.confirmation_recorded_by` is null when the partner confirmed themselves. Response medians count only the partner's own answers. |
| Retention anchor (OQ-9) | **3 months from programme exit, unsubsidised** | It is the anchor UPSNJP's "wage-employed 3 months after completion" uses, so woreda figures roll up without reconciliation. Operations keeps 30/60/90 from placement. The build's third anchor ("6 months") came from a mockup with no framework behind it and is dropped. |
| `service_start_date` (OQ-1) | **Added** | The confirmed-to-outcome gap is the largest loss in the pipeline (50%, median 54 days) and could not be split without it. Renders as not-instrumented until intake populates it, never as zero. |
| `verification_source` (OQ-2) | **Added**, four-value enum | §8.3 makes the externally-verified subset the reportable headline, which is not expressible while the only record is free text. |
| Outcome taxonomy (G-1) | **`applies_to` widened** | Each category admitted one outcome plus Other, so the outcome matrix could only restate its own lookup table and the onward-referral gap was unrepresentable. Widened only where the path is real — a training referral can end in a job. Still administrator-owned (§9). |
| `settlement_type` (OQ-11) | **Added**, optional | Both frameworks require a rural/urban cut. Never proxied from woreda: an Ethiopian woreda routinely contains both, so inferring it gives a confident wrong number rather than an honest blank. |
| Suppression bands (OQ-8) | **30 / 10**, unchanged | NCHS Data Presentation Standards for Proportions. No reason to depart from a published standard. |
| Complementary Service and the cap (OQ-7) | **Outside the cap**, unchanged | A health or legal-aid referral should not consume an employment-pathway slot. `mv_parallel_load` evidences it: zero cases breach. |
| `Case.case_manager` nullable (OQ-12) | **No change** | WS-2 wanted it for an "unassigned youth" count, but §4.2 makes the assignment an accountability record and "registered, no case yet" already answers the question honestly. Weakening a required FK to satisfy one card is the wrong trade. |
| System administrator case access | **Widened**, confirmed | The 2026-08-16 deviation from §7 stands. Do not "fix" it back. |

Still genuinely open, because they need data that does not exist yet:

- `vulnerability_index_score` methodology (§4.3).
- `failure_reason_code` list — a starter pending frontline validation (§5.4).
- Offline conflict resolution (§9, blocks Sprint 9).
- `Placement.exit_reason` as an enum (OQ-5) and `is_subsidised` (OQ-3) — decided in
  principle, but Placement lands in Sprint 5, so there is nothing to add them to.
- The seeded woredas are illustrative; the actual pilot woredas are a programme decision.

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
- **Bulk youth intake.** `apps/youth/imports.py` plus `POST /youth/import/` and
  `GET /youth/import/template/`, with the Import from Excel button on the
  registry screen. See the bulk intake section below.
- **Programme dashboard.** The handoff's screen 8, built on the entities that
  exist; see the dashboard section below. Adds `apps/dashboard`,
  `GET /dashboard/`, `OutcomeType.counts_as_placement`, and
  `permissions.scope_queryset`.
- **Sprint 5 — next.** Training Enrolment (§4.5) and Placement (§4.7) with the
  30/60/90-day retention checkpoints, plus trainer and employer-liaison screens.
  Landing it also fills the dashboard's two absent figures.

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

## The programme dashboard (`apps/dashboard`, `web/src/pages/DashboardPage.tsx`)

The handoff's screen 8, for supervisors and the donor. **This is not the Sprint 7
Metabase work** — §2 puts "supervisor and programme manager dashboards" on the
React frontend, and §8's nine analytical dashboards are a separate Metabase
deliverable against a read-only Postgres role. Building one does not discharge
the other.

### Reporting rules (`apps/dashboard/rules.py`)

Adopted from `docs/Youth_Employment_Dashboard_Prototype_v1.html` panel 5, which
proposes replacing spec §8. **Only these rules are adopted — the four-tier
restructure, the resequencing of Sprint 7 and the new chart palette are not, and
need sign-off.** They live in one module because a rule applied in four places is
four rules, and the one that gets forgotten is always the disaggregated cell.

- **A percentage never travels without its counts.** No shape in the API or in
  `api/types.ts` carries a bare percentage: `rate()` returns `{percent, n, d,
  band, note}` and the screen renders all of it.
- **Three denominator bands.** ≥30 report · 10–29 provisional, marked `25%*` and
  never used in a comparison or ranking · <10 withheld entirely.
  `REPORT_MIN_DENOMINATOR` / `PROVISIONAL_MIN_DENOMINATOR`, both
  `TODO(open-question)` — the thresholds follow NCHS but nobody has agreed them.
- **Suppressed is not zero.** 0 of 40 is a finding; 0 of 4 is not measurable.
  They must not render alike — the screen says "too few to assess", never 0%.
- **Averages band like rates.** A mean over four referrals is as unstable as a
  rate over four; `mean_days()` applies the same thresholds.
- **Nothing is ranked by rate.** Partners and woredas order by `n` — by how much
  evidence there is, not by who is winning. Rate-ranking at these denominators
  sorts by luck, rewards creaming, and is hard to withdraw once published. The
  vulnerability profile that would let us adjust for intake difficulty does not
  exist (§4.3's index is undefined).
- **Progress against a target is read against elapsed time.** The quarter card
  carries `quarter_elapsed_percent` and marks it on the track, or every quarter
  opens saying the programme is failing.
- **Whole percentage points only.** 49%, never 48.81%.

Worth knowing before reading any of it: the pilot is 500–1,000 youth across two
or three woredas (§1). Applied honestly these thresholds suppress much of what a
donor will ask for — every partner-level rate early on, and most of the sex ×
age × woreda × disability disaggregation throughout. That is the correct answer,
not a defect, but somebody has to agree in advance what the donor tier says when
most cells are dashes.

### Routes

**`/dashboard` points at the prototype, not at this code.** It redirects to
`VITE_DASHBOARD_URL` (default: the copy served on 8101), because the prototype is
what is currently under review. The screen built on real §7-scoped data is at
**`/dashboard/live`**, and that is what the sign-in redirect for supervisory
roles uses — signing in must not throw anyone out of the app to a static page.

The prototype's figures are illustrative. If `/dashboard` is ever pointed at a
deployed environment, that has to change first: 842 registered youth and 214
placements are not this programme's numbers.

### The screen

- **A figure with no source entity is absent, not zero.** Retention at six months
  needs Placement and its 30/60/90-day checkpoints (§4.7, Sprint 5), so both the
  retention card and the funnel's last row report `available: false` with a
  reason. A donor-facing 0% that means "not built yet" is a lie, and an invented
  plausible number is a worse one. `Maybe<T>` in `api/types.ts` makes the screen
  handle it — there is no way to read `.value` off an absent figure.
- **The quarterly target is `PLACEMENT_TARGET_PER_QUARTER`, defaulting to 0.**
  The mockup's 180 is mockup data. 0 means "no target agreed" and the card shows
  the count alone rather than a percentage of a number we chose.
  `TODO(open-question)`.
- **What counts as a placement is an admin flag**, `OutcomeType.counts_as_placement`,
  not a list of codes — same reasoning as `exempt_from_parallel_cap`. Seeded true
  for Job Placement, Apprenticeship Start and Enterprise Enrolment. Training
  Completion is deliberately false: a finished course closes a referral without
  putting anyone in work, and counting it inflates the headline.
- **Every figure is scoped before it is counted.** An aggregate is a disclosure:
  "4,812 registered" told to someone entitled to see 300 is still a leak. All
  three base querysets go through `permissions.scope_queryset` — extracted from
  `ScopedQuerySetMixin` so the decision to fail closed lives in one place — and
  the subtitle states the scope so a woreda total cannot be read as the
  programme's. A LINKED scope has no case population and gets 403, not zeroes.
- **The funnel counts youth, not events.** A youth referred three times is one
  youth referred; counting referrals would let a later stage exceed an earlier
  one, which reads as a broken programme rather than a broken query.
- **A partner that never replied is absent from the lag panel, not fast.** A null
  lag is not a short lag, and averaging it in rewards silence.
- **Bars are hand-built divs; no chart library** (the brief's 3G constraint).
  Arithmetic lives in `dashboardLayout.ts`, pure and unit-tested, per the
  `timelineLayout.ts` pattern: a non-zero value always gets a visible sliver
  (`MIN_VISIBLE_PERCENT`), a true zero draws nothing, and `lagScale` keeps the
  14-day standard inside the range so its reference mark is always drawable.
- **The panels use `auto-fit` grids, not `.only-phone` / `.only-laptop`.** They
  have no separate phone layout — they simply stop sitting side by side — so
  there is no second variant that could render at the same time.
- **`--gold-500` carries `--ink-900` text in the gender bar.** The token is
  documented fill-only because it is 2.6:1 *as text on paper*; ink on gold is
  5.9:1 and is what the handoff's own mockup shows. Do not "fix" it to white.
- **The failure-path test lives in its own file** (`DashboardPage.error.test.tsx`).
  A rejecting fetch shares badly with the success-path tests around it — vitest
  attributes the rejection to whichever test is running when it settles.

## Bulk youth intake (`apps/youth/imports.py`)

Woreda registers arrive as .xlsx, so `POST /youth/import/` takes one.
`GET /youth/import/template/` serves the blank register, built from the same
`COLUMNS` list the parser reads — the template cannot describe a column the
importer does not accept.

- **Every row goes through `YouthIntakeSerializer`.** The §9 consent rule, the
  location vocabulary and zone-chain checks and the §11 age-band warning are not
  restated here. A second copy would drift from the form's copy, and consent is
  the one thing that must not. This module owns only the spreadsheet: which cell
  is which field, and what an Excel value means.
- **Two uploads, one file.** The first has no `commit` and writes nothing; the
  UI shows that report and the user approves it. The second replays it with
  `?commit=true`. The report is identical either way.
- **All or nothing.** One invalid row refuses the whole file, inside a single
  transaction. A half-imported register leaves nobody able to say which half.
- **A row already on file is skipped, not refused** — matched on
  `national_or_kebele_id`, or on name plus date of birth where the register
  carries no ID. Registers get re-sent with more names appended, so re-importing
  must not double the registry. Keys are claimed as the file is read, so a name
  repeated inside one file is caught too. Test presence in `seen`, never truth:
  an in-file claim is stored with an empty id.
- **Excel types are not Python types.** A digit-only ID or phone comes back as a
  float (`912345678.0`), a date comes back as `datetime` or as text depending on
  the cell's format, and choice cells carry the label or the code. `_clean`,
  `_coerce_date` and `_coerce_choice` absorb all three.
- **The importer is the `registering_worker`** (§4.1 accountability), and an
  outreach worker or supervisor cannot import outside `woreda_assignment`. Note
  that `POST /youth/` makes no such check — flagged `TODO(open-question)` in
  `_check_scope`, for Phase 1.

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
- **Three breakpoints, in `base.css` only.** `900px` collapses every
  multi-column grid to one column; `780px` is the structural switch (below it:
  cards and a bottom tab bar sticky *inside* the main column, never
  `position: fixed`; at or above: nav rail and tables); `640px` drops the KPI
  row to two columns. Touch targets 48px, tab bar 56px. The design handoff
  specifies 780px alone — 900 and 640 were added on the programme's
  instruction of 2026-08-18 and supersede it.
- **Card padding is 24px** (`--s5`), gaps 16px between cards and 24px between
  sections. Same instruction. `.card` is used on every screen, so changing it
  moves every screen.
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

Screens not built, and why: the **offline/sync strip** is Sprint 8; the
**design-tokens screen** is documentation the handoff itself marks optional. The
**programme dashboard** is built — see its section above — with the two figures
that need Placement (Sprint 5) reported as absent rather than plotted.

## The UI/UX backlog (`docs/UI_UX_BACKLOG.md`)

Findings from the 2026-08-18 review — four parallel audits (visual rendering,
design-system conformance, accessibility, content) against the rendered screens
and the source. 67 entries with stable IDs; 42 still open, 9 of them P1.

Read it before touching the web UI: it records what was **rejected** as well as
what is outstanding, so the same non-issues are not re-opened. Each entry is
marked `✔` (verified here) or `○` (agent-reported, confirm before acting) —
several agent claims did not survive checking.

The largest open item is **DS-04**: ~185 hardcoded user-facing strings, with
five form components entirely un-i18n'd, so a translator delivering Amharic
still gets English on every screen field staff type into.

Screens are photographed with `scripts/shoot.mjs`, which mints a JWT through
`manage.py` and injects it into `localStorage` — no password, no account
mutation. It also reports console errors. Run it before and after UI work;
jsdom applies no stylesheet, so the test suite cannot see a layout fault.

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
