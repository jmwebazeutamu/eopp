# Backlog

Nine stages. Stages 0 to 7 are the pre-pilot. Each story has acceptance criteria written so they can be tested, and a pointer to the SQL assertion that covers the invariant where one exists.

Estimates are deliberately absent. Size them against your own team.

---

## Stage 0. Platform prep

The only work that touches live core code. Highest risk in the plan. Do not price it as plumbing.

### S0.1 Generalise the referral subject
Follow `django/MIGRATION_REFERRAL_SUBJECT.md` exactly. Eight sub-stages, do not compress 5 to 8 into one release.

**Acceptance**
- A referral can be created against a person, group, CLA or federation
- A referral with two subjects is rejected (A16)
- A referral with zero subjects is rejected (A17)
- Deleting a group with an open referral is prevented by the FK
- Every existing youth-side referral still resolves, renders and reports identically
- The referral timeline component renders a group-subject referral with a group header

### S0.2 Referral type subject restrictions
Add `allowed_subject_types` to `referrals.referral_type`, enforced by trigger.

**Acceptance**
- A protection or GBV referral type permits `person` only and is rejected for a group (A18)
- The same type is accepted for a person (A19)
- `credit_facility` is rejected for a group while `gate.credit.allow_group_subject` is false (A20)

### S0.3 RBAC object scoping
Extend geographic scoping with group-level object rules.

**Acceptance**
- A facilitator sees only groups in her kebele scope
- A woreda officer sees all groups in her woreda
- **A facilitator with access to a group roster cannot read those women's youth-side case records**
- A youth case worker cannot read WLT ledger data
- No self-approval: the submitter of a phase or linkage decision cannot be its approver (A24)

### S0.4 Offline sync
Confirm the core sync layer exists, or build it. See Q3.

**Acceptance**
- A meeting records end to end with no connectivity and syncs later
- Two devices recording the same meeting produce a flagged conflict, never a silent merge
- Financial records are never auto-merged
- A stale readiness card displays its sync time

---

## Stage 1. Registry extension

### S1.1 Beneficiary profile
`wlt.beneficiary_profile`, one-to-one with `core.Person`.

**Acceptance**
- Nothing WLT-specific is added to `core.Person`
- A profile cannot be marked `verified` without a verifier and a date
- Programme eligibility computes from ELS completion, grant receipt, sex and PSNP status

### S1.2 Caseload import
**Acceptance**
- Records matching an existing PSNP client ID link to that person, no duplicate created
- Records with no ID and a high-confidence name/kebele/age match queue for woreda confirmation, **never auto-merge**
- Records with no match create a new person and a `verified` profile with `enrolment_route = 'import'`
- The import is idempotent: running the same extract twice creates nothing new
- A rejected match is recorded with a reason, not deleted

### S1.3 Facilitator exception route
**Acceptance**
- A facilitator-added woman starts at `verification_status = 'pending'`
- A pending woman cannot be added to a group
- A woreda officer can verify or reject with a recorded reason
- `mv_enrolment_vs_allocation.exception_route_pct` reports the share per region

### S1.4 Allocation ceilings
**Acceptance**
- Facilitator sees a warning at 90% of a region's allocation
- Group activation past the ceiling is blocked unless a region-level override is recorded with a reason
- Allocations are policy data, editable without deployment (A31)

### S1.5 Candidate pool view
**Acceptance**
- Lists eligible, verified, unassigned women in a kebele
- Shows literacy, device access and primary IGA so a facilitator can compose a workable group
- Excludes anyone with an open membership elsewhere

---

## Stage 2. Group formation

### S2.1 Mobilisation events
**Acceptance**
- Records kebele, date, facilitator, attendee counts by category, endorsement obtained yes or no
- **A refused endorsement is recorded and reported** (A30)
- No individual attendee names are stored beyond the facilitator

