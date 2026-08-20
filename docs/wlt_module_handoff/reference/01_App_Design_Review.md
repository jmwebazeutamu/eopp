# Design review: piloting the case management app on the WLT / SHG programme

**Source reviewed:** Temsalet Pilot Handbook Draft (PSNP 6, Women's Livelihoods Transformation, ELS component)
**Date:** 19 August 2026

> Note on scope: the platform spec files in this folder (`YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`, the technical specs, the dashboard handoff) are OneDrive cloud placeholders and could not be opened. This review works from the handbook and from the app's known shape (individual case management, referral stack, case manager dashboard, RBAC scoping, reporting views). Download those files locally for a clause-by-clause gap analysis.

---

## 1. The headline problem: the unit of work changes

The app was built around an individual beneficiary case: one person, one case file, referrals out to services, a case worker following a caseload. The WLT programme's unit of work is a **group**.

| App today (assumed) | What the handbook needs |
|---|---|
| Person = primary record | Group = primary record; person is a member of a group |
| Case worker → beneficiary | WLT facilitator → SHG → members |
| Referral events on a timeline | Recurring weekly meetings with a fixed agenda |
| Service uptake outcomes | Financial ledger balances, attendance rates, group maturity phase |
| Case closes | Group graduates through 4 phases into a CLA, then a federation |

This is not a configuration change. It needs a `Group` entity with membership over time, a meeting entity, and a financial ledger. Decide early whether you:

- **(a)** extend the existing data model with group objects, or
- **(b)** run WLT as a separate module sharing auth, geography, and reporting.

Option (b) is faster to pilot and less likely to destabilise the youth case management side. Option (a) is better if the long game is one platform for all PSNP livelihoods pathways.

**Also worth naming out loud:** the app is a *youth* employment case management platform. WLT beneficiaries are adult female PSNP livelihoods beneficiaries. If the pilot is a proving ground for the technology rather than the target population, say so in the pilot documentation, otherwise the M&E framing will not hold up.

---

## 2. The app becomes a financial system of record

Sections 3.4 and 3.5 plus the four annexes describe a full savings-and-credit ledger: cashbook, individual passbook, loan ledger, minute book. If the app digitises these, it stops being a case tracker and becomes money infrastructure. That raises the bar:

- **Immutability and audit trail.** Every entry needs who/when/what, and corrections must be reversals, not edits. Members sign the paper register. The digital equivalent needs an equally clear record.
- **Reconciliation.** Cash in the box must reconcile to the ledger at every meeting close. Build a meeting-close step that will not complete on an unbalanced till.
- **Paper stays primary at first.** Do not remove the physical registers in the pilot. Run digital in parallel, reconcile, and only then consider retiring paper. Groups that lost their one smartphone in Uganda's Akaboxi pilot abandoned the system entirely.
- **Service charge engine.** The handbook says 5–10% but does not define the basis (flat per loan, per month, declining balance). This must be a group-configurable parameter, not hardcoded, and it must be defined before build.
- **Terminology switch.** The handbook says groups may use "service charge" instead of "interest" for religious inclusivity, but the annex loan ledger columns say "Interest". Make the label a per-group setting and fix the annexes.

---

## 3. Offline is the requirement, not a feature

Afar and Somali were selected precisely because infrastructure and connectivity are weak. Evidence from savings group digitisation is consistent on this:

- Power was the single biggest reason groups abandoned digitisation in Uganda. All 15 pilot groups lacked reliable electricity.
- Rural groups average 1–2 smartphones per group.
- Dependence on one tech-confident, English-literate member creates a single point of failure. When that person left, groups stopped using the system.

Design implications:

1. **Offline-first with conflict-free sync.** A meeting must be recordable end to end with no signal, syncing later. Not "offline mode as a fallback".
2. **Low-end Android target.** Set a hard floor (for example Android 8, 2 GB RAM) and test on it.
3. **Battery budget.** A meeting session should cost a small, measured percentage of charge. Measure it.
4. **Language.** Amharic, Afaan Oromo, Somali, Afar. Right-to-left is not needed but Ge'ez script rendering and number formatting are. Voice or icon-led flows help members with low literacy. The handbook only asks that "at least one member" has basic digital literacy, which is a thin margin.
5. **Facilitator device, not member device.** In the pilot, the realistic model is the WLT facilitator carries the device and records for the group. Members verify against their paper passbook. Plan the member-facing app for later.

---

## 4. New actors and permissions

The handbook introduces a role that does not exist in the app: **WLT facilitator**. Explicitly "different from the existing community facilitators", mainly female, dedicated to SHGs.

Model needs:

- WLT facilitator (creates groups, records meetings, holds the cashbox key in early months)
- SHG office bearers: Chair, Secretary, Treasurer, **rotating** on a group-defined cycle. Role history matters for audit. Who was treasurer on the date of that disbursement?
- CLA representative (two elected per SHG, phase 3)
- Woreda and regional FSCO staff, read and approve
- Federal / World Bank, read-only aggregate

RBAC scoping should be geographic (region → woreda → kebele → group) and the existing scoping work in `review_kit/fixes/P1-2-rbac-scoping.md` is probably reusable. Facilitator caseload is undefined in the handbook. **Ask FSCO: how many SHGs per facilitator?** At 250 groups in the pre-pilot, this determines the facilitator recruitment number and the app's caseload UI.

---

## 5. Gaps and contradictions in the handbook the app cannot resolve for you

These need decisions before the data model is fixed.

| # | Issue | Where | Why it blocks build |
|---|---|---|---|
| 1 | Group size: "15–20" in Section 2, "15–25" in 3.4, target table calculates at 20 | S2, S3.4, table | Validation rules and target maths |
| 2 | Meeting frequency: "ideally weekly, at least monthly" (3.4) vs phase 1 indicator "meeting every month on schedule" | S3.4, S4 | Compliance calculation, reminders, overdue logic |
| 3 | Internal lending starts after "10 regular savings meetings", but phase 1 runs 0–6 months. At monthly meetings a group cannot reach 10 in phase 1 | S3.5, S4 | Gating logic conflicts |
| 4 | "DAs/CFs should closely support the first few loan cycles" but 3.2 says WLT facilitators are distinct from CFs | S3.5 vs S3.2 | Which role gets the permission? |
| 5 | CLA formation: "when 8 mature SHGs exist" vs indicator "minimum around 6" | S4 phase 3 | Threshold logic |
| 6 | Cashbox keys held by the facilitator | S3.4 step 6 | Contradicts member ownership and the handover principle in 3.2. It is also a safeguarding and fiduciary exposure. Recommend a two-member key or lock arrangement with the facilitator as witness only |
| 7 | No unique member identifier defined, no stated link to the PSNP client ID or the ELS grant record | throughout | Duplicate members, no eligibility verification, no way to join WLT data to PSNP MIS |
| 8 | Eligibility depends on prior ELS completion (life skills, financial literacy, microenterprise support, grant received) with no verification method | S2 | The app should check this at enrolment. Where does that data live? |
| 9 | Social fund mentioned in phase 2 indicators but never defined anywhere | S4 | Second ledger type with its own rules |
| 10 | "Temsalet" in the file name, "WLT" throughout the text | title | Pick one name before it ends up in the UI |
| 11 | Dire Dawa's pre-pilot allocation (292) equals its entire national target | table | Fine, but flag it: no expansion phase there |
| 12 | Loan approval by "consensus or majority" with no quorum rule | S3.5 | Approval workflow needs a quorum definition |

---

## 6. Graduation is a state machine, build it as one

Phases 1 to 4 with maturity indicators are a natural fit for an explicit state machine with automated eligibility flags:

- **Phase 1 → 2:** attendance ≥ 80%, bylaws recorded, all members saving regularly, first loans repaid correctly
- **Phase 2 → 3:** fund ≥ 2–3 months of total member contributions, one loan cycle with no default, social fund running
- **Phase 3 → 4:** CLAs operating 1–2 years, ≥ 10 CLAs of 8–12 SHGs

Let the app **compute** the flags and let a human **approve** the transition. Never auto-graduate. Facilitators will need to override, so record the override reason.

Two indicators are undefined and need a formula: "regular savings" (how many missed contributions break it?) and "without default" (how many days late is a default?).

---

## 7. Social empowerment data needs protection design

Section 3.6 puts GBV awareness, early marriage, and household decision-making on the meeting agenda, and 3.6 step 7 says key points go in the minutes book. This is the highest-risk data in the system.

- **Do not record identifiable disclosures.** Log topic, duration, and who facilitated. Nothing about individual cases.
- If any GBV referral pathway is added later, it needs a separate, restricted store with an explicit consent and safeguarding protocol. Do not put it in the group minutes.
- The handbook's own discussion norm is confidentiality. A synced digital minute book breaks that promise unless the field structure prevents it.

---

## 8. Dashboard and M&E implications

The handbook implies indicators the existing dashboard does not have. Likely additions to the reporting layer:

- Groups formed, active, dormant (define dormant: how many missed meetings?)
- Member attendance rate, savings compliance rate
- Total group savings, loans outstanding, portfolio at risk, repayment rate
- Loan purpose mix (IGA vs emergency vs household)
- Phase distribution across groups, time-in-phase
- Drop-out and replacement rate
- Facilitator activity: meetings attended, groups supported
- Regional slices matching the pre-pilot allocation (Somali 1,600 / Amhara 1,200 / Afar 1,000 / Central Ethiopia 908 / Dire Dawa 292)

Portfolio at risk and repayment rate need agreed definitions before the SQL is written. Borrow standard definitions rather than inventing them.

---

## 9. Pilot mechanics

- **The handbook says the pilot is "only partially designed" and is a living document.** Build for schema change. Version the bylaw parameters, group configuration, and form definitions so a mid-pilot rule change does not corrupt existing records.
- **Sequence the rollout.** Start with 2 regions, not 5. Amhara (highland, denser, easier) and Somali (hardest, pastoralist, mobile) give you the range without 250 groups going live at once.
- **Instrument the app for the research.** The handbook commits to "on-hand research to inform successes and course corrections". Add usage telemetry: meeting record completion time, sync failure rate, field-level error rate, offline duration. That is your evidence base for the design iteration.
- **Plan the exit cost.** Groups in other digitisation pilots hit unexpected user fees after project close. Decide now who pays for data, devices, and hosting after the pilot.

---

## 10. What I would decide first

1. Separate WLT module or extend the youth case model. (Recommend: separate module, shared platform services.)
2. Group as first-class entity, with membership history.
3. Paper-primary, digital-parallel for the pilot. No paperless claim.
4. Offline-first, facilitator-device, low-end Android.
5. Get FSCO to close the 12 open items in section 5 above before the schema is frozen.
6. Two regions first, then expand.

---

## Sources

- [Our Digital Journey with Savings Groups: what we got wrong, DSG Hub](https://dsghub.org/our-digital-journey-with-savings-groups-what-we-got-wrong-and-the-lessons-weve-learned-along-the-way/)
- [Learning from a savings group digitisation pilot in Uganda, Response Innovation Lab](https://www.responseinnovationlab.com/updates/learning-from-a-savings-group-digitisation-pilot-in-uganda)
- [World Bank Productive Safety Net Project 6 (P511478) project documents](https://documents1.worldbank.org/curated/en/099111425070037792/pdf/P511478-ba2ad2f0-3dbb-4993-b589-00b84ca54059.pdf)
- [Ethiopia: A New Phase of Support for Safety Nets, World Bank](https://www.worldbank.org/en/news/press-release/2026/03/03/ethiopia-a-new-phase-of-support-for-safety-nets-will-foster-resilience-and-create-pathways-to-decent-jobs)
