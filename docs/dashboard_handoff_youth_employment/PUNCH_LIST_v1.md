# Punch List: Built App vs Handoff Spec

Youth Employment Case Management and Referral Platform. Reviewed 17 August 2026 against `README.md` (Draft v2) and `django/CASE_MANAGER_DASHBOARD.md`.

**Version 3, 17 Aug 2026 21:25.** Adds Tier 3. Version 2 added Tier 2 and corrected two version 1 findings.

Every item carries a card ID from the handoff, so it drops straight into the backlog.

## Corrections to version 1

The Tier 2 capture showed evidence that was not visible on Tier 1. Two v1 findings were wrong and are restated below.

| v1 finding | v1 claim | What the evidence actually shows |
|---|---|---|
| **P1-1** | The alert engine is not firing. | It is firing. Tier 2 shows 418 overdue alerts across four case managers. The Tier 1 tile read 0 because it filters on `assigned_to = user`, and the signed-in admin owns no alerts. Downgraded to **P2-10**, a display consequence of P1-2. |
| **P1-3** | Referral confirmation never advances. | It advances. Tier 2 shows partner medians of 8 to 10 days on roughly 622 referrals with a recorded decision. Restated as **P1-3 (revised)**: a cohort of 117 referrals is stuck at 477 days and nothing escalates it. |

Neither correction reduces the work. P1-2 grows in importance, because it is now the cause of two visible symptoms rather than one.

This file lists defects only. For what each file in the bundle is and how to use it, read `START_HERE.md`. For the card contracts an item refers to, read `README.md` sections 4 to 6, or `django/CASE_MANAGER_DASHBOARD.md` section 5 for the CM cards.

## Scope of this review

| | |
|---|---|
| Reviewed | Tier 1, "My work" at `/dashboard/my-work`. Capture 17 Aug 17:38. |
| Reviewed | Tier 2, "Woreda oversight" at `/dashboard/woreda`. Capture 17 Aug 20:36. |
| Reviewed | Tier 3, "Programme performance" at `/dashboard/programme`. Capture 17 Aug 21:22. |
| Not reviewed | Tier 4 "Results". The tab exists in the nav. No capture supplied. |
| Not reviewed | CM-7, the referral stack timeline. It sits on the case detail screen, not on a dashboard route. |

Section 6 lists what to check on the remaining tab.

## Severity key

| Level | Meaning |
|---|---|
| **P1** | Blocks pilot. The screen reports something false, or a security boundary is open. |
| **P2** | Ships, but a design rule in the spec is not met. Fix before UAT. |
| **P3** | Known gap, already disclosed in the UI. Schedule it. |

---

## 1. P1 defects

### P1-1 · WITHDRAWN, see P2-10
The v1 claim that the alert engine was not firing is wrong. Tier 2 shows 119, 97, 105 and 97 overdue alerts against the four case managers, 418 in total. The engine works. The Tier 1 tile reads 0 for a correct but misleading reason, now tracked as P2-10.

### P1-2 · RBAC is not scoping the dashboard
**Card:** all of Tier 1
**Observed:** The sidebar identifies the signed-in user as "Platform Admin, System administrator". CM-3 shows 540 cases (250 active, 113 referral pending, 52 stalled, 70 placed, 55 exited).
**Expected:** Dev Spec §7 gives the system administrator configuration access only, no case content. `scoped_cases()` returns `qs.none()` for that role. A case manager sees 80 to 200 cases, not 540.
**Why it matters:** This is the PII boundary. The reporting schema was deliberately built without names so that this boundary lives in one place, in the Django ORM. If it is open for one role it is probably open for all of them.
**Check:** Sign in as each of the ten roles and confirm the case count. The failing assertion is `test_system_admin_sees_no_case_content` in `CASE_MANAGER_DASHBOARD.md` §4.
**Spec:** Dev Spec §7. Handoff `CASE_MANAGER_DASHBOARD.md` §4.