### S2.2 Draft and roster
**Acceptance**
- Hard blocks: ineligible, unverified, already in an active group, fewer than 15 members, no treasurer
- Soft warnings: roster outside 18 to 22, no literate member, no member with a device, mixed kebele, allocation above 90%
- Every soft-warning override writes a `wlt.validation_override` row with a reason
- A woman cannot be selected into two drafts (A7)
- A draft expires after 60 days and its members return to the pool. The draft is retained, not deleted

### S2.3 Bylaws
**Acceptance**
- v1 captures cadence, day, contribution, service charge basis and rate, penalties, rotation period, quorum, max concurrent loans, reserve buffer
- `service_charge_basis` has **no default**; the form cannot be submitted without an explicit choice
- Only one version in force per group (A27)
- Superseding v1 with v2 retains v1 for historical compliance (A28)
- Local-language clause text is stored alongside the structured fields

### S2.4 Officers
**Acceptance**
- Chair, secretary and treasurer recorded with a term start
- Two concurrent holders of one office are rejected (A8)
- Rotation closes the old term and opens a new one, never edits in place
- An alert fires when a term exceeds the bylaw rotation period

### S2.5 Constitution and activation
**Acceptance**
- Constitution locks the roster; later changes go through the membership change flow
- Activation requires a first savings meeting closed with a balanced till
- A group constituted but not activated within 30 days is reported as attrition
- On activation, `current_phase` becomes `p1`

### S2.6 Membership changes
**Acceptance**
- Join requires eligible, verified and no open membership elsewhere
- Her savings compliance counts from her join date, not the group's
- Exit requires a reason code
- **Exit is blocked while she has an outstanding loan** (A11)
- A clean exit reduces the current roster and leaves historical indicators untouched (A12, A13, A14)

---

## Stage 3. Meetings and savings

### S3.1 Meeting capture
**Acceptance**
- Attendance, savings, fines and social fund recorded per member
- Social discussion time and topic recorded; a warning below the 15-minute minimum
- Meeting numbers are unique and sequential per group
- Works fully offline

### S3.2 Till reconciliation
**Acceptance**
- **A meeting cannot close on an unbalanced till** (A4)
- The error names the discrepancy in birr, not a generic failure
- A failed reconciliation raises an at-risk flag

### S3.3 Append-only ledger
**Acceptance**
- `UPDATE` and `DELETE` on `wlt.ledger_entry` are rejected at the database (A5, A6)
- A correction posts a reversal referencing the original, with a mandatory reason
- Every entry carries who and when

---

## Stage 4. Policy and indicators

### S4.1 Policy parameter layer
**Acceptance**
- Resolution order: woreda override, then region, then global, all effective-dated
- No gate logic reads a constant
- A parameter change does not require deployment

### S4.2 Indicator service
**Acceptance**
- Every formula in `DEFINITIONS.md` implemented and matching hand calculation on the seed fixtures
- Attendance and compliance use `roster_on`, not the current roster (A13, A14)
- Computed nightly and on meeting close

### S4.3 Readiness card
**Acceptance**
- **Shows the actual value next to the threshold**: "Attendance 74% (need 80%)", not a red dot
- Updates immediately on meeting close
- Works offline from last sync with a visible sync timestamp

---

## Stage 5. Lending

### S5.1 Loan lifecycle
**Acceptance**
- Requested, approved, disbursed, repaid, written off
- Approval requires the bylaw quorum
- Disbursement writes a ledger entry and cannot precede the group's 10th savings meeting
- Concurrent loans capped per bylaw; reserve buffer respected

### S5.2 Service charge engine
**Acceptance**
- All three bases implemented: flat per loan, per month, declining balance
- The per-group label ("service charge" or "interest") is applied in every UI surface and export
- Basis and rate at disbursement are frozen on the loan, not read live from the bylaw

### S5.3 PAR30 and cycles
**Acceptance**
- PAR30 matches the definition in `DEFINITIONS.md` (A9, A10)
- Cycle completion requires every loan in the batch fully repaid
- **Known limitation to fix here:** PAR30 currently references `loan.due_on`. Switch to the earliest unpaid instalment in `wlt.loan_schedule`

