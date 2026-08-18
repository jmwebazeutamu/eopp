# Handoff: Dashboards and Reporting

Youth Employment Case Management and Referral Platform, Ethiopia. Companion to `YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`. This bundle is authoritative for Section 8 of that document. Section 8 previously listed nine dashboards in one flat table with no audience split, no indicator definitions and no visualisation guidance; the nine are all still here, redistributed across four audiences and given formulas, denominators, chart types and acceptance criteria. Dev Spec §8 has since been rewritten to point here.

Draft v2, August 2026. For Claude Code.

**New to this bundle? Read `START_HERE.md` first.** It maps every file to a role and a purpose in two pages, and carries a runnable quickstart for the database layer.

## Paste This to Claude Code

```
Build the dashboard and reporting layer described in
dashboard_handoff_youth_employment/README.md. Read that file fully first, then
the two companion specs it points to.

Build in the order in §3. Run the SQL in sql/ in filename order; 900_* is the
test harness and must pass before you move on. The case manager tier is a Django
view, not a Metabase dashboard: see django/CASE_MANAGER_DASHBOARD.md and do not
substitute Metabase for it.

Do not silently resolve anything in §9 Open Questions. Implement the stated
working default and leave a # TODO(open-question) comment pointing at this file.
```

## What is in this bundle

```
dashboard_handoff_youth_employment/
├── START_HERE.md                          what every file is for, and who uses it
├── README.md                              this file: the authoritative spec
├── django/
│   ├── CASE_MANAGER_DASHBOARD.md          tier 1 implementation contract
│   └── referral_stack_svg.py              server-rendered timeline, reference implementation
├── sql/
│   ├── 000_test_fixture_schema.sql        stub app tables: TEST ONLY, Django owns these
│   ├── 001_reporting_schema.sql           rpt schema, read-only role, tunable parameters
│   ├── 002_helper_functions.sql           suppression bands, Wilson CIs, funnel verdicts
│   ├── 003_materialized_views.sql         the reporting layer proper
│   ├── 004_indexes.sql                    refresh performance + CONCURRENTLY prerequisites
│   ├── 005_refresh.sql                    refresh procedures, Celery beat schedule
│   └── 900_test_seed_and_assertions.sql   seeded fixtures + assertions A-Q; CI gate
├── PUNCH_LIST_v1.md                       built app vs spec, 17 Aug 2026
├── prototype/
│   └── Youth_Employment_Dashboard_Prototype_v1.html   clickable, 5 tabs, illustrative data
└── screenshots/                           the four tiers, the rationale tab, the timeline
```

The prototype is a **design reference in HTML**, not production code. Card IDs are defined in this document (§4 to §6) and in `django/CASE_MANAGER_DASHBOARD.md` §5; the matching cards in the prototype carry a `data-card` attribute. Open it before writing any code.

Two companion documents sit beside this folder and are referenced throughout:

- `../REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`: the React timeline component and the `ReferralTimelineItem` data contract
- `../design_handoff_youth_employment/README.md`: design tokens and component specs, authoritative for both the React and the server-rendered implementations

---

## 1. The organising decision: four dashboards, not one

Build four small dashboards, not one dashboard with role-based hiding. A single dashboard with permissions always converges on the union of every stakeholder's requirements, and the case manager ends up looking at donor indicators.

| Tier | User | Question answered | Refresh | Where it lives | Primary medium |
|---|---|---|---|---|---|
| **1 Operational** | Case manager | What do I do next? | Live | **Django** | Lists, counts, exception queues |
| **2 Tactical** | Woreda supervisor | Which staff, which cases need me? | Daily 05:30 EAT | Metabase | Ranked tables, small bars |
| **3 Analytical** | Programme manager | Where is the process breaking, and for whom? | Nightly 02:00 EAT | Metabase | Pipeline bars, cohort tables, partner comparisons |
| **4 Strategic** | M&E / World Bank | Are we hitting targets? | **Monthly, frozen** | Metabase | Indicator table vs target, one trend line, narrative |