### P1-3 (revised) · A 117-referral cohort is stuck, and nothing escalates it
**Card:** CM-2, WS-4
**Observed:** Tier 1 lists 117 referrals awaiting partner response at 477 to 513 days. Tier 2 shows the same partners answering in a median of 8 to 10 days across roughly 622 referrals with a recorded decision.
**What this means:** The state machine works. The v1 diagnosis was wrong. What exists instead is a stranded cohort: 117 referrals that were raised, never answered, and never escalated, cancelled or replaced.
**Why it still blocks the pilot:** Dev Spec §6.2 has no transition out of Pending Confirmation except partner action or case manager cancellation. A referral with no answer sits in Pending forever, holds a slot against the two-referral parallel cap in §6.3, and drags the loop-closure denominator down permanently. At 117 out of roughly 740 referrals, that is 16 percent of the pipeline frozen.
**Check:**
```sql
SELECT confirmation_status,
       count(*),
       min(current_date - initiated_date) AS min_age,
       max(current_date - initiated_date) AS max_age
FROM referrals_referral GROUP BY 1;
```
Expect a bimodal age distribution: a healthy recent group, and the stranded tail.
**Fix, two parts:**
1. Add an auto-cancel or auto-fail rule for referrals past a configurable abandonment threshold, with `failure_reason_code = 'PARTNER_NON_RESPONSIVE'`. That code already exists in Dev Spec §5.4 and nothing currently sets it.
2. Decide the threshold with programme management, and add it to `rpt.reporting_parameters` beside `confirmation_threshold_days`.

**Third piece of evidence, from Tier 3:** only 14 `referral confirmation overdue` alerts exist against 117 pending referrals. 103 of them are past threshold with no alert. The stranded cohort is invisible to the alerting layer as well as to the state machine, so nobody would ever be told about it. See G-4.
**Spec:** Dev Spec §5.4, §6.2, §6.3. This is a genuine gap in the state machine, not an implementation slip.

---

## 2. Tier 1: P2 defects and missing panels

| ID | Card | Issue | Expected |
|---|---|---|---|
| **P2-1** | CM-2 tile | Subtitle reads "No referral is waiting on a partner" above the number 117. The conditional is inverted or the string is hardcoded. | "N older than 7 days", computed from `confirmation_threshold_days`. |
| **P2-2** | Tile row | The "Active referrals" tile is absent. Built row has four tiles, spec has five. | Count of referrals with `status = 'active'`, subtitled "across N youth". |
| **P2-3** | CM-2 | Waiting days render as plain text. No threshold badge. | Badge keyed to `confirmation_threshold_days`: under threshold, at threshold, beyond threshold. Colour plus the day count as text, never colour alone. |
| **P2-4** | CM-2 | The threshold footnote is absent. | "Threshold: partner confirmation overdue after N days (`alert.threshold_days`, configurable per alert type)." |
| **P2-5** | CM-3 | Status names render as plain links. No status chip. | Chip pairing colour, word and a geometric mark, per the design tokens. Survives greyscale and direct sunlight. |
| **P2-6** | CM-1, CM-2, CM-4 | No "View all N" link on any list. Lists appear to render every row. | Slice to 6 rows in the template, with a link to `/dashboard/queue/<slug>/`. Fetching 117 rows to show 6 breaks the sub-100 KB budget. |
| **P2-7** | Page header | No freshness stamp. | "Live, refreshed N min ago" for Tier 1. Tiers 2 to 4 read `rpt.v_freshness`. A dashboard that does not state its age invites the reader to assume it is live. |
| **P2-8** | Page header | Reads "Woreda: (blank)". Woreda context is not resolving. | The signed-in user's `woreda_assignment`. This will break every woreda filter on Tiers 2 and 3. |
| **P2-10** | CM-1 tile | Reads 0 while Tier 2 shows 418 overdue alerts across the team. The queryset filters `assigned_to = user` correctly; the signed-in admin owns none. The screen is therefore truthful and useless at the same time. | Any role that is not a case manager should see either their own queue or an explicit "no alerts are assigned to you" state, never a bare 0 beside a caseload of 540. Falls out of P1-2. |
| **P2-9** | CM-3 | Row ordering is correct (Active, Referral Pending, Stalled, Placed, Exited). No action needed. Recorded so it does not get "fixed" into size order later. | Keep workflow order. Sorting by count makes the table unreadable across time. |

### Positive findings, worth keeping

