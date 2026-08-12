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
$C exec web python manage.py seed_locations    # Ethiopian admin hierarchy, idempotent
```

Frontend (`web/`, runs on the host, not in a container):

```bash
cd web
npm install
npm run dev        # Vite on 8100, proxies /api -> localhost:8007
npm run build      # tsc -b && vite build — this is the typecheck gate
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
- **Sprint 4 — next.** Onward/replacement auto-prompts materialised as Alerts
  (§4.13), stall and confirmation-overdue detection, Celery beat jobs,
  "next action" on the case screen.

Later sprints: 5 training/placement · 6 enterprise/follow-up/grievance ·
7 dashboards · 8–9 mobile · 10 hardening.

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
  `awaiting_replacement_prompt()` are querysets; Sprint 4's job materialises
  them into Alerts. Keep the queryset as the single definition.

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
- **`User.partner` does not exist yet.** It arrives with the Partner entity in
  Sprint 2. Until then `PARTNER_STAFF` accounts are scoped to nothing, by design.
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
