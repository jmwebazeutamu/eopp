# Start Here

Dashboard and reporting handoff for the Youth Employment Case Management and Referral Platform, Ethiopia.

This file explains what every other file is for and who uses it. Read this first, then go to the one file your role needs.

## What this bundle is

A build specification for four dashboards, with the database layer written and tested rather than described. It replaces Section 8 of `YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`, which listed nine dashboards in a flat table with no audience split and no visualisation guidance.

The four dashboards, and the 25 cards in them:

| Tier | User | Cards | Built in |
|---|---|---|---|
| 1 Operational | Case manager | CM-1 to CM-6, plus CM-7 on the case detail screen | Django |
| 2 Tactical | Woreda supervisor | WS-1 to WS-6 | Metabase |
| 3 Analytical | Programme manager | PM-1 to PM-8 | Metabase |
| 4 Strategic | M&E and World Bank | ME-1 to ME-5 | Metabase |

Card IDs are used consistently across every file, including the punch list and the prototype markup. Quote them in tickets.

## Read this one file, by role

| You are | Read | Time |
|---|---|---|
| Product manager or task team lead | `README.md` sections 1, 2 and 9 | 15 min |
| Backend engineer | `sql/` in filename order, then `README.md` section 3 | 1 hour |
| Frontend or Django engineer | `django/CASE_MANAGER_DASHBOARD.md` | 40 min |
| M&E lead | `README.md` sections 6 and 8 | 20 min |
| Coding agent | `README.md` in full, then the paste block at its top | n/a |
| Anyone triaging the current build | `PUNCH_LIST_v1.md` | 10 min |

## Every file, and how to use it

### Specifications

| File | Who | What it is | How to use it |
|---|---|---|---|
| `README.md` | Everyone | The authoritative spec. Four tiers, 25 card contracts, indicator definitions, visualisation decisions and what was rejected, cross-cutting rules, 12 open questions, definition of done. | Copy the paste block at the top into Claude Code to start the build. Humans read sections 1 to 3 for the shape, 4 to 6 for the cards, 8 for the rules. |
| `django/CASE_MANAGER_DASHBOARD.md` | Django engineer | Tier 1 implementation contract. Route, view, RBAC scoping code, six card querysets, acceptance criteria. | Build against it directly. Section 8 is the definition of done for Tier 1. |
| `PUNCH_LIST_v1.md` | Whoever triages the build | Built app measured against the spec. **Version 2** covers Tiers 1 and 2 and corrects two version 1 findings. Two P1 items, ten P2 on Tier 1, twelve findings on Tier 2, plus a checklist for Tiers 3 and 4. | Raise one ticket per item, quoting the item ID (P1-2, W-1) and the card ID. Section 6 gives the fix order, section 7 the two decisions needed. |
| `START_HERE.md` | Everyone | This file. | You are here. |

### Database layer, runnable

Run in filename order. `000` and `900` are test-only and never touch staging or production.

| File | What it creates | Notes |
|---|---|---|
| `sql/000_test_fixture_schema.sql` | Stub application tables | **TEST ONLY.** Django owns these tables through migrations. This exists so the reporting layer can be tested before the Django apps are built. If a column here disagrees with the Django model, the model wins. |
| `sql/001_reporting_schema.sql` | The `rpt` schema, the `metabase_ro` read-only role, `rpt.reporting_parameters`, taxonomy lookups | Change the password on line 27 before running. Every tunable threshold lives in `reporting_parameters`: suppression bands, confirmation threshold, maturation window, youth age band. Wire it into Django admin. |
| `sql/002_helper_functions.sql` | Suppression bands, Wilson intervals, funnel-plot verdicts, age bands, maturation guards | These enforce the rules. A Metabase question that computes a percentage inline instead of calling `rpt.rate_label()` is a defect. |
| `sql/003_materialized_views.sql` | 14 materialised views, one per card group | The reporting layer proper. Metabase reads these and never the application tables. |
| `sql/004_indexes.sql` | Indexes on application tables and on the views | The unique indexes are required, not optional. Without them `REFRESH ... CONCURRENTLY` fails and every dashboard blocks during refresh. |
| `sql/005_refresh.sql` | Refresh procedures, freshness view, Celery beat schedule | The commented block at the bottom goes into `backend/config/celery.py`. Set `app.conf.timezone = "Africa/Addis_Ababa"` or the times fire three hours late. |
| `sql/900_test_seed_and_assertions.sql` | Seeded fixtures and 17 assertion groups | **TEST ONLY.** Wire into CI as a blocking gate. It targets the specific ways this class of dashboard reports something false. |