| Card | Note |
|---|---|
| CM-4 | The disclosure block naming the three uninstrumented conditions is exactly the behaviour the spec asks for. It reports a gap instead of a silent zero. Keep this pattern for every partially-built card. |
| CM-3 | Semantic row order preserved. |
| Header | The EN / አማርኛ / Afaan Oromo toggle is beyond the dashboard spec and is welcome. Check number formats and dates in each language, not only labels. |

---

## 3. Tier 1: P3 known gaps

| ID | Card | Gap | Note |
|---|---|---|---|
| **P3-1** | CM-4 | 1 of 4 risk conditions instrumented. Missing: 3 consecutive training absences, left a placement with no exit reason, 4+ failed contact attempts. | Already disclosed in the UI. Needs training attendance records, `Placement.exit_reason`, and follow-up call logging. |
| **P3-2** | CM-7 | Referral stack timeline not verified. | On the case detail screen. Reference implementation in `django/referral_stack_svg.py`. |
| **P3-3** | Tier 1 | Query count and page weight not measured. | Budget is 12 queries and 100 KB. See `CASE_MANAGER_DASHBOARD.md` §8. |

---

## 4. Tier 2, Woreda oversight

Four of the six WS cards are built. Two are absent, and one card lost the segment that matters most.

### 4.1 Card status

| Card | Spec | Built | Status |
|---|---|---|---|
| WS-1 | Team caseload by status, 100% stacked, 4 segments | Built, per case manager, with caseload and overdue count on the right | **Partial**, see W-1 |
| WS-2 | Unassigned youth count | Replaced with an honest "not measurable yet" plus a working proxy | **Built well**, see the positive findings |
| WS-3 | Overdue actions by case manager, sorted row chart | Folded into WS-1 as a right-hand annotation | **Merged**, and this is an improvement, see W-2 |
| WS-4 | Referral response time by partner, median, n shown | Built as a table | **Built** |
| WS-5 | Woreda pipeline, row chart with drop-off | Absent | **Not built.** Also absent from the prototype, see W-6 |
| WS-6 | Data completeness | Built, with a consequence column the spec did not ask for | **Built well** |
| Filter row | Period and pathway, one row above everything | Absent | **Not built**, see W-4 |
| Stat tiles | Five tiles | Absent | **Not built**, see W-5 |

### 4.2 Findings

| ID | Sev | Card | Issue |
|---|---|---|---|
| **W-1** | **P1** | WS-1 | **The "Awaiting partner" segment has been dropped.** Built segments are In progress / Stalled / Placed / Closed. The spec's four are On track / **Awaiting partner** / Stalled / Exited or placed. The build spends two of its four segments on terminal states (Placed, Closed) and none on the one live state a supervisor can act on. Given the 117 stranded referrals in P1-3, "awaiting partner" is precisely the segment that would surface the problem, and it is the one that was cut. Collapse Placed and Closed into one segment and restore Awaiting partner. |
| **W-2** | none | WS-1, WS-3 | **Merging the overdue count into the caseload row is better than the spec.** "Caseload 141, 119 overdue" puts the number and its denominator on one line, which is exactly what the spec's separate WS-3 card needed a paragraph of warning text to achieve. Keep it. Update the spec, not the build. |
| **W-3** | P2 | WS-1 | Two segments per row carry no label. Small segments are left blank while larger ones show a count. The spec requires every segment direct-labelled, because gold and grey both fall below the 3:1 ratio against the surface and cannot carry meaning by fill alone. Move the label outside the segment when it does not fit inside. |
| **W-4** | P2 | Page | No filter row. The spec requires one row above everything it scopes: period (week, month, quarter) and pathway. Without it the supervisor cannot answer "what changed this month". |
| **W-5** | P2 | Page | No stat tiles. Five are specified: unassigned youth, overdue actions across the team, open cases, median days to confirm, outcomes verified this month. Four of the five are already computed elsewhere on the page and only need surfacing. |
| **W-6** | P2 | WS-5 | Woreda pipeline is missing from the build **and from the prototype**. This is a gap in the handoff, not in the build. `rpt.mv_pipeline_summary` already supports it; filter on woreda. |
| **W-7** | P2 | Page | Header reads "All woredas" on a page titled "Woreda oversight", and the top bar still reads "Woreda: (blank)". A supervisor must be scoped to their assigned woreda. Same root cause as P1-2. |
| **W-8** | P2 | WS-1 | Legend uses two greens (In progress, Placed) adjacent to a grey. Check the adjacent-segment ratio reaches 3:1, per WCAG 1.4.11. If it does not, use the validated palette in `README.md` §8.4. |
| **W-9** | P2 | WS-4 | Table is unsorted. Medians read 8, 9, 8, 10, 10, 9 and n reads 109, 107, 108, 104, 102, 92. Sort by median descending so the slowest partner is at the top, and show the threshold, as the spec's row chart does. |
| **W-10** | P2 | WS-6 | "Complete" is shown for outcome type and failure reason. If the denominator is zero, that is not completeness, it is absence of records. Distinguish "0 missing of 147" from "no records to check". This is the same 0-versus-no-data rule the spec applies to PM-6. |
| **W-11** | P2 | Page | No as-of stamp and no delivery note. Tier 2 is specified as a 05:30 refresh feeding an 07:00 email subscription. Neither is visible. Read `rpt.v_freshness`. |
| **W-12** | P3 | WS-4 | Response times are suspiciously uniform: six partners, medians 8 to 10 days, n between 92 and 109. Real partner performance varies far more. Confirm this is seeded data before anyone reads it as a finding. |

