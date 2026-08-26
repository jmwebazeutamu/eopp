# Handoff: WLT dashboards and reporting

Dashboard specification for the `wlt` module (Women's Livelihoods Transformation), Ethiopia PSNP 6 Enhanced Livelihoods Support.

Companion to `wlt_module_handoff/`, which owns the schema, the indicator definitions and the eight reporting views. This document owns the cards that read them.

**Status:** specification. No dashboard code written. Section 3 lists six defects in the existing reporting layer that have to be fixed before any card is built, because four of them make a card report something false.

---

## Paste this to a coding agent

> Build the WLT dashboards per `dashboard_handoff_wlt/README.md`. Read `wlt_module_handoff/DEFINITIONS.md` first: every formula is defined there and none of them may be recomputed inline in a card. Start with section 3 of this file, the reporting-layer fixes, and do not build a card on a view listed there until its fix is merged. Then build Tier 1 in Django per section 4. Tiers 2 to 4 are Metabase and come after. Card IDs (FC-, WO-, PG-, ME-) are the ticket vocabulary; quote them.

---

## What is in this bundle

```
dashboard_handoff_wlt/
├── README.md                                  this file: the spec
└── prototype/
    └── WLT_Dashboard_Prototype_v1.html        clickable, 5 tabs, illustrative data
```

Three companion documents sit outside this folder and are authoritative for what they cover:

| File | Authoritative for |
|---|---|
| `../wlt_module_handoff/DEFINITIONS.md` | Every indicator formula, every phase gate, the glossary |
| `../wlt_module_handoff/sql/004_reporting_views.sql` | The eight materialised views these cards read |
| `../design_handoff_youth_employment/README.md` | Design tokens, type, status colours. Do not invent a colour |

The youth bundle `../dashboard_handoff_youth_employment/` is the pattern this follows. Where a rule there already works, it is reused by reference rather than restated.

---

## 1. The organising decision: four dashboards

Same call as the youth side. Four small dashboards, not one with role-based hiding.

| Tier | User | Question answered | Refresh | Lives in |
|---|---|---|---|---|
| **1 Operational** | WLT facilitator | What do I record, and which group is slipping? | Live, plus last-sync stamp | **Django** |
| **2 Tactical** | Woreda FSCO officer | What is in my approval queue, and who needs coaching? | Daily 05:30 EAT | Metabase + 07:00 email |
| **3 Analytical** | Regional / programme manager | Where is the model breaking, and where is the money? | Nightly 02:00 EAT | Metabase, two tabs |
| **4 Strategic** | M&E and World Bank | Are we hitting targets, and what is still uncertain? | **Monthly, frozen** | Metabase, PDF |

Six cards per dashboard, hard cap nine. Tier 3 runs to ten across two tabs.

**What must not appear on each tier**

- **Tier 1.** No cross-group comparison, no regional aggregates, no trend line. Anything that cannot be tapped to produce a named list of groups, meetings or members gets deleted.
- **Tier 2.** No donor indicators. No facilitator leaderboard ranked by rate.
- **Tier 3.** No member names, no ledger detail, no live counts. Explicitly as-of dated.
- **Tier 4.** No operational noise. No indicator that needs more than one sentence to define. The smallest dashboard in the set.

---

## 2. What changes from the youth bundle

Five differences, each with a reason. Everything else carries over unchanged.

### 2.1 Tier 1 shows percentages. The youth tier 1 does not.

The youth rule bans percentages from the case manager screen because they invite comparison between staff on unstable denominators. The WLT readiness card is the opposite case: it shows one group its own attendance against a threshold that group's own bylaws set. `README.md` §8 of the module spec is explicit that the actual value beside the threshold is most of the module's value, and that a red dot changes nothing.

So: a percentage is allowed on Tier 1 **only** where the denominator is that group's own roster or meeting count and the threshold is rendered next to it. Never for comparison against another group.

### 2.2 The subject is a group, so suppression bands apply to group counts

250 groups across five regions. Dire Dawa is allocated 15. Any regional rate on Tier 3 or 4 has a denominator between 15 and 80, which sits in or near the provisional band the youth bundle sets at 30.

Consequence, stated plainly rather than discovered later: **Dire Dawa is permanently provisional for the pre-pilot and is never ranked.** Afar at 50 and Central Ethiopia at 45 are reportable but never league-tabled. Do not solve this by dropping the bands.

### 2.3 Maturation is about phase age, not checkpoint age

The P2 gate requires 52 weeks since P1 entry. In pilot month 6, zero groups can pass it. A "share of groups reaching P2" figure computed against all activated groups reports near-zero, and someone reads that as the model failing.

Every phase-attainment denominator filters to groups **old enough to have passed the gate**. Groups younger than the gate window render as `not yet eligible (n=...)`, never as a failure and never as zero. This is the single most likely way to publish a false negative about the pilot.

### 2.4 Money raises the bar

The youth platform reports counts. This module is a savings and credit ledger. Two rules follow:

- Any card counting ledger entries **nets reversals**. Corrections are reversals referencing the original, never edits (module `README.md` §5.3). A card summing `amount_etb` without handling `reverses_id` shows a corrected error twice.
- **Fund adequacy stays in weeks of contribution.** Converting it back to a birr target reintroduces the inflation and cross-region comparability problem the definition was written to remove.

### 2.5 Confidentiality becomes a card-level exclusion

`protection_referral` is person-only by database constraint. That constraint stops a GBV disclosure landing on a group record; it does not stop a linkage card aggregating protection referrals into a view a facilitator can drill into.

Every linkage card on Tiers 2 and 3 filters `type_code <> 'protection_referral'` in SQL, not in the card. Protection volume is reported separately, count only, to a protection-scoped audience.

---

## 3. Six defects in the current reporting layer

Found by reading `sql/004_reporting_views.sql` against `DEFINITIONS.md`. Four change a number. Fix before building the cards that read them.

| ID | View | Defect | Effect |
|---|---|---|---|
| **R-1** | `mv_enrolment_vs_allocation` | The geography join is `keb.id = reg.id OR keb.parent_id = reg.id`, which reaches one level below region. The seeded hierarchy is region → woreda → kebele, so a group anchored at kebele never joins to its region. | **Every region reports zero members enrolled.** Assertion A31 only checks `target_members`, which comes from the allocation table, so the suite passes. Feeds ME-2 and PG-2. Fix with a recursive ancestry walk or a materialised `geography_path`. |
| **R-2** | `mv_group_compliance` | `savings_compliance_pct` computes contributions made ÷ contributions expected. `DEFINITIONS.md` defines group savings compliance as the share of members whose individual compliance is at least 90%, and says in the same paragraph that it is deliberately not a group mean. | **The view implements the mean the definition warns against.** One strong saver carries a group where half the members have stopped. This column is read by the P1 → P2 gate. |
| **R-3** | `mv_group_compliance` | The savings numerator counts any entry with `amount_etb > 0`. The definition requires a contribution at or above the bylaw amount in force on that meeting date. | A member paying 5 birr against a 50 birr bylaw counts as fully compliant. Compounds R-2. |
| **R-4** | `mv_group_compliance` | **Meeting adherence is absent.** `DEFINITIONS.md` says it is surfaced through this view; the view has `attendance_pct`, `savings_compliance_pct`, `meetings_held_total` and `last_meeting_on`, and no adherence column. | The P1 → P2 gate names meeting adherence ≥ 90% as a condition and there is nothing to read it from. Needs the bylaw cadence in force at each point to compute meetings due. |
| **R-5** | `mv_group_financials` | `fund_etb` ignores `write_off` and `adjustment` entry types, and treats reversal rows as ordinary entries. | A written-off loan leaves the fund overstated by the principal. Fund adequacy in weeks then overstates the same way, and it is a P2 gate condition. Also blocks W4: with `bank_deposit` and `bank_withdrawal` both excluded, the view cannot split cash from bank. |
| **R-6** | `mv_cohort_survival` | `still_active` counts `status = 'active'` only; `at_risk` falls into `faltering`. `DEFINITIONS.md` says at-risk is an early warning that does not by itself move a group backwards. | Survival is understated by the whole at-risk population. Also grouped by `kebele_id`, giving cells of one or two groups; add region for anything reportable. |

Two smaller items, no number changes:

- `mv_cla_readiness` counts groups **at** P2 or above. The CLA gate in `DEFINITIONS.md` says P2-**eligible**. A group meeting every P2 condition but awaiting woreda approval is eligible and is not counted.
- `mv_group_financials` PAR30 uses `loan.due_on`, correct only for single-maturity loans. Already tracked in `BACKLOG.md`; PG-4 carries the caveat on the card until `loan_schedule` is populated.

**Write an assertion per row above into `900_test_seed_and_assertions.sql`.** The current suite has 32 assertions and none of them would have caught R-1.

---

## 4. Tier 1: Facilitator

Django, inside the WLT app. Not Metabase, for the same three reasons the youth case manager screen is not: it shows named women, it must render in one request under 100 KB, and every element links to work.

One extra reason here. **It has to work from the last sync.** Afar and Somali were chosen for weak infrastructure. Every card renders from local data with a visible sync stamp, and a card that cannot render offline does not belong on this tier.

Six queue cards on the facilitator home screen, two components on the group detail screen.

| ID | Card | Source | Shape | Rules |
|---|---|---|---|---|
| **FC-1** | Meetings to record | `wlt.meeting` where `status = 'open'` or scheduled and absent, against the bylaw cadence | List, sorted by days overdue | The default landing card. Group name, scheduled date, days late, one tap to the capture flow. Show queued-not-synced meetings here too, marked, so the facilitator does not record one twice. |
| **FC-2** | Tills that did not balance | `mv_meeting_reconciliation` (new, §8) | List with the discrepancy in **birr** | Never "reconciliation failed". Name the amount and the direction: `Short 340 ETB` / `Over 120 ETB`. A failed reconciliation raises an at-risk flag, so this card and FC-4 must agree. |
| **FC-3** | Repayments overdue | `mv_loan_arrears` (new, §8) | Two labelled groups, delinquent then default | **Delinquent (≥ 1 day) and default (≥ 30 days) are separate blocks, never one "overdue" count.** One is a conversation at the next meeting, the other is a PAR30 event that blocks a gate. Member name, amount, days past due. |
| **FC-4** | Groups at risk | `wlt.risk_flag` open rows via `mv_risk_register` (new, §8) | List, one row per flag, oldest first | Render the reason in words with the actual value: `Attendance 54% (floor 60%)`, `No treasurer since 12 May`. Six reason codes exist; do not collapse them into a count. At risk is a warning, not a demotion, so never style it as failure. |
| **FC-5** | Formation clock | `mv_formation_clock` (new, §8) | List with days remaining | Drafts expire at 60 days, constitutions that never held a savings meeting at 30. Both are silent deaths. Show days remaining, not the expiry date, and turn the row gold under 14 days. |
| **FC-6** | Sync and conflicts | `mv_sync_health` (new, §8) | Count strip plus a conflict list | Queued / syncing / failed, per the design system's offline strip. Below it, duplicate `(group_id, held_on)` pairs from two devices, awaiting resolution. **Never auto-merge financial records.** |
| **FC-7** | Group readiness card | `mv_gate_block_reasons` (new, §8) | Condition rows on the **group detail** screen | The single most behaviour-changing screen in the module. One row per gate condition: name, **actual, threshold, met**. Blocked is a first-class state, not an error. Recomputes on meeting close, so the row moves the moment work is recorded. Offline it renders from last sync and carries the stamp. |
| **FC-8** | Member passbook strip | `wlt.ledger_entry` per member, roster-on-date | Table on the **group detail** screen | Per member: meetings attended ÷ expected, contributions made ÷ expected, current loan and days past due. Sorted by compliance ascending, so the women who need a conversation are at the top. Denominators visible on every row. |

### 4.1 Acceptance criteria for Tier 1

1. Home screen renders in one request, under 100 KB, with no network beyond the page itself.
2. Every count on the screen is tappable and produces the named list behind it.
3. A facilitator scoped to kebele A sees no group in kebele B, tested in both directions.
4. **A facilitator who can see a group roster cannot reach those women's youth-side case records.** Tested explicitly, both directions, per module `README.md` §9.
5. FC-7 renders from cached data with an airplane-mode toggle on, and shows the sync time.
6. Closing a meeting moves the relevant FC-7 rows without a page reload.
7. No percentage anywhere on the tier without its denominator or its threshold beside it.

---

## 5. Tier 2: Woreda FSCO officer

Delivered as an **07:00 server-rendered email**, with the Metabase dashboard as the drill-down. On 3G a rendered snapshot in the inbox beats a dashboard that takes twelve seconds to paint.

| ID | Card | Source | Shape | Rules |
|---|---|---|---|---|
| **WO-1** | Approval queue by age | `wlt.phase_event` submitted-not-decided, `referrals.referral` in `pending_approval`, `beneficiary_profile` pending verification, `validation_override` unreviewed | Four labelled counts, each with the oldest item's age | This is the officer's job, so it is card one. **Age, not just count.** A phase transition sitting 18 days is the finding. Gates are evaluated again at approval, so the queue view must show the value as of now, not as of submission. |
| **WO-2** | Groups by phase | `mv_groups_by_phase` | 100% stacked row per kebele, **four segments** | Forming / P1 / P2 / P3+. Phase is ordered, so use the **sequential** ramp, not four categorical hues (§9). Direct-label every segment. Carry the group count on the row. |
| **WO-3** | Facilitator load and data currency | `mv_sync_health`, group counts per facilitator | Sorted rows, **counts only** | Groups carried, meetings recorded on time ÷ meetings due, days since last sync. **Never a rate ranking.** At 5 to 10 groups per facilitator a rate is noise and creates pressure to stop recording bad news. Carry the denominator on the row. |
| **WO-4** | At-risk register | `mv_risk_register` (new) | Table, oldest flag first | Group, reason in words, actual vs threshold, days open. A flag open 40 days is a supervision failure, not a group failure. |
| **WO-5** | What is blocking P2 | `mv_gate_block_reasons` (new) | Row chart, one row per gate condition | The coaching card. `Meeting adherence: 14 groups short`, `Fund adequacy: 9 groups short`. A group appears under every condition it fails, so **state that the rows do not sum to a group count**. This is also the evidence for revising a threshold rather than guessing at it. |
| **WO-6** | Overrides recorded | `mv_override_register` (new) | Table by rule, then by actor | Module `README.md` §4.3: overrides are reviewed at woreda level and they tell you which validation rules are wrong for the field. A rule overridden 30 times is a rule to change, not 30 facilitators to correct. |
| **WO-7** | CLA readiness | `mv_cla_readiness` | Per kebele: eligible, threshold, short by | **Not instrumented until stage 8.** Until then render the words `not yet instrumented`, never a zero. Fix the P2-eligible definition first (§3). |

Six cards plus WO-7 when stage 8 lands. If that pushes past the cap, WO-6 moves to a monthly review rather than the daily dashboard.

---

## 6. Tier 3: Programme manager

Ten cards, two tabs. As-of dated, no names, no live counts.

### Tab 1: Formation and money

| ID | Card | Source | Shape | Rules |
|---|---|---|---|---|
| **PG-1** | Formation attrition | `mv_formation_attrition` | **Row chart, shared left baseline** | Mobilisations → endorsed → drafts opened → constituted → activated. Annotate the loss at every transition. **Not a funnel chart** (§9). Refused endorsements and abandoned drafts are the finding: a kebele with three abandoned constitutions has a mobilisation problem, and a report of successes alone cannot show it. |
| **PG-2** | Enrolment vs allocation | `mv_enrolment_vs_allocation` | One axis, two series, both counts, direct-labelled | **Blocked on R-1.** Carry the exception-route share beside each region; the alert threshold is 10% and lives in `enrolment.exception_route_alert_pct`. An exception route becoming the main route is a control failure. Warn at 90% of the ceiling. |
| **PG-3** | Fund adequacy distribution | `mv_group_financials` | Binned histogram, weeks of contribution, one series per region as small multiples | **Never a mean fund.** Bin at the gate: under 12 weeks, 12 to 26, 26 to 52, 52+. The count under 12 is the number of groups the P2 gate is currently holding. Blocked on R-5. |
| **PG-4** | Portfolio quality | `mv_group_financials`, `mv_loan_arrears` (new) | **League table sorted by outstanding birr**, never by PAR | Region, groups lending, loans outstanding, birr outstanding, birr at risk, PAR30. Ranking regions by PAR at these denominators sorts by luck and is politically irreversible once published. Carry the single-maturity caveat on the card until `loan_schedule` is populated. |
| **PG-5** | Savings compliance distribution | `mv_group_compliance` | Binned, share of groups per compliance band | **Blocked on R-2 and R-3.** Until those land this card reports a mean and must not ship. Bands at the 80% gate. |

### Tab 2: Survival and linkage

| ID | Card | Source | Shape | Rules |
|---|---|---|---|---|
| **PG-6** | Cohort survival | `mv_cohort_survival` | Cohort heatmap, months since activation across, cohort down | The card that says if the model works in Afar the way it works in Amhara, and the most important output the pilot produces. **Censoring is the mechanic:** a cohort activated three months ago has no month-6 cell. Render it hatched with the date it matures, never 0%, never blank. Blocked on R-6, and needs region added to the view. |
| **PG-7** | Linkage funnel and block reasons | `mv_linkage_funnel` | Row chart by stage, plus a **separate block-reason table** | Proposed → screened → blocked → pending → approved → active, then distressed / defaulted / closed. Split by `type_code`. **Not a Sankey** (§9). Block reasons carry the programme learning: they say which gate is stopping subjects. **Excludes `protection_referral`** (§2.5). |
| **PG-8** | Phase progression time | `mv_phase_progression` (new) | Row chart of **median weeks** P1 → P2, n beneath each | Median, never mean. Show n per region. Apply the maturation guard (§2.3): groups still inside the 52-week window are excluded from the denominator and counted separately as `not yet eligible`. |
| **PG-9** | Dormancy and exits | `mv_cohort_survival`, `wlt.group` status | Small multiples by region | Dormant, at risk, split, merged, dissolved. Dormancy is defined as three times the bylaw cadence with a 60-day floor, so a weekly and a monthly group reach it at different times: **never render a single dormancy rate across cadences without saying so.** |
| **PG-10** | Data health | `mv_meeting_reconciliation` (new), `mv_sync_health` (new), view refresh timestamps | Table, worst woreda named, with a consequence column | Reconciliation failures, meetings recorded more than seven days late, groups with no bylaw version, groups with no treasurer on record, attendance above 100%. **Carry a consequence column** saying what each gap costs. A dashboard that does not say how stale it is invites the reader to assume it is live. |

---

## 7. Tier 4: M&E and World Bank

Five cards, frozen monthly, delivered as PDF and email. Smallest dashboard in the set.

| ID | Card | Source | Rules |
|---|---|---|---|
| **ME-1** | Results framework | `wlt.*` views joined to an indicator target table | **Indicator wording verbatim from the PSNP 6 ELS results framework.** That framework is not in this bundle; see OQ-4. Do not paraphrase and do not invent an indicator, or woreda figures will not roll up without reconciliation. As-of date in the card title. |
| **ME-2** | Women reached vs allocation | `mv_enrolment_vs_allocation` | Cumulative, by region, against the 5,000 ceiling. **One axis, two series, both counts.** Never a dual axis, never a gauge. Blocked on R-1. |
| **ME-3** | Group maturity | `mv_groups_by_phase`, `mv_cohort_survival` | Phase distribution with the **maturation guard visible**: `P2 attained: 31 of 88 groups eligible; 162 groups not yet eligible`. Publishing 31 of 250 is the false negative described in §2.3. |
| **ME-4** | Savings and portfolio | `mv_group_financials` | Total fund in ETB, fund per member, groups lending, PAR30. **Label the fund as member savings, not programme disbursement.** Show it as a stock and name the share-out question (OQ-1): if FSCO decides on share-out, part of this figure is a pending distribution, not an accumulated asset. Denominators on every row. |
| **ME-5** | What changed, and what is uncertain | Hand-written text card | One sentence beats another chart. Must name, every month: the share-out decision status; the share of meetings reconciled against paper; and which phase thresholds are still marked NEEDS FSCO, because attainment against a provisional threshold is a provisional number. |

---

## 8. New SQL required

Eight new objects. All go in a `006_dashboard_views.sql` beside the existing files, none of them modify the eight views except through the §3 fixes.

| Object | Feeds | Contents |
|---|---|---|
| `mv_gate_block_reasons` | FC-7, WO-5 | One row per (subject, gate condition): `code`, `threshold`, `actual`, `met`, `policy_version_id`, `computed_at`. The same shape the gate service returns, materialised nightly and recomputed on write for the facilitator card. Thresholds resolve through `policy_parameter`, never constants. |
| `mv_meeting_reconciliation` | FC-2, PG-10 | Closed meetings where `counted_cash_etb <> closing_cash_etb`, with the **signed birr discrepancy**; plus meetings open past `scheduled_for`. |
| `mv_loan_arrears` | FC-3, PG-4 | Per loan: outstanding principal, days past due, class (`current` / `delinquent` / `default`) from `loan.delinquent_days_past_due` and `loan.default_days_past_due`. Switch the reference date from `loan.due_on` to the earliest unpaid `loan_schedule.due_on` when that table is populated. |
| `mv_risk_register` | FC-4, WO-4 | Open `risk_flag` rows joined to the value that raised them, from `detail` jsonb, with days open. |
| `mv_formation_clock` | FC-5 | Drafts and constituted groups with days remaining against `formation.draft_expiry_days` and `formation.constituted_expiry_days`. |
| `mv_sync_health` | FC-6, WO-3, PG-10 | Meetings by `device_id`: unsynced count, last `synced_at`; plus duplicate `(group_id, held_on)` pairs recorded from two devices. |
| `mv_phase_progression` | PG-8 | Weeks between consecutive `phase_event` rows, median by region and by phase pair, with n, and a separate `not_yet_eligible` count. |
| `mv_override_register` | WO-6 | `validation_override` by rule code, actor and kebele, with the reason text. |

Wire all eight into `wlt.refresh_reporting()`. `mv_gate_block_reasons` and `mv_risk_register` are read by the facilitator UI, so they refresh `CONCURRENTLY` and need unique indexes.

---

## 9. Visualisation decisions, and what was rejected

The youth bundle's table applies in full. These are the additions the group domain needs.

| Data shape | Chosen | Rejected | Why |
|---|---|---|---|
| Phase distribution | 100% stacked, four segments, **sequential ramp** | Four categorical hues; pie; donut | Phase is ordered, P1 through P4. Categorical hues say the categories are unrelated, which invites reading P3 as a different kind of thing rather than a later one. |
| Gate readiness | Condition rows carrying **actual, threshold, met** | Traffic-light dot; radial gauge; a single readiness score | `Attendance 74% (need 80%)` changes what the facilitator does next week. A red dot does not, and a composite score hides which condition is short. |
| Fund position across groups | Binned histogram, bins set at the gate | Mean fund per group; total fund only | A mean is carried by the largest group. The count under the 12-week gate is the number the programme can act on. |
| Cohort survival | Heatmap, hatched censored cells | Survival curve; a single "% still active" | The heatmap separates decay with tenure, read across, from cohort-over-cohort improvement, read down. One curve conflates them. |
| Regional comparison, n = 5 | Five bars, or small multiples | Choropleth map | Area is a confound: Somali would dominate visually regardless of its data. At n = 5 there is no spatial pattern to find, and a map is the most expensive card on the page. |
| Approval backlog | Counts with the **oldest item's age** | Average days in queue | An average of 4 days hides one transition sitting 40. The old item is the finding. |
| Delinquency | Two labelled blocks, ≥ 1 day and ≥ 30 days | A single "overdue" count; a PAR gauge | The two carry different consequences: a conversation, or a blocked gate. |
| Attendance over 100% | A **data-quality flag** naming the meeting | Clamping to 100%; rounding | It means attendance was recorded for someone off the roster that day. Clamping hides a real record error. |

Banned outright, as on the youth side: 3D charts, rainbow palettes, more than four categorical hues, truncated bar axes, a number on every point, colour as the only encoding, dashed gridlines. Plus one more here: **no chart that renders a phase as a size**. A P4 group is not four times a P1 group.

---

## 10. Cross-cutting rules

The youth bundle's §8 applies in full: suppression bands at 30 and 10, no percentage without its denominator, whole percentage points, zero distinguished from no data, never rank by rate, every chart has a table twin, no colour alone, no shadows or light-grey secondary text for sunlight readability. These are the WLT-specific additions.

1. **Every compliance denominator uses `wlt.roster_on()`.** A card or question that recomputes attendance against today's roster is a review-blocking defect. A woman who joined in month 6 must not make months 1 to 5 look worse.
2. **No formula lives in a card.** Every one is in `DEFINITIONS.md` and implemented once. A Metabase question computing a percentage inline is a defect, same rule as the youth side.
3. **Thresholds render from `policy_parameter`, never typed into a card.** Otherwise the card and the gate that blocks the group will eventually disagree, and the facilitator will believe the card.
4. **Ledger cards net reversals.** Assert it: post an entry, reverse it, check the fund is unchanged.
5. **Maturation guard on every phase-attainment denominator** (§2.3). Groups inside the gate window are `not yet eligible`, counted separately.
6. **Fund adequacy stays in weeks.** Do not restate it in birr as a target.
7. **`protection_referral` never appears on a group-subject card** (§2.5).
8. **Freshness is on the page.** Tier 1 carries the device sync stamp. Tiers 2 to 4 carry the view refresh time. A dashboard that does not say how stale it is invites the reader to assume it is live.
9. **Colour follows the youth design system.** Series palette for charts (`#12836B` `#D08A0A` `#B0442A` `#7A4CA8`; sequential `#84BEAC` → `#0C5346`), reserved status palette for state. A status colour used as a series is a defect, and so is a series colour meaning failed. At risk is a warning, so it uses gold and never red.
10. **Language.** Amharic, Afaan Oromo, Somali and Afar. Confirm the BI tool renders Ge'ez in card titles, axis labels and PDF exports **before** committing to it, not after. Carried from the youth bundle's OQ-10, still unverified, and it now also covers Somali and Afar.

---

## 11. Open questions

| ID | Question | Working default |
|---|---|---|
| **OQ-1** | Share-out or accumulate (module Q1)? It decides if ME-4's fund figure is an accumulated asset or partly a pending distribution, and if fund adequacy is measured cumulatively or within a cycle. | Accumulating. ME-4 carries the caveat in text until FSCO answers. |
| **OQ-2** | How many groups does one facilitator carry? It sets the shape of FC-1 and WO-3. At 5 groups these are lists; at 30 they need filters and paging. | Assumed 5 to 10. Confirm with the pre-pilot staffing plan. |
| **OQ-3** | Does the woreda officer want the 07:00 email, or does the daily rhythm differ from the youth side? | Email subscription, same as WS. Confirm in the FSCO walkthrough. |
| **OQ-4** | What is the exact indicator wording in the PSNP 6 ELS results framework for WLT? ME-1 must quote it verbatim and this bundle has not seen it. | ME-1 blocked. Do not build it from the handbook's phrasing. |
| **OQ-5** | Are the suppression bands 30 and 10 accepted here, given that three of five regions sit near or below 30 groups? | 30 and 10, inherited. Consequence in §2.2 stated on the card. |
| **OQ-6** | Does at-risk count as surviving in cohort survival (drives R-6)? | Yes, per `DEFINITIONS.md`. Confirm with M&E before publication. |
| **OQ-7** | Who sees ME-4's fund figure at kebele level? A published group fund total in a small kebele identifies a specific cash box. | Region is the lowest published level for money. Woreda and below stay inside the platform. |

OQ-7 has a security dimension, not only a statistical one. Raise it with the task team before any tier 4 output leaves the platform.

---

## 12. Build sequence

| # | Step | Verified by |
|---|---|---|
| 1 | Fix R-1 to R-6, add one assertion per fix | `run_tests.sh` passes with 38 assertions |
| 2 | Write `006_dashboard_views.sql`, wire into `refresh_reporting()` | Refresh completes; unique indexes present on the two concurrent views |
| 3 | Tier 1 in Django: FC-1 to FC-6 | §4.1 acceptance criteria, including the airplane-mode and cross-domain permission tests |
| 4 | FC-7 and FC-8 on the group detail screen | Readiness rows move on meeting close without reload |
| 5 | Metabase read-only role, asserted to have no access to `wlt.ledger_entry` or `core.person` | A test that connects as the role and expects a privilege error |
| 6 | Tier 2 cards, plus the 07:00 subscription | §5 card contracts |
| 7 | Tier 3, tab 1 then tab 2 | §6 card contracts |
| 8 | Tier 4, frozen monthly, after OQ-4 is answered | §7 card contracts |

Steps 1 and 5 are gates, not tasks. Do not skip either to demonstrate a dashboard sooner.

### Definition of done, per card

- Reads a view, never an application table.
- Every percentage carries its denominator or its threshold.
- Renders correctly with zero rows, and says `no records` rather than `0`.
- Carries its as-of time.
- Has a table twin.
- Its card ID appears in the markup as `data-card`.
