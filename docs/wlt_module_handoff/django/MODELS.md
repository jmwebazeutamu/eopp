# Django app layout and model notes

Notes on what the ORM layer needs beyond a direct translation of `sql/001_wlt_schema.sql`. Field-level detail is in the DDL; this covers the things a straight `inspectdb` will not tell you.

---

## App layout

```
apps/
  core/                  existing: person, geography, rbac, audit
  referrals/             existing: referral engine + stack timeline
                         CHANGED in stage 0 (polymorphic subject)
  wlt/
    models/
      registry.py        BeneficiaryProfile, ImportMatchCandidate
      formation.py       MobilisationEvent, Group, BylawVersion,
                         GroupMembership, OfficeHolder, TrainingEvent,
                         ValidationOverride
      ledger.py          Meeting, Attendance, LedgerEntry, Loan,
                         LoanSchedule, Repayment
      phase.py           PhaseEvent, RiskFlag
      structure.py       CLA, Federation, FormationEvent,
                         FormationCandidate, StructuralMembership, Delegate
      policy.py          PolicyParameter, PolicyVersion, EnrolmentAllocation
    services/            ALL business logic lives here
      enrolment.py       import pipeline, matching, verification
      formation.py       draft, validate, constitute, activate
      ledger.py          savings, loans, repayments, reconciliation, reversals
      indicators.py      the formulas in DEFINITIONS.md
      gates.py           eligibility evaluation against policy
      phase.py           transition submission and approval
      linkage.py         service linkage lifecycle over referrals
      structure.py       CLA and federation formation events
    policy/              parameter resolution with effective dating
    api/                 DRF viewsets, thin
    sync/                offline reconciliation
    reporting/           WLT materialized views + refresh hooks
```

**No business rules in models or views.** Gates, ledger rules and linkage transitions live in `services/`, in one testable place, because FSCO will change them mid-pilot.

---

## Models that need care

### `Group`
Status and phase are separate fields, not one. Status is the lifecycle (draft, constituted, active, at_risk, dormant, split, merged, dissolved, abandoned). Phase is maturity (p1 to p4) and is null until activation. A check constraint keeps them consistent.

### `GroupMembership`, `OfficeHolder`, `StructuralMembership`, `Delegate`, `BylawVersion`
All are **dated ranges**. Never add an `is_active` boolean; it will drift from the dates. The partial unique indexes in `002` enforce "one open row" and Django will not create them from `unique_together` alone. Declare them explicitly:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['person'],
            condition=models.Q(exited_on__isnull=True),
            name='group_membership_one_open_per_person',
        )
    ]
```

### `LedgerEntry`
Append-only, enforced by database trigger. Give the model no `save()` path for updates and no delete. A correction creates a new row with `reverses` set and a mandatory reason. Django's `.update()` and `.delete()` will raise; that is intended, so catch it in the service layer and return a useful message.

### `PhaseEvent`
Immutable, same treatment. `gate_snapshot` is `JSONField`. It is the audit defence when someone questions a graduation two years later, so serialise the whole `GateResult`, not a summary.

### `Meeting`
`status = 'closed'` fires the reconciliation trigger. Closing is a service operation, not a model save. Surface the trigger's error message to the facilitator verbatim: it names the discrepancy in birr.

### `PolicyParameter`
Resolution order is woreda override, then region, then global, each filtered by effective date. Cache per request. `wlt.policy_int()` in `004_reporting_views.sql` shows the SQL-side equivalent for reporting.

---

## The gate service contract

```python
@dataclass
class Condition:
    code: str
    threshold: Any
    actual: Any
    met: bool

@dataclass
class GateResult:
    passed: bool
    conditions: list[Condition]
    policy_version_id: UUID
    computed_at: datetime
```

Two rules:

1. **Always return `actual` next to `threshold`.** The UI shows "Attendance 74% (need 80%)". A red dot changes nothing about facilitator behaviour; a number does.
2. **Serialise the whole `GateResult` into the decision record.** Not just `passed`.

Compute nightly for dashboards and on write for immediate feedback. The immediate feedback at meeting close is most of the module's behaviour-change value.

---

## Offline sync

| Operation | Offline |
|---|---|
| Meeting, attendance, savings, repayments | Yes. The core requirement |
| Loan disbursement | Yes, with local balance validation |
| Readiness card | Yes, from last sync, stamped with sync time |
| Propose a linkage | Queued offline, submitted on sync |
| Approve anything | No. Online only |
| Formation events | Delegate capture offline, submission online |

Client generates UUIDs, so ids are stable across sync. Meetings are append-only per group and date, so genuine conflicts are rare. Where two devices record the same meeting, keep both, flag for facilitator resolution, and **never auto-merge financial records**.

A stale readiness card that is honest about its age beats a fresh one that is wrong.

---

## Testing

Mirror the SQL assertions in the Python suite so the rules are enforced at both layers:

- Roster and membership: A1, A7, A12, A13
- Reconciliation and ledger immutability: A4, A5, A6
- Loan lifecycle and PAR30: A9, A10, A11
- Referral subject integrity and safeguarding: A15 to A20
- Structural hierarchy and delegates: A21, A22, A23
- Governance and immutability: A24, A25, A26
- Bylaw versioning: A27, A28

Add Python-level tests the database cannot express: permission boundaries between modules, offline conflict handling, gate evaluation against fixture datasets, and the import pipeline's idempotency.