### 4.3 What Tier 2 tells us about the data

Three numbers reconcile cleanly, which is a good sign for the underlying model:

| Figure | Source | Reconciles |
|---|---|---|
| 540 cases | Tier 1, CM-3 | + 74 registered with no case = 614 |
| 614 records | Tier 2, WS-6 denominator | matches |
| 418 overdue alerts | Tier 2, WS-1 annotations | 119 + 97 + 105 + 97 |

Two numbers do not:

- **Four case managers on Tier 2, five in the spec.** Caseloads of 141, 138, 134 and 127 total 540, so the four are the whole population. Fine, but the caseload ceiling in `rpt.reporting_parameters` defaults to 120 and every one of them exceeds it. Nothing flags this. The ceiling is configured and unused.
- **418 overdue alerts against 540 cases.** Roughly four in five cases carry an overdue action. Either the thresholds are too tight for a pilot at this stage, or the backlog is real. Either way, a work queue where almost everything is overdue prioritises nothing. Review the threshold defaults with programme management before UAT.

### 4.4 Positive findings on Tier 2

| Card | Note |
|---|---|
| WS-2 | "Not measurable yet: every case must have a case manager, so a youth cannot be left unassigned", followed by the measurable proxy "Registered, no case yet: 74". This is the correct answer to OQ-12, and it is better than the spec: rather than reporting a false zero or omitting the card, it explains the constraint and substitutes a number that means something. Third time this team has handled a gap this way. Make it the house pattern. |
| WS-6 | The "Vs programme" column, explaining what each missing field costs, is not in the spec and should be. It turns a data-quality table into an argument for fixing the data. |
| WS-1 | Caseload and overdue count on one line. See W-2. |

---

## 5. Tier 3, Programme performance

Six of the eight PM cards are built, one of them wrong in a way that makes it useless. Two more cards were built that the spec and prototype both omitted.

### 5.1 Card status

| Card | Spec | Built | Status |
|---|---|---|---|
| PM-1 | Pipeline, 8 stages, drop-off and median days in stage | Built, 5 stages | **Partial**, see G-5 |
| PM-2 | Small multiples of the pipeline per woreda | Reduced to one placement-rate bar per woreda | **Partial**, see G-9 |
| PM-3 | Referral category to outcome, pivot with zero cells | Built, zero cells rendered as `0` | **Built, and useless**, see G-1 |
| PM-4 | Partner league table sorted by n, with verdicts | Built, sorted by closed descending, CIs and verdicts present | **Built correctly**, see the positives |
| PM-5 | Cohort retention heatmap | Absent, disclosed as "not measurable yet" | **Not built**, honestly |
| PM-6 | 90-day disposition | Absent | **Not built** |
| PM-7 | Parallel referral load | Built. 40 of 469 cases, 0 above the cap | **Built**, and it is not in the prototype |
| PM-8 | Data health and refresh age | Absent from Tier 3 | **Not built** |
| Filter row | Woreda, sex, age band | Absent | **Not built**, see G-7 |
| Confirmation lag by partner | Not in the spec | Built | **New**, keep it |
| Open alerts by type | Not in the spec | Built | **New**, keep it, see the positives |
| Gender split of placements | Not in the spec | Built | **New**, keep it, see G-10 |

