# WLT module: build response

What was built against this handoff, what was adapted, and what was not built.
Written to be read beside `START_HERE.md` — it answers the six questions the
package raises for the receiving team in `OPEN_QUESTIONS.md`, and records every
place the implementation departs from the specification.

**Status: stages 0 to 8 are built in the backend, with the three screens the
handoff calls behaviour-changing.** Stage 9 (credit facility, federation) is
schema and gates only, as D8 asks.

---

## 1. The one architectural decision that changed

**D4 — "service linkage rides the existing referral engine" — is implemented in
half.** The subject generalises; the lifecycle does not.

`sql/000_core_stubs.sql` models a referral engine this platform does not have.
Its stub carries `type_code`, `provider_id`, a person subject and a twelve-state
lifecycle (`proposed` … `defaulted`). The real `referrals.Referral` hangs off a
**Case**, not a person; it uses `referral_category` and `receiving_partner`; and
its `status` is the youth spec's §6.2 table transcribed — six states, shaped
around a partner confirming a referral for one young person.

The two state machines share no state but "active". Folding them into one field
would have meant re-auditing every youth-side queryset, all four dashboard
tiers, four alert jobs and the referral stack timeline for group-subject
leakage — which this package itself calls the highest-risk item in the plan.

So the split is:

| | Where it lives | Why |
|---|---|---|
| **Subject generalisation** | `referrals.Referral` | Exactly as D4 specifies: typed nullable FK columns, an exactly-one check constraint, a generated `subject_type`, and `allowed_subject_types` on the category row. All three of D4's reasons for rejecting a `GenericForeignKey` hold here unchanged. |
| **Service referral (W7)** | `referrals.Referral` | The thin workflow, riding the engine unchanged, with no lifecycle of its own. `wlt.services.linkage.create_service_referral` is the whole of it. |
| **Gated linkage (W4, W5, W6, cooperative)** | `wlt.ServiceLinkage` | Twelve states, screening, a multi-level approval chain, a distress cascade. It shares the provider directory (`partners.Partner`), the gate service and the reporting funnel. What is not shared is the state machine, which was never the same machine. |

The decision was put to the programme before any of it was written, with the
literal reading and the full reversal offered as alternatives. The consequence
to hold onto: `mv_linkage_funnel` reads **two** tables, as a union with a
`source` column.

## 2. What the core platform actually looks like

`OPEN_QUESTIONS.md` asks six questions about the real codebase. Answered:

| Question | Answer |
|---|---|
| What does `core.Person` look like? | It is `youth.Youth` — the platform's only person table, named for the youth-employment programme it was built for. UUID pk, location as **text** fields (region/zone/woreda/kebele), consent required at write time, `simple_history` audit. A WLT member is a `Youth` row. The age band is a warning, not a constraint, so an adult PSNP woman sits in it honestly. |
| Does the geography hierarchy exist, and are the five regions seeded? | Yes — `locations.Location`, self-referencing, region → zone → woreda → kebele, and all five WLT regions are already in `seed_locations`. **No zones, woredas or kebeles existed under them**; `seed_wlt_policy` adds one illustrative woreda and two kebeles per region. The real pilot sites are a programme decision. |
| Is there an existing provider directory? | Yes — `partners.Partner`, with `woreda_coverage` already carrying provider geography. Three provider types were added (`RUSACCO`, `COOPERATIVE`, `BUYER`) and a `standing` field for suspension and blacklisting. |
| How does the RBAC express scope? | `apps/users/models.ACCESS_MATRIX`, one row per role, read by `scope_queryset`. Extended with `group_scope` / `group_write` and a parallel `scope_group_queryset`. See §4. |
| Is the PSNP client ID available? | Not from any integration. It is a field on `wlt.BeneficiaryProfile` populated by the import, and the import is the only channel. Reconciliation with the PSNP MIS remains unbuilt because there is nothing to reconcile against. |
| What is the materialized-view refresh orchestration? | There was none in the live database — the youth-side `rpt` schema is blocked (see CLAUDE.md). The WLT views are created in migration `wlt/0004_reporting_views`, refreshed by `wlt_refresh_reporting()`, and driven by `manage.py refresh_wlt_reporting` and a Celery task. |

Other adaptations, all mechanical:

- **Uppercase enum values.** `GroupStatus.ACTIVE`, not `'active'`. The platform's
  convention is `TextChoices`, and the SQL's lowercase codes would have been the
  only lowercase enums in the database.
- **Django table names**, `wlt_group` rather than `wlt.group`. Reading them as
  `wlt.<table>` gives the handoff's names exactly.
