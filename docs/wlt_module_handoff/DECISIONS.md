# Decision log

Decisions already taken. Each records what was chosen, what was rejected, and why. If you want to reverse one, the "consequences" row tells you what breaks.

---

## D1. The registry stays as is

**Decision.** `core.Person` remains the single identity. Women register individually through the existing registry, then join groups. The module creates no person table of its own.

**Rejected.** A `wlt.Member` table with its own identity. It would let the two sides disagree about who someone is, and there is no way to reconcile that later.

**Consequences.** WLT-specific attributes hang off `wlt.beneficiary_profile`, a one-to-one extension. Nothing WLT-specific goes on `core.Person`. Group membership is a join, not an identity.

---

## D2. Group formation is new functionality on top of the existing registry

**Decision.** A four-state formation flow: Mobilisation → Draft → Constituted → Active. A group becomes Active when its first savings meeting closes with a balanced till. Only then does the phase machine take over.

**Rejected.** Creating groups in an already-active state. It hides the drop-off between mobilisation and first savings, which is exactly what the pilot needs to measure.

**Consequences.** Abandoned drafts and refused community endorsements are recorded, not deleted. `wlt.mv_formation_attrition` reports them. A kebele that produced no groups is programme learning.

---

## D3. Linkage splits into structural and service

**Decision.** Two models with two lifecycles.

| | Structural | Service |
|---|---|---|
| Model | `wlt.structural_membership` | `referrals.referral` |
| Examples | SHG into CLA, CLA into federation | bank account, buyer agreement, credit facility, service referral |
| Cardinality | one parent at a time, exclusive | many, concurrent |
| Carries | governance, delegates, voting | obligations, money, contract terms |
| Created by | a multi-party formation event | a per-subject application |
| Ends by | withdrawal, dissolution, merge | closure, maturity, default, termination |

**Rejected.** One generic `Linkage` table covering both. The two share almost no fields, no lifecycle and no cardinality rule. A single table would be mostly nulls with a type column deciding which half applies.

**Consequences.** `structural_membership` has a partial unique index enforcing one open parent per child, and a check constraint enforcing the hierarchy (a federation contains CLAs, never groups directly). Assertions A21 and A22 cover both.

---

## D4. Service linkage rides the existing referral engine

**Decision.** Generalise `referrals.referral` so its subject can be a person, group, CLA or federation. Implement with **typed nullable FK columns plus an exactly-one check constraint**, and a generated `subject_type` column.

**Rejected: Django `GenericForeignKey`.** Three reasons:

1. The reporting layer runs on materialized views. A GFK cannot be joined in SQL without a contenttypes lookup per row, so every WLT reporting view would degrade or need hand-written unnesting.
2. A GFK gives no referential integrity. A deleted group leaves dangling referrals.
3. Typed columns index cleanly and read obviously in the SQL the team already maintains.

The cost is one column per subject type. With four types that is acceptable. If subject types were open-ended it would not be.

**Rejected: a parallel `wlt.linkage` table mirroring the referral shape.** It duplicates the lifecycle, the provider directory, the event model and the timeline UI, and the two copies will drift.

**Consequences.**
- One platform change to live code. See `django/MIGRATION_REFERRAL_SUBJECT.md`.
- The referral timeline component must resolve subject by type. Regression-test the youth path.
- Referral permissions now resolve through two scoping paths. This is the highest-risk item in the plan.
- A side benefit: `referral_type.allowed_subject_types` turns the GBV safeguarding rule into a database constraint. A protection referral permits `person` only and can never be created against a group. Assertions A18 and A19.

---

## D5. Enrolment is hybrid

**Decision.** Import the PSNP ELS caseload as the candidate pool. Facilitators may add women the extract missed, but those start at `verification_status = 'pending'` and cannot be assigned to a group until a woreda officer verifies them against PSNP records.

**Rejected: facilitator-only registration.** 5,000 hand-keyed registrations on phones in Afar, no eligibility verification, high duplicate risk.

**Rejected: import-only.** The extract will be incomplete and facilitators would have no legitimate path for a woman who is clearly eligible.

**Consequences.**
- An import pipeline with PSNP client ID matching and a fuzzy-match queue. **Never auto-merge on a fuzzy match**: merging two different women is worse than carrying a duplicate.
- Duplicate detection runs on group assignment, not only on import. The realistic failure is the same woman entering through both routes in the same week.
- The exception-route share is a reported metric per woreda (`wlt.mv_enrolment_vs_allocation.exception_route_pct`). Past 10%, the extract is the problem and should be fixed rather than worked around.

---

## D6. Thresholds are data, not code

**Decision.** Every threshold FSCO can change lives in `wlt.policy_parameter`, effective-dated and geography-scoped. Every phase and linkage decision records the policy version it was made under.

**Rationale.** The source handbook describes itself as a living document, and it already states group size three ways, the CLA threshold two ways and the federation threshold two ways. Values will move mid-pilot.

**Consequences.** No constants in gate logic. A phase decision made in March under an 80% attendance rule stays auditable in September when the rule is 75%.

---

## D7. Savings linkage opens at Phase 2, credit stays at Phase 4

**Decision.** A group savings account is available from Phase 2. External credit facilities are restricted to CLAs and federations at Phase 4, behind a four-level approval chain, and group-level credit is blocked outright in the pilot (`gate.credit.allow_group_subject = false`, assertion A20).

**Rationale.** The handbook treats "linkage" as one step. The two carry very different risk. A locked cash box in a pastoralist kebele is a worse custodian than a bank account. Early linkage of savings groups to microfinance is the clearest negative finding in the Ethiopian evidence base.

**Consequences.** Activating a savings account changes ledger behaviour: cash and bank become two balances and the meeting close must reconcile both. Build that into the ledger service before enabling the linkage, not after.

---

## D8. The pre-pilot tests Phases 1 to 3 only

**Decision.** Federation functionality is schema-only. No UI in the pilot build.

**Rationale.** Phase 4 requires 10 CLAs of 8 to 12 SHGs, so 80 to 120 groups inside one woreda. The largest regional allocation is Somali at 80 groups across the whole region. It is arithmetically unreachable.

**Consequences.** Stage 9 in the build sequence is post-pilot. Say this in the pilot documentation too, or the pilot will be judged against a milestone that was never achievable.