Six cards per dashboard, hard cap nine. Tier 3 now specifies eleven, which is over the cap: split it across two dashboard tabs (Pipeline, then Outcomes and quality), never one long page. Each Metabase card is an independent query round-trip; on 3G, card count dominates perceived load time. If a tier needs more, use dashboard tabs or a linked second dashboard, never a longer page.

**What must not appear on each tier:**

- **Tier 1:** no percentages, no charts, no comparison with other case managers, no trend lines. Anything that cannot be clicked to produce a list of named youth should be deleted.
- **Tier 2:** no donor indicators, no annual targets, no unadjusted staff leaderboards.
- **Tier 3:** no live case detail, no PII, no real-time counts. Explicitly as-of dated.
- **Tier 4:** no operational noise, no unstable disaggregations, no metric that needs more than one sentence to define. This should be the smallest dashboard you build.

## 2. Two architecture calls that change the Dev Spec

### 2.1 The case manager dashboard is not a Metabase dashboard

It belongs in Django, inside the case management app. Three blockers, not preferences:

1. **PII boundary.** This screen shows named youth. The `rpt` schema deliberately contains none, and Metabase's row-and-column security is a paid-tier feature. A per-youth access boundary belongs in the Django ORM, enforced in the queryset and covered by tests.
2. **Latency.** Six Metabase cards is six round-trips. This page must be one server-rendered request under 100 KB.
3. **Action affordance.** Every element links into a filtered list or a case. A BI tool renders numbers; this screen renders work.

Full contract: `django/CASE_MANAGER_DASHBOARD.md`.

### 2.2 Sprint 7 is too late and too monolithic

Dev Spec §10 originally put all nine dashboards in Sprint 7. The case manager work queue is not a reporting feature: it is the thing that makes the system worth opening, and without it there is no data to report on. Resequence:

| Work | Was | Now |
|---|---|---|
| Case manager work queues (CM-1 … CM-6) | Sprint 7 | **Sprint 4**, with the alert engine that feeds them |
| Referral stack timeline | Sprint 3 | Sprint 3 (unchanged), plus the server-rendered SVG fallback |
| `rpt` schema, helpers, materialised views | Sprint 7 | **Sprint 5**, once Training and Placement exist |
| Metabase, tiers 2 and 3 | Sprint 7 | Sprint 7 |
| Tier 4 donor dashboard | Sprint 7 | Sprint 7, last |

Build inside-out. The donor dashboard has the loudest stakeholder and the least operational value.

## 3. Build order

Each step is independently verifiable. Do not start a step before the previous one's check passes.

| # | Step | Verified by |
|---|---|---|
| 1 | Run `sql/001` … `sql/005` in filename order against a scratch database seeded by `sql/000` | No errors; `rpt.refresh_all()` completes |
| 2 | Run `sql/900_test_seed_and_assertions.sql` | Prints `ALL REPORTING LAYER ASSERTIONS PASSED`; wire into CI as a blocking gate |
| 3 | Django `apps/reporting/`: Celery tasks calling the refresh procedures, admin for `rpt.reporting_parameters` and `rpt.indicator_targets` | Beat schedule fires; a parameter change moves every dependent card |
| 4 | Tier 1 Django views | `django/CASE_MANAGER_DASHBOARD.md` §8 acceptance criteria |
| 5 | Metabase deployment, `metabase_ro` connection, caching on | `metabase_ro` cannot read any table in `public`: assert it |
| 6 | Tier 2 cards + the 07:00 email subscription | §4 card contracts + the §10 checklist |
| 7 | Tier 3 cards | §5 card contracts + the §10 checklist |
| 8 | Tier 4 cards, frozen monthly | §6 card contracts + the §10 checklist |

**Step 5 is a security gate, not a config step.** Write a test that connects as `metabase_ro` and asserts `SELECT` on `youth_youth` raises insufficient privilege.

## 4. Tier 2: Woreda supervisor

Six cards. Delivered as an **07:00 server-rendered email subscription**, with the interactive dashboard as the drill-down. On 3G, a rendered snapshot in the inbox is a better product than a dashboard that takes twelve seconds to paint.