- **`Money` is `DecimalField(14, 2)`**, never float, as `DEFINITIONS.md` §4 asks.

## 3. Where a number differs from `sql/004`, and why

Four departures, each of which changes a reported figure:

1. **PAR30 references the earliest unpaid instalment**, not `loan.due_on`. The
   bundle flags this as a known limitation of its own view and puts the fix in
   its punch list; `services/indicators.py` and `wlt_mv_group_financials` both do
   it the corrected way, because two definitions of PAR30 in one system is
   exactly what `DEFINITIONS.md` forbids.
2. **Fund adequacy is converted to weeks by the group's own cadence.** The
   bundle divides the fund by one period's contributions and calls the result
   weeks, which for a monthly group reports months. A threshold stated in weeks
   has to mean weeks for every group.
3. **A completed loan cycle requires every loan in the batch to be settled.**
   The bundle counts distinct `cycle_batch` among repaid loans, which credits a
   cycle whose other loans are still outstanding.
4. **Meeting adherence counts meetings held *inside the window*,** not the last
   twelve whenever they happened. Those are the same number for a healthy group
   and very different ones for a group that has stopped meeting: its last twelve
   are still twelve, so the bundle's reading would report 100% adherence for a
   group that has not met since March.

One departure in `sql/002`: the phase-event trigger blocks every `UPDATE`, which
would make a submission impossible to approve — approving one writes the decision
onto the row. Here the row **locks when it is decided** (`OLD.decided_at IS NOT
NULL`), which is the property A26 is actually about. Both cases are tested.

## 4. Permissions

The handoff's §9 table needs four roles this platform did not have. They were
added to `Role` and `ACCESS_MATRIX` rather than mapped onto the existing ten:

`WLT_FACILITATOR` · `WLT_WOREDA_OFFICER` · `WLT_REGION_OFFICER` · `WLT_FEDERAL_OFFICER`