### Design references

| File | Who | How to use it |
|---|---|---|
| `prototype/Youth_Employment_Dashboard_Prototype_v1.html` | Everyone | Open in a browser. Five tabs: the four dashboards plus a rationale tab explaining every variable and chart choice. Self-contained, no server needed. Each card heading carries its ID as a `data-card` attribute and a visible chip. **A design reference, not production code.** The data is illustrative. |
| `django/referral_stack_svg.py` | Django engineer | Reference implementation of CM-7, the per-youth referral timeline. Copy into `apps/referrals/rendering.py`. Server-rendered inline SVG, no charting library. The test list at the bottom of the file is the test suite to write. |
| `screenshots/01-case-manager.png` | Anyone in a meeting | Tier 1 rendered in full. Drop into slides. |
| `screenshots/02-woreda-supervisor.png` | Anyone in a meeting | Tier 2 rendered in full. |
| `screenshots/03-programme-manager.png` | Anyone in a meeting | Tier 3 rendered in full. |
| `screenshots/04-me-donor.png` | M&E lead, task team | Tier 4 rendered in full. |
| `screenshots/05-variables-rationale.png` | Anyone challenging a chart choice | The rationale tab. Every variable, its source field, its chart type, and what was rejected. |
| `screenshots/06-referral-stack-timeline.png` | Django engineer | CM-7 as rendered by `referral_stack_svg.py`. The shape to match. |

### Two files that live outside this folder

Both sit beside this folder and are referenced throughout.

| File | Why it matters here |
|---|---|
| `../design_handoff_youth_employment/README.md` | Authoritative for design tokens, colours, type and component specs. Do not invent a colour. |
| `../REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md` | The React version of CM-7 and its `ReferralTimelineItem` data contract. `referral_stack_svg.py` mirrors that contract field for field. If one changes, change both. |

## Quickstart: prove the database layer works

Takes about two minutes on any Postgres 14 or later.

```bash
createdb yep_reporting_test

cd dashboard_handoff_youth_employment/sql
for f in 000_test_fixture_schema 001_reporting_schema 002_helper_functions \
         003_materialized_views 005_refresh 004_indexes; do
  psql -v ON_ERROR_STOP=1 -d yep_reporting_test -f ${f}.sql
done

psql -v ON_ERROR_STOP=1 -d yep_reporting_test -f 900_test_seed_and_assertions.sql
```

Expected last line:

```
NOTICE:  ALL REPORTING LAYER ASSERTIONS PASSED
```

Note the order: `005` runs before `004`. The refresh procedures are created first, and the indexes they depend on come after, because `900` calls `rpt.refresh_all()` and needs both present.

Against a real database, skip `000` and `900`. Django owns those tables, and `900` truncates them.

## Reading order for a human

1. This file.
2. `README.md` sections 1 and 2. Four tiers, and the two architecture calls that change the Dev Spec.
3. Open the prototype. Click through all five tabs. The rationale tab answers most questions the spec raises.
4. `README.md` section 7. What chart was chosen for each data shape, and what was rejected.
5. `README.md` section 9. The 12 open questions. Five of them add fields to entities in Dev Spec Section 4, so they need a decision before the schema settles.
6. `PUNCH_LIST_v1.md` if you are reviewing the current build.

## The three rules that matter most

If nothing else survives from this bundle, keep these. Each is enforced in SQL, not left to reviewer memory.

1. **No percentage without its denominator.** Below n=30 a rate is marked provisional and never used in a comparison. Below n=10 it is suppressed, and the numerator is withheld too. `rpt.rate_label()` enforces this by construction.
2. **Nothing is scored before it is due.** A youth placed 20 days ago is not a 30-day retention failure. A referral raised 3 days ago is not an unclosed loop. `rpt.is_mature()` guards every checkpoint denominator. Without it, rates collapse at every period boundary and staff learn to stop raising referrals late in the quarter.
3. **Never rank partners by rate.** Sort by denominator. With these sample sizes, rate-ranking sorts by luck, and it is politically irreversible once published.