| ID | Card | Source | Visualisation | Rules |
|---|---|---|---|---|
| WS-1 | Team caseload by status | `rpt.mv_caseload_status`, `rpt.mv_alert_load` | 100% stacked row per case manager | **≤ 4 segments, and one must be "Awaiting partner".** Six statuses collapse to four via `display_segment`; six adjacent segments cannot hold WCAG 1.4.11's 3:1 non-text ratio. Do not spend two segments on terminal states: collapse Placed and Closed into one. A supervisor can act on a case that is waiting and cannot act on one that is finished. Every segment direct-labelled, outside the bar when it does not fit inside. **Carry the caseload size and the overdue-alert count on the same row**, per WS-3. |
| WS-2 | Unassigned youth | `rpt.dim_youth` where `case_manager_id IS NULL`; fallback below | Big number + link | Requires `Case.case_manager_id` to be **nullable**. Dev Spec §4.2 marks it Required; Dev Spec §11.1 tracks the change. Until then, do not ship a zero. State the constraint plainly ("every case must have a case manager, so a youth cannot be left unassigned") and substitute the measurable proxy: **youth registered with no case record yet**. A named constraint plus a real number beats a false zero. |
| WS-3 | Overdue actions by case manager | `rpt.mv_alert_load` | Annotation on WS-1, or a sorted row chart | **Counts, never a rate.** A per-staff rate is noise at n = 71 and creates cream-skimming pressure. The count must appear beside its denominator. Rendering it as a right-hand annotation on the WS-1 row ("Caseload 141, 119 overdue") does this in one line and is preferred over a separate card, which needs a paragraph of warning text to achieve the same thing. |
| WS-4 | Referral response time by partner | `rpt.mv_partner_performance` | Row chart of `median_days_to_confirm` | **Median, not mean.** Show n per partner. |
| WS-5 | Woreda pipeline | `rpt.mv_pipeline_summary` filtered to the woreda | Row chart + drop-off column | See PM-1 |
| WS-6 | Data completeness | `rpt.mv_data_completeness` | Table, worst case manager named | A programme widget, not an IT widget. **Carry a consequence column** saying what each missing field costs ("Follow-up calls cannot be made", "No pathway can be justified without it"). That turns a data-quality table into an argument for fixing the data. Missing `failure_reason_code` is the highest-cost gap: it breaks the replacement prompt and the partner failure breakdown at once. Where the denominator is zero, show "no records to check", never "Complete". |

## 5. Tier 3: Programme manager

Eleven cards across two tabs. PM-1 to PM-4 and PM-10 on tab 1; PM-5 to PM-9 and PM-11 on tab 2.

**Tab 1: Pipeline**

| ID | Card | Source | Visualisation | Rules |
|---|---|---|---|---|
| PM-1 | Pipeline: where youth are lost | `rpt.mv_pipeline_summary` | **Row chart, shared left baseline** | **Not a funnel chart** (§7). Annotate drop-off at every transition. Show `median_days_in_prev_stage` on every row: it is the most actionable pipeline number and no funnel shows it. |
| PM-2 | Same pipeline, by woreda | `rpt.mv_pipeline_summary` | Small multiples, shared x-scale | **Not a map** (§7) |
| PM-3 | Referral category → outcome type | `rpt.mv_referral_outcome_matrix` | Pivot table, single-hue scale, counts visible | **Not a Sankey** (§7). The view CROSS JOINs the taxonomy lookups so every combination has a row, including `n_referrals = 0`; render those as `0`, never blank. The `not recorded` row is a data-quality row, not an outcome. |
| PM-4 | Partner performance | `rpt.mv_partner_performance` | Constrained league table | **`ORDER BY n_closed DESC`. Never by rate.** Show numerator, denominator, Wilson CI and the three-state verdict. Suppression already applied in SQL. |

**Tab 2: Outcomes and quality**