**Every one has `case_scope: NONE`.** That is the module boundary, expressed
once, in the table every permission class reads. The alternative — mapping a
facilitator onto `OUTREACH_WORKER` and a woreda officer onto `SUPERVISOR` —
would have carried a youth case scope into the group domain, and S0.3's rule
("a facilitator who can see a group roster must not thereby see those women's
youth-side case files") would then depend on every viewset remembering.

Symmetrically, every youth-side role has `group_scope: NONE`. Both directions are
tested, on the same woman, in `apps/wlt/tests/test_boundary.py`.

Group scoping keys off `User.wlt_scope_location`, a nullable FK to any level of
the hierarchy — the handoff's `app_user.scope_geo_id`. `woreda_assignment` stays
what it is on the youth side: a list of woreda *names*, which cannot express a
region without re-listing every woreda in it.

## 5. What is built

| Stage | State |
|---|---|
| 0 Platform prep | **Built.** Referral subject generalisation (no data migration needed — see below), subject-type restrictions, RBAC object scoping, offline-shaped capture. |
| 1 Registry extension | **Built.** `BeneficiaryProfile`, the import pipeline with fuzzy-match queue, the exception route and its verification, allocations, candidate pool. |
| 2 Group formation | **Built.** Mobilisation, draft, hard blocks and soft warnings, overrides, bylaws, officers, constitution, activation, membership changes, expiry sweeps. |
| 3 Meetings and savings | **Built.** Meeting capture, attendance, savings, till reconciliation, append-only ledger with reversals. |
| 4 Policy and indicators | **Built.** `wlt/policy.py` with effective-dated geographic resolution, every formula in `DEFINITIONS.md`, the readiness card. |
| 5 Lending | **Built.** Loan lifecycle, all three service-charge bases, PAR30, cycles, write-offs. |
| 6 Phase machine | **Built.** Gates, submission, approval with re-evaluation, evidence snapshots, at-risk, dormancy, de-graduation. |
| 7 Service linkage | **Built.** Full lifecycle, provider directory with geography and blacklisting, savings account and the two-balance ledger, market offtake, service referral, funnel reporting. |
| 8 Structural linkage | **Built** (schema and services). CLA formation events, delegates and rotation, structural membership, CLA readiness, withdrawal and dissolution. |
| 9 Credit and federation | **Schema and gates only**, per D8. No UI. |

### The migration runbook collapses

`django/MIGRATION_REFERRAL_SUBJECT.md` describes eight stages to swap
`person_id` for `subject_person_id` on a live table: backfill, dual-write,
parity check, cut over, drop. **None of it applies here**, because `case` was
not replaced. It became one of five subject slots, and every existing row
already satisfies the new check constraint. The migration adds columns and a
constraint; there is no window in which a referral has two subjects or none.

The runbook's *regression suite* does apply, and it is written:
`apps/wlt/tests/test_referral_subject.py` covers the youth referral list, detail
resolution, the state machine, reporting, and — the row the runbook calls the
highest risk in the plan — visibility in both directions.

## 6. What is not built, and why

- **Offline sync (S0.4) is partial, and this is the largest gap.** Open question
  Q3 asks whether the core has a sync layer. It does not — the mobile client is
  Sprints 8–9 of the youth programme and does not exist. What is built is
  everything that makes a sync layer possible without reopening this module:
  client-generated UUIDs on meetings, `device_id` and `synced_at` provenance, an
  append-only ledger, and `wlt.SyncConflict`, which keeps a rejected duplicate
  meeting *exactly as the device sent it* for a facilitator to resolve. What is
  not built is the client, the queue and the delta protocol. **This is platform
  work on the critical path, and the handoff is right that it changes the
  estimate materially.**
- **Federation UI**, per D8 — arithmetically unreachable in the pre-pilot.
- **The Amharic, Somali and Afar tables.** Every string goes through `gettext`
  and `t()`, and the tables are empty pending a translator, exactly as the youth
  side is. Note the handoff wants **Somali and Afar** as well as Amharic and
  Afaan Oromo; the language switch currently offers three.
- **A device floor and battery measurement.** Cross-cutting items with no code to
  attach to until there is a client.

## 7. Open questions, as implemented

Every seeded value is a row in `wlt.PolicyParameter`, editable in the admin. A
default is not an agreement.

| # | Question | Implemented as |
|---|---|---|
| Q1 | Share-out or accumulate | **Accumulating.** The ledger has no cycle dimension and the fund never resets. If FSCO says share-out, `LedgerEntry` needs a cycle and fund adequacy has to be measured within one — that is a migration, not a setting. Still the largest unstated decision in the handbook. |
| Q2 | Can the referral subject generalise | **Yes, the subject can; the lifecycle cannot.** See §1. |
| Q3 | Does the core have offline sync | **No.** See §6. |
| Q4 | Service charge basis | **Nullable, no default.** All three bases implemented; the form cannot be submitted without an explicit choice, and the basis is frozen on the loan at disbursement. |
| Q5 | Default days past due | **30**, `loan.default_days_past_due`. |
| Q6 | CLA threshold | **8**, `gate.cla.min_groups`. |
| Q7 | Federation threshold | **10**, `gate.federation.min_clas`. |
| Q8 | Group size | **Hard 15–25, soft warn 18–22.** |
| Q9 | What is the social fund | **A ledger entry type with no rules.** The P2 gate asks only whether the group has one, which is the most the handbook supports. |
| Q10 | WLT membership and youth cases | **Independent.** A woman may hold both; neither is visible from the other. |

Two items the handoff leaves open that the build had to decide:

- **Does `absent_excused` count against attendance?** It currently does. The
  status is its own value so the rule can change without a migration.
- **Where do fuzzy matches stop being offered?** 0.86 similarity on name plus
  place, adjusted by birth-year gap. The threshold decides what is worth a
  woreda officer's attention; it never decides what is true, and nothing is ever
  auto-merged at any score.

## 8. How to run it

```bash
cd infra
C="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

$C exec web python manage.py migrate
$C exec web python manage.py seed_locations          # the five regions
$C exec web python manage.py seed_wlt_policy         # parameters, allocations, pilot sites
$C exec web python manage.py seed_wlt_taxonomy       # linkage types, WLT referral categories
$C exec web python manage.py refresh_wlt_reporting   # build the materialized views

$C exec web pytest apps/wlt -q                       # the module's own suite
$C exec web pytest -q                                # everything, including the youth regression
```

Screens: `/wlt/groups`, `/wlt/groups/<id>` (the readiness card), `/wlt/linkages`
(the blocked-gate screen), `/wlt/cla-readiness`. API under `/api/v1/wlt/`.

## 9. Where the assertions went

`sql/900`'s 32 assertions are mirrored in `apps/wlt/tests/test_assertions.py`
and `test_referral_subject.py`, one test per assertion, named for it. They are
re-expressed against the real models rather than run as SQL, because the
bundle's suite needs `sql/000`'s idealised schema to run at all.

Most are checked **twice**: once through the service layer, where the error
message is the product ("counted 5,000, expected 5,200 — a difference of 200"),
and once by bypassing it, because the service is not the only writer. The admin,
a data fix and a future sync reconciler all reach these tables, and an
append-only ledger that only one path respects is not append-only.
