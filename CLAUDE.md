# Economic Opportunities Pathway Platform (EOPP)

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
- ~~`Placement.exit_reason` as an enum (OQ-5) and `is_subsidised` (OQ-3)~~ — both
  implemented in Sprint 5, on the entity that now exists. `psnp_client_category`
  (OQ-4) is on Youth; its three values still need FSCO.
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
- **Sprint 5 — done.** Training Enrolment (§4.5), Placement (§4.7) with the
  30/60/90-day retention checkpoints and their reminders, the trainer and
  employer-liaison screens, and the four dashboard cards that had been reporting
  `available: false` since the dashboards were built. See the section below.
- **Sprint 6 — done.** Enterprise (§4.8) with its milestones sub-table,
  Follow-Up / Contact Log (§4.9) with referral outcome verification, Grievance
  (§4.10), the enterprise-officer, M&E and grievance screens, and §4.13's last
  undetected alert type. See the section below.
- **Sprint 7 — next.** The §8 Metabase deliverable: nine analytical dashboards
  against a read-only Postgres role, on port 8009. Note that the four-tier
  React dashboard already built does **not** discharge it — see the dashboard
  handoff section above.

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
- **Card padding is 18px/20px**, gaps 16px between cards and 24px between
  sections. `.card` is used on every screen, so changing it moves every screen.
  This started at 24px on the 4px scale and was tightened by
  `docs/design_handoff_partners_page/`, which exists to tighten "an oversized,
  inconsistent type scale" throughout. The programme confirmed the tighter
  result on 2026-08-18 — do not restore 24px.
- **The palette has grown past the original handoff.** `--blue-*`, `--teal-*`
  and `--slate-*` were added for the alerts inbox
  (`docs/design_handoff_alerts_inbox/`) and confirmed. This supersedes the
  design handoff's "blue is deliberately absent" for those tokens; red is
  still reserved for genuine failure, and gold still carries waiting.
- **The rail is 232px expanded, 60px collapsed**, and the global search sits
  in the rail rather than a top bar.
- **`tokens.css` wins over a handoff's hex values.** Confirmed 2026-08-19.
  The later handoffs were traced from screen captures, so each quotes the same
  surfaces at slightly different values — the page ground appears as `#f7f4ee`
  (tokens), `#f6f2ea` (partners) and `#f7f2e7` (results); the rail as `#173629`
  and `#1b3a30`. Those are tracing drift, not three decisions. Build the
  *design* — layout, type scale, spacing, component structure — from the
  handoff, and take every colour from the token layer. Each of these handoffs
  says so itself: "recreate using the codebase's existing design system where
  equivalents exist."

  Two literals that reached components this way were both unreadable, which is
  the practical reason as well as the tidiness one: `#9b9282` for muted text is
  3.07:1 on white, and the partners handoff's 65%-opacity pill count is 2.95:1.
  A token has its contrast checked once; a traced hex has not been checked at
  all.
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

## The user manual (`web/public/manual.html`)

One standalone HTML file, reached from the account menu at the foot of the rail,
from the More sheet on a phone, and from the sign-in card — all opening in a
new tab. It is on the sign-in screen for the same reason the language switch
is: a password that will not work and a first sign-in are both on that side of
the door.

- **A static file, not a route.** A manual is wanted precisely when the app is
  not working — an uncached bundle on 3G, a printout, a copy saved to disk. It
  is served by nginx (Traefik gives `/manual.html` to the `spa` service), has no
  JavaScript, and prints. 33 kB, 11 kB gzipped.
- **It duplicates the token hex values in its own `<style>`.** This is the one
  sanctioned exception to "no literal hex outside `design/status.ts` and
  `ANTD_THEME`": the page cannot import `tokens.css` and still open on its own.
  The block says so; if the palette changes, change it there too.