---

## Stage 6. Phase machine

### S6.1 Gates and transitions
**Acceptance**
- P1 and P2 gates evaluated per `DEFINITIONS.md`
- The system computes readiness, a human approves. Never auto-graduate
- Submitter cannot approve (A24)
- Every transition writes an immutable evidence snapshot with the policy version (A25, A26)
- Overrides require a reason and are recorded

### S6.2 At-risk, dormant, de-graduation
**Acceptance**
- At-risk raised and cleared automatically per the trigger list
- Dormancy computed from the group's own cadence
- De-graduation is a normal transition, not an error state
- A group with an external linkage in `distressed` cannot show green on its readiness card

---

## Stage 7. Service linkage

### S7.1 Linkage lifecycle
**Acceptance**
- Full state machine: proposed, screened, blocked, pending approval, returned, approved, rejected, lapsed, active, distressed, defaulted, closed
- Gates evaluated at screening **and again at approval**
- `blocked` is a first-class state showing exactly what the subject needs to reach
- Approval chain per referral type

### S7.2 Provider directory
**Acceptance**
- A provider is only proposable in woredas where it operates
- RUSACCO is a first-class provider type, not "other"
- Blacklisting a provider flags open linkages for review and does not auto-close them, because the obligation still exists

### S7.3 Savings account linkage
**Acceptance**
- Available from Phase 2
- Activation switches the ledger to two balances, cash and bank
- Meeting close reconciles both
- A deposit lag between meeting collection and bank deposit is representable

### S7.4 Market offtake and service referral
**Acceptance**
- Delivery and payment events log against the linkage, so it is useful for M&E rather than a name in a field
- Service referral reuses the existing timeline UI unchanged

### S7.5 Linkage funnel reporting
**Acceptance**
- `mv_linkage_funnel` reports proposed through closed with block reasons (A32)
- Block reasons are the primary programme-learning output: they say which gate is stopping groups

---

## Stage 8. Structural linkage and CLA

### S8.1 Formation events
**Acceptance**
- Multi-group event stays open until every selected SHG has recorded two delegates
- A selected SHG that drops below threshold before approval is flagged at approval time
- Excluding a group requires an explicit action with a reason, visible on that group's record
- Events expire after 90 days
- Approval creates the CLA, opens structural memberships, activates delegates and moves each SHG to P3 under one shared event id

### S8.2 Structural membership and delegates
**Acceptance**
- A group belongs to at most one CLA (A21)
- A federation contains CLAs, never groups directly (A22)
- At most two active delegates per group per CLA (A23)
- Delegate rotation closes and reopens, never edits
- Withdrawal that drops a CLA below threshold flags it; it does not auto-dissolve

### S8.3 CLA readiness view
**Acceptance**
- Per kebele: eligible group count, threshold, and how many more are needed (A29)
- This screen drives facilitator behaviour more than any report. Make it prominent

---

## Stage 9. Credit and federation (post-pilot)

### S9.1 Credit facility
Six gates, four-level approval, obligation tracking, distress cascade to member SHGs. Group subjects blocked (A20).

### S9.2 Federation
Schema and minimal admin only. Cooperative registration is a `cooperative_registration` referral with its own lifecycle, not an attribute of the federation.

---

## Cross-cutting, every stage

| Item | Requirement |
|---|---|
| **Offline** | Everything a facilitator does in a kebele works offline. Approvals are online only |
| **Language** | Amharic, Afaan Oromo, Somali, Afar. Ge'ez script rendering tested |
| **Device floor** | Set a hard minimum, for example Android 8 and 2 GB RAM, and test on it |
| **Battery** | Measure the charge cost of a full meeting capture. Power was the top reason groups abandoned digitisation in a comparable pilot |
| **Audit** | Every financial and phase event carries actor, timestamp and, where a decision was made, a snapshot |
| **Telemetry** | Meeting capture time, sync failure rate, field-level error rate, offline duration. This is the pilot's evidence base for design iteration |