| ID | Card | Source | Visualisation | Rules |
|---|---|---|---|---|
| PM-5 | Placement retention by cohort | `rpt.mv_cohort_retention` **filtered to `anchor = 'placement'`** | Cohort heatmap (pivot + conditional formatting) | **Censoring is the critical mechanic.** `is_censored` cells render hatched with the `matures_on` date. Never 0%, never blank. Never mix anchors in one card. |
| PM-6 | 90-day disposition | `rpt.mv_placement_disposition` | 100% stacked bar, exactly 4 segments | `still_placed` / `left_for_better` / `left_involuntarily` / `outcome_unknown`. Voluntary exits are not failures, and `outcome_unknown` (unreachable at the check, or exit reason not recorded) is never folded into either: "0" and "we do not know" must look different. The view asserts it emits no fifth segment. |
| PM-7 | Parallel referral load | `rpt.mv_parallel_load` | Count tile + list | Dev Spec §6.3. `breaches_cap` evidences OQ-7. |
| PM-8 | Data health by woreda | `rpt.mv_data_completeness`, `rpt.v_freshness` | Table | Include refresh age. A dashboard that does not say how stale it is invites the reader to assume it is live. |
| PM-9 | Open alerts by type | `rpt.mv_alert_load` | Four labelled counts | Splits the alert backlog into onward prompt, replacement prompt, stall and confirmation overdue. A single total hides the mix, and the mix is what says where the process is failing. Compare the confirmation-overdue count against the number of referrals actually past threshold; a large gap means the alert rule is not covering the backlog. |
| PM-10 | Confirmation lag by partner | `rpt.mv_partner_performance` | Row chart of `median_days_to_confirm`, n beneath each | The programme-level twin of WS-4. State the programme standard on the card, and read it from `rpt.reporting_parameters.confirmation_threshold_days` rather than typing it, so the card and the alert rule cannot disagree. |
| PM-11 | Gender split of placements | `rpt.mv_disaggregation` | One 100% stacked bar, plus the registration split as a reference figure | Placement split beside registration split turns two percentages into an equity finding. Carry the denominator and say what it counts. Suppress below n = 30, as everywhere else. |

## 6. Tier 4: M&E and donor

Five cards, **frozen monthly**, delivered as a PDF and email subscription.

| ID | Card | Source | Rules |
|---|---|---|---|
| ME-1 | Results framework | `rpt.mv_results_framework` joined to `rpt.indicator_targets` | Indicator wording verbatim from the parent operations. As-of date in the card title. |
| ME-2 | Cumulative placements vs target | `rpt.mv_pipeline_youth` | **One axis, two series, both counts, direct-labelled.** Never a dual axis, never a gauge. |
| ME-3 | Disaggregation | `rpt.mv_disaggregation` | Suppression rule applied **and visible**. Footnote explains `*` and `-`. |
| ME-4 | Retention at each checkpoint | `rpt.mv_cohort_retention`, both anchors | Show denominators on every row; they differ per checkpoint. The `anchor` column carries `placement` or `exit`; render it as a visible column, because the two will never be equal and an unlabelled table invites the reader to average them. The exit-anchored rows are unsubsidised only. |
| ME-5 | What changed, and what is uncertain | Hand-written text card | A sentence beats another chart. Must name the gross-not-net caveat and the verified-subset figure. |

### 6.1 Indicator definitions

| Indicator | Numerator ÷ denominator | Framework |
|---|---|---|
| Youth clients with business plans financed or enrolled in wage employment | Count, no denominator | **PSNP 5 / SEASN (P172479), verbatim**: use this exact wording so woreda figures roll up without reconciliation |
| Youth who received livelihood grant | Count | PSNP 5 / SEASN (P172479), verbatim |
| Share of beneficiaries completing training | Completed ÷ initially enrolled | World Bank Jobs M&E Toolkit (2017), intermediate |
| Number of self- and/or wage employed beneficiaries | Count meeting the ILO-adapted employment criterion | Jobs M&E Toolkit, PDO-level. **Gross, not net** of deadweight or displacement |
| Wage-employed 3 months after completion | Unsubsidised employed at 3 months ÷ youth who exited 3+ months ago | Ethiopia UPSNJP (P169943) |
| Referrals confirmed within threshold | Confirmed ≤ N days ÷ referrals raised in period | Adapted from PSNP's "% of transfers within 45 days" |
| Referral loop closure rate | Outcome recorded and verified ÷ mature closed referrals | Adapted from CMS50 "Closing the Referral Loop" |