### 5.2 Findings

| ID | Sev | Card | Issue |
|---|---|---|---|
| **G-1** | **P1** | PM-3 | **The matrix is a tautology.** 86 of 195 completed referrals carry a non-Other outcome, and **all 86 sit exactly on the canonical category-to-outcome mapping in Dev Spec §5.3. Zero crossovers.** Training produced 14 training completions and 0 job placements. Employment produced 12 job placements and 0 of anything else. A real dataset always has some. This means `outcome_type` is being derived from `referral_category` rather than recorded by the person verifying the outcome. The card then reproduces the §5.3 lookup table and tells you nothing. PM-3 exists to expose the onward-referral gap, which is precisely the crossover this build cannot represent. Make `outcome_type` an independently recorded field on outcome verification. |
| **G-2** | **P1** | Whole page | **Three different numbers are labelled "placed" on one screen.** The tile says 14 placements this quarter. Woreda comparison totals 30 placed. The pipeline says 168 "placed or completed". Each is defensible alone; together they guarantee the reader picks the wrong one, and this is the screen a programme manager quotes in a meeting. Rename the pipeline stage to what it measures ("first referral closed successfully"), and state the period on every placement figure. |
| **G-3** | **P1** | PM-3 | **56 percent of completed referrals have `outcome_type = 'Other'`** (109 of 195). Dev Spec §5.3 requires a free-text note with Other. More than half the outcomes uncategorised makes every outcome breakdown, including the donor tier, unreportable. Treat Other above a threshold as a data-quality alert, not a valid outcome. Related to G-1: if the derived value cannot be inferred, the code falls through to Other. |
| **G-4** | **P2** | Open alerts | **Alert coverage gap.** Only 14 `referral confirmation overdue` alerts exist, against 117 referrals sitting unanswered on Tier 1 at 477 days and over. **103 pending referrals past threshold have no alert.** Either the rule only evaluates recent referrals, or an alert was raised once, actioned or dismissed, and never re-raised. This sharpens P1-3: the stranded cohort is invisible to the alerting layer as well as to the state machine. |
| **G-5** | P2 | PM-1 | Pipeline reduced from 8 stages to 5. "Service attended" is correctly absent (OQ-1, the field does not exist). But **Profiled and eligible** and **Pathway assigned** are missing although the data exists: Tier 2 reports 82 of 614 profiling records missing, so 532 are present. Those two stages are where 145 youth are lost in the spec's model, and the build cannot see it. |
| **G-6** | P2 | PM-1 vs partner cards | **Units are not labelled.** PM-1 says 336 partner confirmed. The confirmation-lag card totals 620 confirmed referrals. Both are right: PM-1 counts youth, the lag card counts referrals, and a youth holds several. Unlabelled, they read as a contradiction. Put "youth" or "referrals" on every axis and denominator. |
| **G-7** | P2 | Page | No filter row. The spec requires woreda, sex and age band above everything they scope. Without sex and age band the page cannot answer the equity question its own gender-split card raises. |
| **G-8** | P2 | Page | No as-of stamp. Tier 3 is specified as a nightly 02:00 refresh and must be explicitly dated. The header says "Q3 2026, All woredas" but not when the numbers were computed. |
| **G-9** | P2 | PM-2 | Woreda comparison collapsed to a single placement-rate bar (6%, 5%, 4%). The spec asks for small multiples of the pipeline so a reader can see **which stage** each woreda loses youth at. Three near-identical rates say there is no difference; a stage comparison would say where the difference is. |
| **G-10** | P2 | Gender split | "33% women, 67% men, 22 of 30" does not add up and does not say what 22 is. 33% of 30 is 10, not 22; 67% of 30 is 20, not 22. Label the denominator explicitly, and state if the percentages are of 30 or of the 22 records with a recorded sex. |
| **G-11** | P2 | Retention | The build introduces a **third retention anchor**: "retained at 6 months". The spec has 30/60/90 days from placement for operations and 3 months from programme exit for the donor tier. Three anchors will produce three different retention rates that nobody can reconcile. Pick from OQ-9 before building PM-5. |
| **G-12** | P2 | PM-4, Tier 2 WS-4 | Adama Skills Hub shows **n = 108 on Tier 2 and n = 106 on Tier 3** for the same metric. The other five partners match exactly. If the difference were a period filter all six would move. Investigate before either number is quoted. |
| **G-13** | P3 | PM-5, PM-6, PM-8 | Not built. PM-5 and PM-6 are blocked on retention checkpoint data and are honestly disclosed. PM-8 has no blocker: `rpt.v_freshness` and `rpt.mv_data_completeness` already exist. |
| **G-14** | P3 | PM-1 | The "Placed or completed" bar renders gold while every other bar is green, with no legend. If that is an emphasis highlight, label it. Gold falls below the 3:1 ratio and may not carry meaning by fill alone. |

