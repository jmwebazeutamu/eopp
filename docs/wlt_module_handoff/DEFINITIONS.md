# Indicator definitions and glossary

**None of these formulas exist in the source handbook.** It names the indicators and leaves them undefined. These are the definitions the module implements. Do not invent your own, and do not let a reporting request quietly introduce a second version of any of them.

Everything here is implemented in `wlt/services/indicators.py` and surfaced through `wlt.mv_group_compliance` and `wlt.mv_group_financials`.

---

## 1. Formulas

### Meeting adherence
```
meetings held / meetings due, over the rolling window
```
"Due" comes from the group's own bylaw cadence in force at the time, not a global default. A weekly group and a monthly group are measured against their own schedules.

### Attendance rate
```
sum(present or late) / sum(roster size at each meeting), over the rolling window
```
The denominator uses the roster **as it stood on each meeting date**, via `wlt.roster_on(group_id, date)`. Not the roster today. A woman who joined in month 6 does not make months 1 to 5 look worse.

Open item for FSCO: does `absent_excused` count against her? Currently it does. The column exists so the rule can change without a migration.

**A value above 100% is a data-quality alarm**, not a rounding artefact. It means attendance was recorded for someone off the roster on that date. Investigate rather than clamp.

### Member savings compliance
```
meetings where she contributed >= the bylaw amount / meetings she was expected at
```
Bylaw amount is the version in force on that meeting date.

### Group savings compliance
```
share of members whose individual compliance >= 90%
```
Deliberately not a group mean. One strong saver can carry a mean while half the group has stopped contributing.

### Fund adequacy
```
total fund / (bylaw contribution x current roster), expressed in WEEKS OF CONTRIBUTION
```
Expressed as a duration rather than a birr amount so it stays comparable across regions and needs no re-indexing for inflation.

This **replaces** the handbook's Phase 2 target of "2 to 3 months' worth of total member contributions". That target sits below the natural accumulation floor: a weekly group of 20 at 50% compliance already holds about six months' worth by month 12. It screens nothing.

### Loan delinquent
```
any scheduled repayment >= 1 day past due
```

### Loan in default
```
any scheduled repayment >= 30 days past due
```
Standard microfinance convention. Parameter `loan.default_days_past_due`. **Needs FSCO confirmation.**

### PAR30
```
outstanding principal of loans with any payment > 30 days late
--------------------------------------------------------------
              total outstanding principal
```
Standard definition. Do not invent a local variant.

Current implementation uses `loan.due_on` as the reference date, correct for single-maturity loans. Once `wlt.loan_schedule` carries multiple instalments, switch to the earliest unpaid instalment's `due_on`. Tracked in `BACKLOG.md`.

### Loan cycle completed
```
every loan in a cycle_batch fully repaid, principal and service charge
```

### Dormant
```
no meeting recorded for (3 x bylaw cadence), floor 60 days
```
Weekly group: 60 days. Monthly group: 90 days.

### At risk
Any one of:
- attendance below 60%
- PAR30 above 20%
- two consecutive missed meetings
- no treasurer on record
- an external linkage in `distressed` or `defaulted`
- a meeting that failed to reconcile

At risk is an early warning, not a phase demotion. It is visible to the facilitator and does not by itself move the group backwards.

---

## 2. Phase gates

Every condition is a policy parameter. Values below are the seeded defaults in `003_policy_seed.sql`; several are marked NEEDS FSCO.

| Gate | Conditions, all required |
|---|---|
| **Forming → P1** | bylaws recorded; roster 15 to 25; chair, secretary and treasurer elected; first savings meeting closed with a balanced till |
| **P1 → P2** | meeting adherence >= 90%; attendance >= 80%; group savings compliance >= 80%; >= 10 savings meetings held; if any loans issued, PAR30 = 0 |
| **P2 → P3 eligible** | fund adequacy >= 12 weeks; >= 1 completed loan cycle; PAR30 = 0; social fund active; >= 52 weeks since P1 entry |
| **CLA formation** | >= 8 P2-eligible SHGs in one kebele; each elects 2 delegates; CLA constitution recorded |
| **P3 → P4** | >= 10 CLAs in the woreda; each CLA operating >= 12 months; federation constitution recorded |
| **Credit facility** | subject at P4; subject is a CLA or federation, never a group; aggregate PAR30 = 0 for 6 months; >= 2 completed cycles per member SHG; active savings account >= 12 months; facility <= 1.0 x own funds; provider active and operating in that woreda |

Gates are evaluated **twice**: at screening, and again at approval. A group can drift below threshold while an approval sits in a queue, and approving against stale numbers is how bad credit linkages happen.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **CLA** | Cluster Level Association. 8 or more mature SHGs in a kebele, each sending 2 elected delegates |
| **CF / DA** | Community Facilitator / Development Agent. Existing PSNP field staff, distinct from WLT facilitators |
| **ELS** | Enhanced Livelihoods Support. The PSNP 6 component WLT sits inside |
| **Federation** | Woreda-level body formed from multiple CLAs. May register as a cooperative |
| **FSCO** | Food Security Coordination Office. Government counterpart, and the approval authority in this module |
| **IGA** | Income Generating Activity |
| **PSNP** | Productive Safety Net Programme |
| **RUSACCO** | Rural Savings and Credit Cooperative. The incumbent rural financial structure in Ethiopia |
| **Service charge** | The handbook's term for loan interest, used for religious inclusivity. Per-group label, stored in `bylaw_version.service_charge_label` |
| **SHG** | Self Help Group. 15 to 25 women saving and lending together |
| **Social fund** | Referenced in the handbook's Phase 2 indicators and never defined. Open question Q9 |
| **WLT** | Women's Livelihoods Transformation. The initiative this module serves |
| **Woreda / kebele** | District / village. The two administrative levels below region |

---

## 4. Units and conventions

- Currency is **ETB**, stored as `numeric(14,2)`. Never float.
- Dates are dates, not timestamps, wherever they represent a field event.
- Distances and measures are metric.
- All timestamps are `timestamptz`. Store UTC, render in Africa/Addis_Ababa.
- Ethiopian calendar dates are **not** stored. If the UI needs them, convert at the presentation layer.