### 6.2 Disaggregation, on everything above

Sex; **age band 15–29**; woreda; pathway; PSNP client category; disability; verification source.

Rural/urban is required by both the ILO and World Bank frameworks but **has no source field**: Dev Spec §4.1 has no settlement type and woreda does not imply one. Tracked as OQ-11; `mv_disaggregation` carries a `TODO(open-question)` at the point the cut would be added.

**Ethiopia defines youth as 15–29, not the international 15–24.** Confirmed in the ILO Ethiopia Youth Country Brief (2023), the Ethiopian Statistical Service 2013 EFY Labour Force Survey, and the Federal Plan of Action for Job Creation. Implemented in `rpt.age_band()`; carry a secondary 15–24 cut for international comparability, plus ILO's 15–17 / 18–24 splits.

Two further Ethiopian conventions will silently break any comparison against ILOSTAT if ignored: the national working-age population starts at **10**, not 15, and the national unemployment definition **includes discouraged job-seekers**, which the ILO definition excludes. Carry both a strict and a relaxed measure, or the figures reconcile with neither.

## 7. Visualisation decisions, and what was rejected

| Data shape | Chosen | Rejected | Why |
|---|---|---|---|
| Pipeline with drop-off | Row chart, shared left baseline, drop-off annotated | Funnel chart | A funnel highlights survivors; the question is losses. Metabase's funnel cannot be recoloured or broken out by woreda, the taper distorts sharp drop-offs, and comparing two funnels needs a shared baseline it does not have. No funnel shows median days in stage. |
| Six-status distribution | Table at tier 1; 100% stacked bar collapsed to 4 segments above | Six-segment stack; pie; donut | Four stacks is the practical ceiling. Six adjacent segments cannot hold the 3:1 non-text ratio WCAG 1.4.11 requires. Order semantically, never by size, or segments swap places across time. |
| Category → outcome flow | Pivot table, single-hue scale, counts visible | Sankey | Up to 40 ribbons; unreadable at 5 inches; needs hover, the interaction least available to these users; breaks on circular flows; and hides zero cells, which here are the finding. |
| Per-youth referral chain | Inline SVG timeline (LifeLines pattern) + event table | Any BI chart | A detail view of one record, not a BI question. Hand-built SVG is a few KB, renders on any Android browser, and prints. Metabase has no timeline visualisation. |
| Rates on small denominators | League table sorted by n, three-state verdict from funnel-plot limits | Sorted bar chart of rates; RAG grid; the funnel plot itself | Ranking on unstable rates sorts by luck and is politically irreversible once published. A funnel plot is correct but needs training to read, so compute the logic in SQL and render the verdict as a word plus a symbol. |
| Retention over time | Cohort heatmap + disposition stacked bar | Survival curve as primary; a single retention % | A heatmap separates decay-with-tenure (read across) from cohort-over-cohort improvement (read down); one curve conflates them. A single percentage hides voluntary exits. |
| Three-woreda comparison | Three bars, or small multiples | Choropleth map | Area is a confound: the largest woreda dominates visually regardless of its data. At n = 3 there is no spatial pattern to find, and a map is the most expensive card on the page: GeoJSON plus tiles, on 3G. Revisit past ~15–20 woredas, and prefer proportional symbols even then. |
| Progress vs target | One line chart, one axis, both series in counts | Dual axis; gauge; speedometer | Dual axes invent correlations that are not in the data, and tested poorly on both accuracy and speed. Gauges spend a whole card on one number with no comparative context. |

Also banned outright, anywhere in this system: 3D charts, rainbow palettes, more than four categorical hues, truncated bar-chart axes, a number on every data point, red/green as the only encoding, and dashed gridlines.

## 8. Cross-cutting rules

### 8.1 Small numbers