### 5.3 The one number worth taking to the task team

**Partner confirmed 336, placed or completed 168. A 50 percent loss, median 64 days in stage.**

This is the largest single loss in the pipeline and the longest stage, and it is the same gap the prototype predicted with different numbers. Half of all youth who reach a confirmed referral never reach an outcome, and they spend two months in that state. Nothing else on the page matters as much.

### 5.4 Positive findings on Tier 3

| Card | Note |
|---|---|
| PM-4 | **The league table behaves exactly as designed.** Sorted by closed descending (66, 63, 63, 61, 58, 50). Every partner returns "as expected" with overlapping intervals around a programme rate of 54 percent. That is the funnel-plot logic working: with these sample sizes the partners are genuinely indistinguishable, and the table refuses to invent a ranking. Resist any request to sort it by rate. |
| Internal consistency | Three independent reconciliations hold. PM-4 completed (195) equals the PM-3 matrix total (195). Woreda registered (212 + 202 + 200) equals the pipeline top (614). Open alerts (190 + 159 + 55 + 14) equals Tier 2's overdue total (418). The underlying model is sound. |
| Open alerts by type | Not in the spec and it should be. Splitting 418 alerts into onward prompt, replacement prompt, stall and confirmation overdue is what made G-4 visible. Add to `README.md` §5. |
| Gender split | Not in the spec and it should be. Placing the placement gender split beside the registration split (33 percent against 42 percent) surfaces a 9-point equity gap in one line. Fix the arithmetic per G-10, then promote it to Tier 4. |
| PM-7 | Built although absent from the prototype. "0 above the cap" is the evidence OQ-7 needs. |
| "Not measurable yet" | Fifth and sixth use of this pattern, now on retention. Consistently applied across three tiers by three different cards. This is the team's strongest habit. |

---

## 6. Verification checklist for the remaining tab

Send a full-page capture of each tab, or run these checks directly.

### Before checking any card

| # | Check | Pass condition |
|---|---|---|
| V-1 | `\dn` in psql | Schema `rpt` exists |
| V-2 | `SELECT count(*) FROM rpt.refresh_log;` | Non-zero. If zero, the views were never refreshed and every Tier 2 to 4 card is empty or stale. |
| V-3 | `SELECT * FROM rpt.v_freshness;` | Two rows, `operational` and `donor`, neither stale |
| V-4 | Run `sql/900_test_seed_and_assertions.sql` against a copy of the database | Prints `ALL REPORTING LAYER ASSERTIONS PASSED` |
| V-5 | Connect as `metabase_ro`, `SELECT * FROM youth_youth` | Permission denied |
| V-6 | Check if Tier 2 to 4 cards query `rpt.*` or the application tables | Must be `rpt.*`. Live queries work at 540 records and fail at pilot scale. |

### Tier 4, M&E and donor

