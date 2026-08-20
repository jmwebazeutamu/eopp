# Open questions

Ten items with FSCO. Three block the schema and should be answered before stage 1 starts. The rest can be answered while earlier stages are built, but each has a "needed by" stage.

Where a question has a seeded placeholder in `003_policy_seed.sql`, the note says `NEEDS FSCO`. Placeholders are the conservative reading of the handbook, not an agreed position.

---

| # | Question | Blocks | Needed by | Current placeholder |
|---|---|---|---|---|
| **Q1** | **Share-out or accumulate?** Does an SHG distribute its fund at the end of a cycle (VSLA style) or accumulate permanently (Kindernothilfe SHG style)? | **Ledger schema** | Stage 3 | Accumulating, by implication |
| **Q2** | Can the core referral model take a polymorphic subject without destabilising the youth side? | **Stage 0 approach** | Stage 0 | Assumed yes |
| **Q3** | Does the core platform already have an offline sync layer? | **Critical path** | Stage 0 | Assumed no. If no, this is platform work, not module work |
| **Q4** | Service charge basis: flat per loan, per month, or declining balance? | Loan engine | Stage 5 | `flat_per_loan`, nullable so it cannot be silently defaulted |
| **Q5** | Default definition: how many days past due? | PAR30, all credit gates | Stage 5 | 30 days |
| **Q6** | CLA threshold: 6, 8, or 8 to 10? The handbook says 8 in the text and "around 6" in the indicator. The Kindernothilfe source says 8 to 10 | CLA formation | Stage 8 | 8 |
| **Q7** | Federation threshold: "5 to 10 CLAs" (text) or "at least 10" (indicator)? | Federation | Post-pilot | 10 |
| **Q8** | Group size: 15 to 20 (S2), 15 to 25 (S3.4), or 20 (target table)? | Roster validation | Stage 2 | Hard 15 to 25, soft warn 18 to 22 |
| **Q9** | What is the **social fund**? It appears in the Phase 2 indicators and is defined nowhere | P2 gate | Stage 6 | Modelled as a ledger entry type with no rules |
| **Q10** | Does SHG membership relate to PSNP household graduation status? Can a woman hold a WLT membership and an active youth employment case at the same time? | Candidate pool query, permissions | Stage 1 | Assumed independent |

---

## The three that block schema

### Q1. Share-out or accumulate

The largest unstated design decision in the source handbook. It changes:

- Does the fund ever reset, or grow indefinitely?
- Is the ledger continuous or cyclical?
- What does "graduation" mean financially?
- Member incentive to stay for a second year

The handbook follows the accumulating model without saying so. Many PSNP women have prior VSLA exposure and will **expect a share-out**. If they save for two years with no distribution and no explanation, drop-out arrives in year two, exactly when the indicators say the group is maturing.

If the answer is share-out, `wlt.ledger_entry` needs a cycle dimension and a share-out calculation, and `fund adequacy` has to be measured within a cycle rather than cumulatively.

### Q3. Offline sync

Afar and Somali were selected for weak infrastructure. A meeting must record end to end with no signal. If the core has no sync layer, building one is platform work on the critical path and the estimate changes materially. This is not a module-level concern that can be deferred.

### Q4. Service charge basis

`bylaw_version.service_charge_basis` is deliberately **nullable with no default**, so the system cannot silently pick one. A flat 5% per loan and 5% per month on a 3-month loan differ by a factor of three. Getting this wrong misstates every group's fund position.

---

## Questions this package raises rather than answers

These are not FSCO decisions; they are things to confirm against the real codebase before build.

1. What exactly does `core.Person` look like today? `000_core_stubs.sql` is a guess. Confirm column names and types.
2. Does the geography hierarchy already model region / zone / woreda / kebele, and are the five pilot regions already seeded?
3. Is there an existing provider or service directory the referral engine uses, or does `referrals.provider` need creating?
4. How does the current RBAC express scope? The module assumes geographic scoping already exists per `review_kit/fixes/P1-2-rbac-scoping.md`.
5. Is `PSNP client ID` actually available to this platform, and through what channel? Without it there is no eligibility verification and no reconciliation with the PSNP MIS.
6. What is the existing materialized view refresh orchestration, and where do WLT views hook into it?