Implemented once in `rpt.suppression_band()`, `rpt.safe_rate()` and `rpt.rate_label()`. **A Metabase question that computes a percentage inline is a review-blocking defect.**

| Band | Condition | Display |
|---|---|---|
| Report | denominator ≥ 30 | Rate, plus n/N, plus 95% Wilson CI where it matters |
| Provisional | 10 ≤ denominator < 30 | Rate with a persistent visible marker (`52%*`) and a footnote. Never used in a comparison or a ranking. |
| Suppress | denominator < 10 | `too few to assess (n=8)`. The **numerator is withheld**: publishing `- (5/8)` suppresses the percentage while handing over the counts it was computed from. |

Plus:

- **Never show a percentage without its denominator.** Anywhere. `rate_label()` enforces this by construction.
- **Apply the rule to every disaggregation.** Female × PWD × Woreda C is exactly where denominators collapse and exactly what donors ask for.
- **Suppression must be non-complementary.** Suppress one cell in a row and publish the total, and the hidden value is recoverable by subtraction. Suppress a second cell or suppress the total. *Not yet automated: see OQ-6.*
- **A funnel verdict is a comparison.** `rpt.funnel_verdict()` returns `too_few` for anything outside the report band, not merely below the suppression floor, because the provisional band is defined as never compared or ranked.
- **Distinguish 0 from no data.** Zero placements from 40 referrals and no report submitted are different findings.
- **Whole percentage points only.** 49%, never 48.81%.

### 8.2 Maturation

`rpt.is_mature()` and `rpt.matures_on()`. Every checkpoint metric filters its denominator on this. A youth placed 20 days ago is not a 30-day retention failure; a referral raised three days before period end is not an unclosed loop. Omitting the guard collapses rates at every period boundary and teaches staff to stop raising referrals late in the quarter.

### 8.3 Attribution, settled before Metabase work starts

- A referral counts once, against the receiving partner named on that referral record. The rule goes in the card subtitle.
- Deduplicate at person level within a reporting period. `mv_referral_outcome_matrix` carries both `n_referrals` and `n_youth` for this; use `n_youth` for any person-level indicator.
- Every outcome carries `verification_source`. Report the verified subset as the headline; a self-reported placement rate is an aspiration.
- Label placements **gross**. They are not "jobs created".

### 8.4 Colour and accessibility

**Two palettes, and they must not be mixed.**

*Series colours* carry identity in charts. Machine-validated, not chosen by eye:

- Categorical: `#12836B` `#D08A0A` `#B0442A` `#7A4CA8`
- Sequential: `#84BEAC` → `#5FA890` → `#3D9078` → `#1E7D66` → `#0C5346`

Both pass lightness-band, chroma-floor, colour-vision-deficiency separation, normal-vision separation and surface-legibility checks. `#D08A0A` sits below 3:1 against the page, which is why **every gold mark carries a visible label** rather than relying on fill alone.

*Status colours* carry state, are reserved, and come from the design system (`design_handoff_youth_employment/README.md`). They always ship with a shape and a word:

| State | Fill | Text |
|---|---|---|
| Active / on track | `#1C7A5B` | `#0B4A38` |
| Completed | `#0F4F3C` | `#0B4A38` |
| Pending / waiting | `#C98A15` | `#7A5308` |
| Stalled / replaced | `#A84B2A` | `#8A3A1E` |
| Failed | `#B3261E` | `#8C1D18` |

A status colour used as "series 4" is a defect, and so is a series colour used to mean "failed". The referral stack timeline uses the status palette; every chart uses the series palette.

- **Never colour alone.** Every status pairs colour with a word and a geometric mark.
- **Every chart has a table twin.** WCAG 1.1.1, and the fallback when SVG fails on a low-end browser.
- **Adjacent segments need a 3:1 ratio** against each other (WCAG 1.4.11 non-text).
- **Sunlight:** no shadows, no gradients, no light-grey secondary text, 2px minimum strokes, weight 600+ on any number that matters.
- Design tokens are authoritative in `../design_handoff_youth_employment/README.md`.

### 8.5 Bandwidth