| Card | Check |
|---|---|
| ME-1 | Indicator names match the PSNP 5 and Jobs Toolkit wording verbatim. As-of date in the card title. |
| ME-2 | One axis, two series, both counts, direct-labelled. No dual axis, no gauge. |
| ME-3 | Suppression applied and visible. Footnote explains `*` and the suppressed rows. Suppressed cells do not publish their numerator. |
| ME-4 | Denominators on every row. The `anchor` column visible, showing placement or exit. |
| ME-5 | Narrative text card present, naming the gross-not-net caveat and the verified subset. |
| Refresh | Monthly, not nightly. Confirm `rpt.refresh_donor` is on a monthly beat schedule. |

---

## 7. Suggested fix order

**Fix these three before anyone quotes a number from Tier 3 or 4.**

1. **G-1** Record `outcome_type` independently of `referral_category`. Until this changes, every outcome breakdown on Tiers 3 and 4 restates the Dev Spec §5.3 lookup table rather than reporting what happened.
2. **G-3** The 56 percent Other rate. Cause and effect are entangled with G-1, so fix them together.
3. **P1-2** RBAC. A security boundary, and the cause of four visible symptoms across three tiers.

**Then, in order:**

4. **G-2** Three numbers labelled "placed" on one screen. Cheap, and it is the screen that gets quoted in meetings.
5. **W-1** Restore the "Awaiting partner" segment on WS-1. One line, and it surfaces P1-3.
6. **P1-3 and G-4** The abandonment rule plus the alert coverage gap. Needs the threshold decision in section 8 first.
7. **V-1 to V-6.** Establish if the `rpt` schema is deployed and if the build survives pilot scale.
8. **G-5, G-9** Restore the missing pipeline stages and the woreda small multiples. The data exists for both.
9. **G-6, G-10, G-12** Label units, fix the gender arithmetic, reconcile the Adama Skills Hub n.
10. **W-4, W-5, G-7, G-8, P2-7, W-11** Filter rows, stat tiles, as-of stamps across all three tiers.
11. **P2-1, P2-2, P2-3, P2-5, W-3, W-8, G-14** The remaining display items.
12. **W-6, G-13** Build WS-5 and PM-8. Neither has a blocker.
13. **P3-1** The three remaining risk conditions, as their source data lands.

Items W-2, G-13's positives, the WS-2 and WS-6 treatments, and the three new Tier 3 cards are improvements on the spec. Fold them into `README.md` rather than changing the build.

## 8. Three things to decide

### 8.1 Can a case manager record a partner confirmation on the partner's behalf?

Partners answer in a median of 9 to 10 days when they answer, across 620 confirmed referrals. Self-confirmation works most of the time. The 117 stranded referrals are where it did not.

| Option | Effect |
|---|---|
| Partner self-confirms only | Clean audit trail. Referrals stall when partners do not respond. |
| Case manager may record a confirmation, tagged with who reported it | Referrals move. Keep `confirmed_by` and a new `confirmation_recorded_by` separate, so partner responsiveness stays measurable. |

### 8.2 What are the correct alert thresholds, and what is the abandonment threshold?

418 open alerts against 540 cases. Four in five cases carry an overdue action, so nothing is prioritised. Separately, only 14 of 117 overdue referrals raise an alert at all.

1. Is 7 days right for partner confirmation, where partners may check the system weekly? The Tier 3 card states a programme standard of 14 days, which contradicts the 7 in `rpt.reporting_parameters`. Settle on one.
2. What is `referral_abandonment_days`, after which an unanswered referral auto-fails with `PARTNER_NON_RESPONSIVE`? The parameter now exists and is null. It needs a number.
3. `caseload_ceiling` defaults to 120. All four case managers run 127 to 141 and nothing flags it. Raise it or surface the flag.

### 8.3 Which retention anchor is the reportable one?

The build now shows a third anchor. That is one too many.

| Anchor | Where it appears | Purpose |
|---|---|---|
| 30/60/90 days from placement | Spec, PM-5 | Case manager follow-up |
| 3 months from programme exit, unsubsidised | Spec, ME-4 | Rolls up to the World Bank |
| 6 months, unspecified start | Tier 3 build | Unclear |

`rpt.mv_cohort_retention` already computes the first two, with an `anchor` column. Decide which is reportable, then drop or align the third. Tracked as OQ-9.