- **It states the screens as built, and quotes their real strings.** Status
  labels and marks come from `design/status.ts`, button and chip text from
  `i18n/strings.ts`, the role table from `ACCESS_MATRIX` and `TIER_ACCESS`.
  Checked against those, not written from memory — a manual that names a button
  nobody can find is worse than none.
- **No threshold days are printed.** Confirmation, stall and abandonment windows
  are configuration and three of them are still open questions; the manual says
  "past the threshold" and leaves the number to the screen.
- **Section 12 is the one to keep current.** It explains suppression bands,
  "too few to assess" and "not measurable yet" — the parts of the dashboards
  that read as faults until somebody explains that they are not.

## The WLT group module (`backend/apps/wlt`, `web/src/pages/wlt/`)

**A second programme on the same platform, not a later sprint of the first.**
PSNP 6 Women's Livelihoods Transformation: 5,000 women in Self Help Groups of
15-25, saving weekly, lending internally, maturing through four phases and
federating into Cluster Level Associations. Its subject is a *group*; the youth
domain's is a *person*. That difference is why it is a separate app and why it
carries its own roles.

`docs/wlt_module_handoff/` is the specification — read `START_HERE.md` first,
then `DECISIONS.md`. **`BUILD_RESPONSE.md` in the same directory records what
was built, every adaptation, and why each departure was made.** Read it before
changing anything here; several of the differences from the bundled SQL are
deliberate and each one changes a reported number.

Sprint order (CLAUDE.md rule 1) does not apply to it: it is not in the youth
spec's §10 at all. Stages 0-8 of the handoff's own sequence are built; stage 9
(credit facility, federation) is schema and gates only, per its decision D8.

### The load-bearing decisions

- **Decision D4 is implemented in half, deliberately.** The referral *subject*
  generalises exactly as D4 specifies — `referrals.Referral` now names a case, a
  youth, an SHG, a CLA or a federation through typed nullable FK columns, an
  exactly-one check constraint and a generated `subject_type`. The twelve-state
  gated linkage *lifecycle* does not: it lives in `wlt.ServiceLinkage`, because
  it shares no state with §6.2 but "active", and folding them into one status
  field would have meant re-auditing every youth queryset, dashboard tier and
  alert job for group-subject leakage.
- **`Referral.objects.youth_side()` is the module boundary**, not an
  optimisation. Every youth-side entry point goes through it: the referral
  viewset, the dashboard scoping, all four alert jobs. A `Scope.ALL` user would
  otherwise read a savings group's bank linkage on a screen built around a young
  person. Add it to any new consumer of `Referral`.
- **`ReferralCategory.allowed_subject_types` is a safeguarding control.** A
  protection category permits `CASE` and `YOUTH` only, so a GBV disclosure can
  never be created against a group or land on a group timeline. An **empty list
  means CASE**, not "anything" — reading it as unrestricted would open the rule
  the moment somebody cleared the field.
- **A woreda officer may draft a group; she may not run one.** Confirmed
  2026-08-22, and implemented as `CanDraftGroups` rather than as a widening of
  `group_write`. The two writes look alike and are not: *running* a group is
  recording what happened in the room — meetings, attendance, the ledger — and
  stays the facilitator's alone, because an officer who could post a ledger
  entry could also settle a discrepancy nobody witnessed. *Drafting* one is an
  administrative act at woreda level: she holds the ELS extract and convenes
  the mobilisation, and a facilitator's scope is the kebeles of groups she
  already runs, so gating drafting on `group_write` left the first group in a
  new kebele creatable by nobody. Same shape as `CanEnrolBeneficiaries` and
  `delivery_write` — named for the work rather than stretching §7's write
  column over it. Anybody who is not a facilitator must name the facilitator
  who will run the group, so an officer's draft lands with somebody
  accountable. Region and federal officers are approval tiers and are
  deliberately **not** included.

  The first attempt at this dropped `CanAccessGroups` from the create action
  entirely, which removed the `group_scope != NONE` check with it — the module
  boundary stopped being enforced on that action at all. A test pins that a
  case manager still cannot draft a group.