Chart type barely affects page weight. What matters:

1. **Card count**: each is a query round-trip. Cap at 6, hard cap 9.
2. **Result-set size**: aggregate in SQL, never return detail rows to a card. Table cards limited to 20–50 rows with a "view all" link.
3. **Query latency**: pre-aggregate (`sql/003`) and enable Metabase caching. Pre-warm dashboards via the Metabase API at 06:00 EAT so the first supervisor of the day gets cache hits.
4. **External requests**: this is where maps lose badly.

## 9. Open questions for sign-off

Working defaults are implemented. Do not silently resolve these; leave `# TODO(open-question)` comments pointing here.

| ID | Question | Working default |
|---|---|---|
| **OQ-1** | `referrals_referral.service_start_date` does not exist in Dev Spec §4.6, but pipeline stage 6 ("service attended") needs it: and that transition is where the largest loss occurs. Add the field? | Column added in `sql/000`. Until Django defines it, stage 6 renders as "not yet instrumented", never as zero. |
| **OQ-2** | `verification_source` is not in Dev Spec §4.6. Without it, every outcome rate is self-reported. | Column added; enum `self_reported` / `provider_confirmed` / `employer_confirmed` / `document_verified`. |
| **OQ-3** | `placements_placement.is_subsidised` is not in Dev Spec §4.7. PSNP public works placements must be excluded from the employment numerator or the placement rate is really a programme-participation rate. | Column added, defaults false. |
| **OQ-4** | `psnp_client_category` (PW / PDS / TDS) is not in Dev Spec §4.1 but is a required donor disaggregation. | Column added, nullable. |
| **OQ-5** | `Placement.exit_reason` is free text in Dev Spec §4.7. `mv_placement_disposition` cannot classify voluntary vs involuntary exits reliably from free text. | Enum proposed: `better_job`, `further_training`, `voluntary_progression`, `dismissed`, `contract_ended`, `business_closed`, `health`, `relocation`, `other`. |
| **OQ-6** | Secondary suppression is not implemented. A single suppressed cell in a published row is recoverable by subtraction. | Consuming questions must suppress a second cell. Automate before external publication. |
| **OQ-7** | Do Complementary Service referrals count toward the two-referral parallel cap (Dev Spec §6.3)? | Outside the cap (Dev Spec §6.3). `mv_parallel_load` counts both so the decision can be evidenced. |
| **OQ-8** | Are the suppression thresholds (30 / 10) accepted, or does the World Bank task team prescribe its own? | 30 / 10 in `rpt.reporting_parameters`. |
| **OQ-9** | Retention anchor for donor reporting: placement date or programme exit? | Both computed: `rpt.mv_cohort_retention` carries an `anchor` column with `placement` and `exit` rows, and the exit rows exclude subsidised placements. PM-5 filters to `placement`, ME-4 shows both. The task team confirms which anchor is the reportable one. |
| **OQ-10** | Does Metabase render Amharic (Ge'ez) and Afaan Oromo correctly in card titles, axis labels and exports? | Unverified. **Check before committing to Metabase, not after**: commercial BI tooling constraining multilingual support is a documented failure mode in this class of project. |
| **OQ-11** | Add `Youth.settlement_type` (rural / peri-urban / urban)? Both the ILO and World Bank frameworks require rural/urban disaggregation and nothing in the model supports it. | Cut omitted from `mv_disaggregation` with a `TODO(open-question)`. Do not proxy it from woreda. |
| **OQ-12** | Make `Case.case_manager_id` nullable? WS-2 counts unassigned youth, which Dev Spec §4.2 currently forbids as a state. | Nullable in the fixture schema. If it stays non-nullable, WS-2 uses the registered-with-no-case proxy instead. |
| **OQ-13** | What is the abandonment threshold, after which a referral with no partner answer auto-fails with `PARTNER_NON_RESPONSIVE`? Dev Spec §6.2 has no exit from Pending Confirmation except partner action or manual cancellation, so an unanswered referral sits forever, holds a slot against the §6.3 parallel cap, and drags the loop-closure denominator down permanently. | None set. Add `referral_abandonment_days` to `rpt.reporting_parameters` beside `confirmation_threshold_days`. Observed in the build: 117 referrals stranded past 477 days. |
| **OQ-14** | Is `caseload_ceiling` (default 120) the right number, and where is the flag surfaced? Observed caseloads of 127 to 141 all exceed it and nothing flags them. | Parameter exists and is unused. Either raise it or render the flag on WS-1. |
| **OQ-15** | Is `outcome_type` recorded independently, or derived from `referral_category`? Dev Spec §5.3 lists which outcomes apply to which category, and that table is easy to mistake for a derivation rule. It is a validation constraint, not a formula. | Must be recorded by the person verifying the outcome. Observed in the build: all 86 categorised outcomes sat exactly on the §5.3 mapping with zero crossovers, which makes PM-3 a restatement of the lookup table. Add a check that a completed referral carries an `outcome_type` **and** a `verification_source`. |
| **OQ-16** | What share of `outcome_type = 'Other'` is acceptable before the outcome breakdown is unreportable? | Observed 56 percent. Propose flagging above 10 percent on PM-8 as a data-quality alert. Dev Spec §5.3 already requires a free-text note with Other; enforce it. |

## 10. Definition of done

Per tier, in addition to the Dev Spec §10.1 criteria.

**Reporting layer**
- [ ] `sql/900` passes in CI as a blocking gate
- [ ] `metabase_ro` cannot `SELECT` from any table in `public`: asserted by a test
- [ ] No column named `full_name`, `phone_number` or `national_or_kebele_id` exists in the `rpt` schema except staff names on `mv_caseload_status` and `mv_alert_load`
- [ ] `rpt.refresh_operational()` completes in under 60 s at pilot scale (1,000 youth, 3,000 referrals)
- [ ] Every `mv_*` has a unique index, so `CONCURRENTLY` refresh works and dashboards never block

**Every dashboard**
- [ ] Six cards or fewer, nine absolute maximum
- [ ] Every rate carries its denominator on screen
- [ ] Every rate passes through `rpt.rate_label()` or `rpt.safe_rate()`: no inline percentage arithmetic in any Metabase question
- [ ] Every chart has a table view
- [ ] Every status encoding pairs colour with a word and a mark
- [ ] The as-of timestamp from `rpt.v_freshness` renders in the header
- [ ] Loads in under 5 s on a throttled 3G profile with cold cache

**Tier-specific**
- [ ] Tier 1: `django/CASE_MANAGER_DASHBOARD.md` §8 in full
- [ ] Tier 2: the 07:00 email subscription renders server-side and arrives
- [ ] Tier 3: PM-4 is sorted by `n_closed`, and a test asserts the saved question's ORDER BY
- [ ] Tier 3: PM-5 renders censored cells hatched with a maturation date, verified with a fixture whose newest cohort is 10 days old
- [ ] Tier 4: refreshes monthly, not nightly, and the as-of date appears in every export

## 11. Sources behind the design decisions

Frameworks: World Bank Jobs M&E Toolkit (2017); WBG Scorecard FY24–30; PSNP 5 / SEASN (P172479); Ethiopia UPSNJP (P169943); ILO *Guide on Measuring Decent Jobs for Youth* Notes 2 and 3; ILO School-to-Work Transition Survey; Ethiopian Statistical Service 2013 EFY Labour Force Survey; ILO Ethiopia Youth Country Brief (2023).

Referral measurement: CMS50 "Closing the Referral Loop"; MEASURE Evaluation completed-referrals indicator; NNSI *Health and Human Services Referral Systems Measurement and Evaluation Playbook*.

Dashboard design: Primero CPIMS; DHIS2 tracker analytics and the tracker-to-aggregate pattern; CommCare UCR; Salesforce Nonprofit Cloud Case Management; Stephen Few, *Information Dashboard Design*; UK Government Analysis Function data visualisation guidance; Spiegelhalter (2005) funnel plots; NCHS Data Presentation Standards for Proportions; WCAG 2.1; HCIL LifeLines.