- **Four WLT roles, all with `case_scope: NONE`.** `WLT_FACILITATOR`,
  `WLT_WOREDA_OFFICER`, `WLT_REGION_OFFICER`, `WLT_FEDERAL_OFFICER`. That is how
  "a facilitator who can see a group roster must not thereby see those women's
  youth-side case files" becomes a property of `ACCESS_MATRIX` rather than of
  every viewset that remembers. Every youth role has `group_scope: NONE` in
  return, and both directions are tested on the same woman.
- **Group scoping is `scope_group_queryset`**, keyed on `Group.facilitator` or
  on `User.wlt_scope_location` — a nullable FK to any level of the hierarchy.
  `woreda_assignment` stays what it is: woreda *names*, which cannot express a
  region without re-listing every woreda in it. Fails closed, same as §7 scoping.
- **A WLT member is a `youth.Youth` row.** Handoff decision D1: one identity, no
  second person table. The model is named for the programme it was built for;
  the age band is a warning rather than a constraint, so an adult PSNP woman
  sits in it honestly.

### Rules that will bite if you skip them

- **Thresholds live in `wlt.PolicyParameter`, never in code.** Effective-dated
  and geography-scoped, resolved by `wlt/policy.py` most-specific-place-first.
  The source handbook states group size three ways and the CLA threshold two;
  values will move mid-pilot. `FALLBACKS` in that module is the whole rule set in
  one place, used only when the table has no row at all.
- **Membership, office, bylaws and delegates are dated ranges, never flags.**
  Every indicator computes against the roster as it stood *on each meeting date*
  (`Group.roster_on`), and against the bylaw in force *then*. An `is_active`
  boolean would drift from the dates within a month.
- **The ledger is append-only and the till must reconcile**, enforced by
  triggers in migration `wlt/0002_ledger_invariants` as well as in
  `services/ledger.py`. That is a deliberate departure from "no business rules in
  the database": the service layer is not the only writer — the admin, a data fix
  and a future sync reconciler reach these tables too — and members sign the
  paper register, so the digital record has to be defensible against it.
  Corrections are reversals with a mandatory reason, never edits.
- **A phase decision locks when it is decided, not when it is written.** The
  bundle's `sql/002` blocks every UPDATE on `phase_event`, which would make a
  submission impossible to approve. Here the trigger tests `OLD.decided_at IS
  NOT NULL`, which is the property assertion A26 is actually about.
- **Gates are evaluated at screening and again at approval**, on a subject
  re-read from the database. A group can drift below threshold while an approval
  sits in a queue, and re-evaluating from a stale in-memory instance is the same
  bug as not re-evaluating at all.
- **The system computes readiness; a human approves.** No job graduates a group.
  The nightly tasks only observe: at-risk and dormancy are descriptions of the
  data and clear themselves when it changes.

### Four numbers that differ from the bundled `sql/004`, on purpose

PAR30 references the **earliest unpaid instalment** rather than `loan.due_on`
(the bundle's own punch list asks for this); fund adequacy is **converted to
weeks by the group's cadence**, so a monthly group is not reported in months
under a weeks-denominated threshold; a **completed loan cycle needs every loan
in the batch settled**; and meeting adherence counts meetings **inside the
window** rather than the last twelve whenever they happened — a group that
stopped meeting in March otherwise reads 100%. All four are stated in
`BUILD_RESPONSE.md` §3.

### Layout and commands

```
apps/wlt/
  models/     registry · formation · ledger · phase · structure · linkage · policy
  services/   ALL business logic: enrolment, formation, ledger, indicators,
              gates, phase, linkage, structure
  policy.py   effective-dated, geography-scoped parameter resolution
  api/        thin DRF viewsets; every status moves through an action, not a PATCH
  reporting.py + migration 0004: eight materialized views, refreshed nightly
```

```bash
$C exec web python manage.py seed_wlt_policy      # parameters, allocations, pilot sites
$C exec web python manage.py seed_wlt_taxonomy    # linkage types + WLT referral categories
$C exec web python manage.py refresh_wlt_reporting
$C exec web pytest apps/wlt -q
```

Screens: `/wlt/groups`, `/wlt/groups/<id>` (**the readiness card** — every gate
condition with the actual value beside the threshold, three states not two —
and **the roster**), `/wlt/linkages` (**the blocked-gate screen**, which the
handoff calls the most behaviour-changing in the module), `/wlt/cla-readiness`.
API at `/api/v1/wlt/`.

### The roster (`web/src/pages/wlt/GroupRoster.tsx`)

Added 2026-08-20. The group screen had carried a member *count* and no names, so
twenty women existed in the database with no screen that listed them, and none
of the four WLT screens made a single write call. The services underneath were
complete from stage 1 — this is the route and the panel over them.

- **An exit closes a dated range; it never deletes a row.** A former member
  stays on the screen with her date and her reason, and the panel says why in as
  many words. Hide her and February's attendance changes when she leaves in
  April, because the denominator is the roster as it stood at each meeting.
- **`exit_member` had no route.** It was written, tested against A11 and never
  reachable over HTTP, so the only way to close a membership was a shell. It is
  now `POST /wlt/groups/{id}/members/{membership_id}/exit/`, and the membership
  is looked up *through* the group so it inherits the group's scoping.
- **The reason is mandatory in the route, not only in the check constraint.**
  The constraint can only say "not blank". "Moved away" and "expelled" are
  opposite programme outcomes and a group losing members to one is not the same
  finding as a group losing them to the other.
- **`BeneficiaryProfileQuerySet.unassigned()` was inverted, and had always
  been.** `exclude(person__wlt_memberships__exited_on__isnull=True)` reads
  correctly and compiles to a LEFT OUTER JOIN inside the subquery, so a woman
  with *no* membership row gets a joined NULL, matches `exited_on IS NULL`, and
  is excluded. Every profile in the database failed it — `candidate_pool()`
  (backlog S1.5) returned nothing, for anyone, ever. Now an `Exists` subquery.
- **The API's `candidates` action had the opposite bug** and did not filter
  eligibility at all: `wlt_memberships__isnull=True` meant never in *any* group,
  so an exit was permanent, and the pool offered women `add_member` then refused.
  It now calls the same three queryset methods the service does.

Still not built here: creating a group and closing one. `POST /wlt/groups/`
exists but bypasses `open_draft`, so it skips the endorsement check — a group
can be drafted from a mobilisation meeting the community refused. Closing a
group has no action at all; `DELETE` is the wrong shape, because
`GroupMembership.group` is `PROTECT` and dissolution is a status transition
carrying a reason (`DISSOLVED` / `SPLIT` / `MERGED` / `ABANDONED` are all in
`GroupStatus`).

### The register, and the workflow through it (2026-08-20)

**"Youth registry" is now "Beneficiary registry" on screen.** The registry holds
two populations on one identity (decision D1): the young people the youth
programme registered, and the adult PSNP women WLT enrolled. The `Youth` model
keeps the name it was built with — renaming it would be a migration across every
app for no gain — but the screen does not, because a facilitator looking for a
fifty-year-old woman should not have to read "youth" and trust it.

**The workflow is register → group → linkage, and its first step did not exist.**
`YouthViewSet` is gated on `CanAccessCases` and every WLT role has
`case_scope: NONE`, so no WLT account could create the `youth.Youth` row that
`add_by_facilitator` needs. Decision D5's exception route stopped at its first
step. The ELS import had the mirror problem: `import_batch` worked and had no
parser, no template and no endpoint. Both routes are now reachable.

- **`POST /wlt/profiles/register/` writes the person and her profile together.**
  This does not breach the module boundary and the distinction is the point:
  registering somebody is not reading their case file. She still gets 403 on
  every case route, which `test_boundary` pins and `test_enrolment_api` re-pins
  from the other side. `import_row` already created `Youth` rows on the same
  reasoning.
- **The place is a kebele, by `code`.** Region, zone and woreda are derived
  server-side — a hand-typed woreda that disagrees with its kebele scopes to one
  place and reports in another. `code` because that is what the locations API
  emits and looks up on; its integer pk appears nowhere a client can see.
- **`CanEnrolBeneficiaries` is a permission, not a widening.** A woreda officer
  has `group_write: False` on purpose — meetings and the ledger belong to the
  facilitator who was in the room — but she is the person who *holds* the ELS
  extract, and a facilitator's scope is the kebeles of groups she already runs,
  so she cannot seed the first one. Gating enrolment on `group_write` left the
  extract importable by nobody who has one. Same shape as `delivery_write`: §7's
  write column did not fit the person doing the work, so the permission is named
  for the work rather than stretched to cover it.
- **A name match never refuses a registration.** Rule 2 forbids turning a fuzzy
  match into a decision, and two women in one kebele really can share a name.
  Only the PSNP client id refuses. The check that matters is at group assignment,
  where one open membership per person is a database constraint.
- **A row whose cells cannot be read is rejected, not half-imported.** Dropping
  the bad cell and importing anyway would register a woman with no birth date —
  a record nothing downstream ever calls incomplete. She is named against her
  sheet row, and reported separately from rows queued for a woreda officer:
  those are different problems with different owners.
- **`read_rows` and `build_template` in `apps/youth/imports.py` now take a column
  set.** The ELS extract is a different sheet with identical problems, and a
  second copy of that parser would drift. `coerce_row` was extracted at the same
  time — `read_rows` returns *raw* cells, which is how the extract first arrived
  with `None` in every blank cell.

**`GET /wlt/profiles/{id}/journey/` is the four stages, read forwards.** The
stages existed only as services that refuse things: a facilitator learned a woman
was ineligible at the moment she tried to seat her, and was told *that* she was
refused rather than which condition was the problem. `services/journey.py`
assembles the same refusals using the gate vocabulary the readiness card renders.

- **Four states per stage, not two.** `waiting` is not `blocked`: verification is
  a woreda officer's judgement, and a facilitator reading "blocked" would go
  looking for something to fix that is not hers. Only `ready` carries a button.
- **The threshold shows only where it is still wanted.** Most conditions here are
  yes/no, and "Yes (need Yes)" says nothing while wrapping the rows that do need
  reading at 360px. The readiness card shows thresholds always because its values
  are quantitative.
- **A linkage type her group cannot reach yet is named with the phase it needs**,
  not omitted. "Savings account — needs Phase 2, group is at Phase 1" answers the
  question an empty list provokes.
- It computes on request, like the readiness card, so an exit or a verification
  shows immediately.

Screens: `/wlt/beneficiaries` (the register, with both enrolment routes) and
`/wlt/beneficiaries/<profile>` (the journey). The rail lists them first, in
workflow order.

### The largest gap

**Offline sync is not built, and it is on the critical path.** Open question Q3
asks whether the core has a sync layer; it does not. What exists is everything
that makes one possible without reopening the module — client-generated meeting
UUIDs, `device_id` and `synced_at` provenance, an append-only ledger, and
`wlt.SyncConflict`, which keeps a rejected duplicate meeting exactly as the
device sent it for a facilitator to resolve. **Financial records are never
auto-merged.** What is missing is the client, the queue and the delta protocol.
Afar and Somali were selected for weak infrastructure, so this is not a
deferrable nicety.

## Training and placement (`apps/training`, `apps/placements`) — Sprint 5

§4.5 Training Enrolment and §4.7 Placement, with the 30/60/90-day retention
checkpoints. Landing them filled four cards that had read "not built yet" since
the dashboards were written, and resolved the §7 LINKED scope for two roles that
had carried it since Sprint 0 with nothing to be linked through.

### The decisions worth keeping

- **A placement count and a placement record are different numbers, and both are
  reported.** `Referral.objects.placements()` is still *the* definition of a
  referral that ended in a job, and the funnel and loop-closure figures read it.
  `Placement` rows are what a person wrote up, and they include a youth who
  found work without a referral and exclude an outcome nobody has written up
  yet. `dashboard.outcomes.placement_coverage` reports the gap. Merging the two
  would have been tidier and would have produced a headline that moves when a
  data-entry backlog moves.
- **Nothing auto-creates a placement from a referral outcome.** §4.7 marks
  employer, sector, type and date all required, and a referral outcome carries
  none of them — an auto-created row would be four invented fields wearing the
  authority of a record. `services.backfill_from_referral_outcomes` **reports**
  the missing ones, the same way the alert engine raises a prompt and stops.
- **The three checkpoints open with the placement**, as `PENDING` rows. A
  checkpoint that exists only as arithmetic between today and a placement date
  cannot be listed, counted or assigned, and every screen would recompute it.
- **An exit closes the outstanding checks**, answering each from the date she
  left: a checkpoint that fell due before the exit was genuinely retained then.
  Answering all three as "exited" would understate 30-day retention for a youth
  who held the job two months.
- **`UNREACHABLE` is an answer, not a gap.** At 90 days a real share of youth
  cannot be contacted. Counting them as "not retained" overstates loss; as
  retained, overstates success. It is banded separately in every figure.
- **The retention denominator is answered checks, not placements.** Divide by
  placements and the rate falls every time the programme places somebody new —
  a figure that drops when the programme succeeds.
- **A failed assessment is not a dropout.** She attended to the end. It sits in
  the completion rate's denominator and not its numerator, and filing it as a
  dropout would hide an assessment problem that belongs to the provider.

### Two open questions closed here, and one that could not be

Both were on the list of schema changes that had to land **before** the first
placement was recorded or the first cohort would be permanently unreportable:

| Question | Implemented as |
|---|---|
| `is_subsidised` (OQ-3) | A flag on Placement. The reported anchor is "unsubsidised", and a placement whose wage the programme pays cannot be told apart afterwards. |
| `Placement.exit_reason` as an enum (OQ-5) | Eight values, ordered from the outcome the programme wants to the one it does not. "Left for a better job" and "dismissed" are opposite results, and §4.7's free text could not tell a report which had happened. A check constraint refuses an exit with no reason. |
| `psnp_client_category` (OQ-4) | Added to Youth, optional, three values following PSNP 4/5 practice and marked `TODO(open-question)` — the enumeration still needs FSCO. |

### Delivery records come from referrals, gated by category (2026-08-20)

Training enrolments (§4.5), placements (§4.7) and enterprise records (§4.8) all
require a `source_referral` on create, and **which referrals qualify is three
flags on the category row**: `ReferralCategory.creates_training_enrolment`,
`creates_placement`, `creates_enterprise`.

- **Not lists of codes.** They replaced `TRAINING_REFERRAL_CATEGORY_CODES`,
  `PLACEMENT_REFERRAL_CATEGORY_CODES` and `ENTERPRISE_REFERRAL_CATEGORY_CODES`
  in the three apps' `models.py`. §9 makes the taxonomy the administrator's to
  extend, and a tuple meant a category she added — "Vocational Training", a
  coaching partner that incubates businesses — silently could not open the
  record, with nothing on screen to say why and no fix short of a deploy. Same
  reasoning as `exempt_from_parallel_cap` and `counts_as_placement`. Migrations
  `referrals/0010` and `0012` turn the flags on for exactly the codes the tuples
  named, so no existing database changes behaviour.
- **`<record>_referral_error()` is the single definition** in each app, called by
  the service, the serializer and `Model.clean`. The serializer is the one that
  matters: where `perform_create` calls `serializer.save()`, a `ModelSerializer`
  does **not** run `full_clean`, so a rule stated only in `clean()` is not
  enforced over the API at all. That was live on **training and enterprises** —
  both proved by removing the serializer check and watching a wrong-category
  referral through. Placements already saved through the service and were safe;
  a test pins it now, because `perform_create` is one edit away from the other
  shape. Do not let the three callers drift apart.
- **The case is the referral's, never the client's.** The serializer derives it
  and refuses a mismatch, the same way `Case.woreda` is read-only.
- **Validation runs on add, not on every save.** Records written before this rule
  are still valid rows; re-validating them would make them uneditable rather
  than merely historical.
- **`CATEGORIES` in `seed_referral_taxonomy` is keyed, not positional.** The row
  carries five flags now, and an eight-element tuple is read by counting commas
  — which is how a flag lands on the wrong category. Omitted flags are False,
  and every flag is written on every row so a hand-set value is reset to the
  seeded default rather than kept silently.
- **`TrainingEnrolment.objects.awaiting_onward_prompt` is now a legacy sweep.**
  It covers enrolments with no source referral — "a youth put into a course
  directly" — which no new row can be. Kept rather than deleted: those rows
  exist, and their youth still need a next step. It raises nothing on a database
  seeded after this date, and `alerts.generate_training_onward_prompts` says so.
  The referral-side prompt covers everything else, which is what stops the two
  jobs raising one prompt twice.

**CM-4's "three consecutive training absences" is still uninstrumented**, and
now for a different reason: §4.5 asks for an attendance *rate*, and the platform
has no session-level register. A rate cannot answer the question, and putting
the condition's name on it would be a wrong label on a right number. The
condition it replaced — "left a placement with no exit reason" — is now
**unreachable rather than uninstrumented**, because the check constraint refuses
that state.

### `delivery_write` — a fifth key in ACCESS_MATRIX

§7 gives an employer liaison LINKED case scope and **no case write**, and she is
the person who records the placement and makes the 30/60/90-day calls. Gating
those writes on `case_write` left her looking at a queue she could not action.

`delivery_write` is that permission: true for the case manager, the trainer, the
employer liaison, the enterprise officer and the administrator; false for every
role that reads a programme rather than delivering it. It does **not** widen
case access — an employer liaison still cannot edit a case record.

### The LINKED scope finally resolves

`LINKED_THROUGH` in `apps/users/permissions.py` maps a role to the entity it is
linked through: a trainer to the enrolments she recorded, an employer liaison to
the placements she recorded. The lookup is written relative to a **Case**, and
every viewset over some other model declares `linked_case_prefix` — the path
back to the case.

**A viewset that omits it raises `FieldError` rather than returning a wrong
answer**, which is the right way round for a scoping bug, and it is how the
alerts, cases and youth viewsets were caught: before Sprint 5 the LINKED branch
returned `none()` for every role that could reach them, so the missing
declaration was invisible.

### Commands

```bash
$C exec web python manage.py seed_demo_sprint5            # 12 enrolments, 12 placements
$C exec web python manage.py seed_demo_sprint5 --refresh  # delete and rebuild
$C exec web pytest apps/training apps/placements -q
```

Screens: `/training` (the trainer's queue — **overdue courses lead the sort**,
because until the outcome is recorded the youth is neither in training nor
ready for a next step) and `/placements` (the employer liaison's, where the
**due-checks queue is the screen** and the placement list is behind a tab).

## Enterprise, follow-up and grievance — Sprint 6

`apps/enterprises` (§4.8), `apps/followups` (§4.9), `apps/grievances` (§4.10).
Landing them closed the last §4.13 alert type without a detector, instrumented
the last of CM-4's four conditions that could be instrumented, and resolved the
last §7 LINKED role.

### The one that matters most: verification

§8.3 makes the **externally verified** subset of outcomes the reportable
headline. That subset was always computable — and there was no way to *move* an
outcome into it. `verification_source` was a field somebody typed, so the
difference between the recorded placement rate and the reportable one was a
permanent shortfall rather than a queue.

`followups.services.verify_referral_outcome` is the route §6.2 always described
("outcome recorded and verified via follow-up visit"). It refuses three things,
each of which was reachable before it existed: a follow-up naming no referral, a
follow-up that **did not reach the youth**, and a referral with no recorded
outcome. It stamps source, verifier and method together, because those three
drifted apart when each was set by hand on a different screen.

`verification_source` is now read-only on the referral serializer for the same
reason `status` is. `/verification` is the M&E screen that works the queue.

### Decisions worth keeping

- **A grievance's `case` is nullable, and everything follows from that.** §4.10
  makes it optional; a complaints channel that only accepts complaints from
  people already on file is not a channel. So a grievance carries its **own
  woreda** and scopes by place rather than by caseload — a supervisor must see a
  complaint about a partner in her woreda whether or not it names her youth.
- **Sensitive complaints are narrowed further.** Safeguarding and staff conduct
  are visible only to the assigned staff member and the administrator, because
  the person complained about may be the supervisor who would otherwise read it.
  `GrievanceQuerySet.visible_to` is the one place that decides it.
- **`RESOLVED` and `CLOSED` are not the same**, and §4.10 is right to separate
  them. Resolved means something was done; closed means the file is shut, which
  also happens when a complainant withdraws. Folding them would inflate the
  resolution rate with every complaint nobody could pursue. Resolving requires
  saying what was done — in the service and in a check constraint.
- **A grant disbursed is not a business trading**, and trading is not surviving.
  Three separate fields, three separate counts, and only the third is an
  outcome. `record_disbursement` refuses money against an unapproved plan.
- **A missed milestone is recorded, never deleted.** A plan whose missed
  milestones vanish reads as a plan that went well.
- **The contact log is append-only through the API** (no PATCH, no DELETE). An
  attempt that can be edited afterwards is not evidence of anything, including
  the four failures CM-4 counts.
- **"Reached, not engaged" is not a failed contact.** She answered and declined;
  the case manager knows where she stands. Only `NO_RESPONSE` and `UNREACHABLE`
  count toward the at-risk condition.

### CM-4 is now three of four

The at-risk queue checks a stalled case **or** a youth with four or more failed
contact attempts in the current episode. The subquery is inlined into the scoped
statement rather than materialised, for two reasons that are both tests in
`apps/dashboard`: a `set()` cost a second round trip and broke the Tier 1 page's
12-query budget, and the AST scoping guard refuses any `.objects` that is not
narrowing a scoped base in the same statement.

The fourth condition — "3 consecutive training absences" — stays uninstrumented
and stays named on the card. §4.5 records an attendance *rate*, not a register,
and a rate cannot answer it.

### Three new thresholds, all unagreed

`FOLLOW_UP_DUE_DAYS` (14), `GRIEVANCE_RESPONSE_DAYS` (21) and
`FAILED_CONTACT_ATTEMPTS_AT_RISK` (4). Only the last comes from the spec — §5
says "4+". The other two are working defaults marked `TODO(open-question)` and
want the same conversation the confirmation threshold had on 2026-08-18.

The **Follow-Up Due condition itself** is also undefined by the spec, which names
the alert type and stops. The working definition lives in
`followups.services.awaiting_follow_up`: an Active referral past the threshold
with no contact attempt recorded against it since. It is written there, not in
the job, so the screen and the inbox read the same one.

### Commands

```bash
$C exec web python manage.py seed_demo_sprint6            # 8 enterprises, 21 contacts, 4 grievances
$C exec web python manage.py seed_demo_sprint6 --refresh
$C exec web pytest apps/enterprises apps/followups apps/grievances -q
```

Screens: `/enterprises` (the officer's — **awaiting disbursement leads**, because
that delay is the programme's), `/verification` (M&E's two queues) and
`/grievances` (**overdue leads**, for the same reason).

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
