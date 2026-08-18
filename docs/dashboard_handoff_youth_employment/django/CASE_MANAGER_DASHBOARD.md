# Case Manager Dashboard: Django Implementation Contract

Tier 1 of four. Companion to `../README.md`. For Claude Code.

New to this bundle? Read `../START_HERE.md` first.

## Paste This to Claude Code

```
Build the case manager dashboard described in
dashboard_handoff_youth_employment/django/CASE_MANAGER_DASHBOARD.md.
Read that file and ../README.md §2 and §7 fully first.

This is a Django view in the case management app, NOT a Metabase dashboard and
NOT a DRF endpoint consumed by a chart library. Server-render it. Write tests for
the RBAC boundary and for each work-queue queryset before wiring the template.
The acceptance criteria at the end of this file are the definition of done.
```

---

## 1. Why this is not in Metabase

Three reasons, all of which are blockers rather than preferences:

1. **PII boundary.** This screen shows named youth and masked phone numbers. The `rpt` schema deliberately contains no PII (see `sql/003_materialized_views.sql`), and Metabase's row-and-column security is a paid-tier feature. A per-youth access boundary belongs in the Django ORM, enforced in the queryset and covered by tests.
2. **Latency.** Each Metabase card is an independent query round-trip. Six cards on 3G is several seconds before anything paints. This page must be one request, server-rendered, under 100 KB.
3. **Action affordance.** Every element on this screen is a link into a filtered list of named youth or straight into a case. A BI tool renders numbers; this screen renders work.

## 2. What must NOT appear on this screen

This is a hard list. A pull request that adds any of these should be rejected.

- **No percentages.** A caseload of 80–200 youth is far below the n = 30 stability floor once disaggregated, and a rate is not an action.
- **No charts.** The Primero, CommCare and Salesforce operational views converge on counts and lists; charts start at the supervisor tier.
- **No comparison with other case managers.** That is the supervisor's view. Putting it here creates cream-skimming pressure with no compensating information value.
- **No trend lines, no cohort analysis, no woreda comparison.**
- **Nothing that cannot be clicked to produce a list of named youth.** If a number does not link somewhere, delete it.

The one exception to "no charts" is the referral stack timeline (§6), which is a detail view of a single record, not an aggregate.

## 3. Route and view

```
GET  /dashboard/                       CaseManagerDashboardView    (this file)
GET  /dashboard/queue/<queue_slug>/    WorkQueueListView           (drill-down)
GET  /cases/<case_id>/                 CaseDetailView              (Sprint 1; add §6 to it)
```

Server-rendered Django templates. No client-side data fetching on the dashboard route.

```python
# apps/dashboard/views.py

class CaseManagerDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/case_manager.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        return {
            **super().get_context_data(**kwargs),
            "needs_action":      queues.needs_action(user)[:6],
            "needs_action_count": queues.needs_action(user).count(),
            "awaiting_partner":  queues.awaiting_partner(user)[:6],
            "awaiting_partner_count": queues.awaiting_partner(user).count(),
            "at_risk":           queues.at_risk(user)[:6],
            "at_risk_count":     queues.at_risk(user).count(),
            "caseload_by_status": queues.caseload_by_status(user),
            "week_counts":       queues.week_counts(user),
            "outcomes_verified_this_month": queues.outcomes_verified(user),
        }
```

Every list is sliced to 6 in the template with a "View all N →" link. `count()` is a separate cheap query against a partial index; do not `len()` a sliced queryset and do not fetch 200 rows to display 6.

## 4. RBAC scoping: the security boundary

**One helper, used by every queue. No queue may build its own filter.**

`Role` is the `TextChoices` class on the `User` model (Dev Spec §4.12, §7). All ten roles must have an explicit branch; a role that falls through to the default is denied, which is the safe outcome but a silent one.

```python
# apps/dashboard/scoping.py

def scoped_cases(user) -> QuerySet[Case]:
    """
    The single entry point for CASE visibility. DEV_SPEC §7.

    Every queryset in this module starts here. A queryset that filters
    Case.objects directly is a security defect, not a style problem.
    """
    qs = Case.objects.select_related("youth", "case_manager")

    if user.role == Role.YOUTH_CASE_MANAGER:
        return qs.filter(case_manager=user)

    if user.role in (Role.OUTREACH_WORKER, Role.WOREDA_SUPERVISOR):
        return qs.filter(woreda__in=user.woreda_assignment)

    # "View, linked cases only": each linked through a different entity.
    if user.role == Role.TRAINER:
        return qs.filter(
            trainingenrolment__training_provider_id=user.partner_id).distinct()
    if user.role == Role.EMPLOYER_LIAISON:
        return qs.filter(placement__isnull=False,
                         referrals__receiving_partner_id=user.partner_id).distinct()
    if user.role == Role.ENTERPRISE_DEV_OFFICER:
        return qs.filter(enterprise__isnull=False,
                         referrals__receiving_partner_id=user.partner_id).distinct()
    if user.role == Role.REFERRAL_PARTNER_STAFF:
        return qs.filter(referrals__receiving_partner_id=user.partner_id).distinct()

    if user.role in (Role.PROGRAMME_MANAGER, Role.ME_STAFF):
        return qs

    if user.role == Role.SYSTEM_ADMINISTRATOR:
        return qs.none()      # configuration only, no case content by default

    return qs.none()          # deny by default


def scoped_referrals(user) -> QuerySet[Referral]:
    """
    The single entry point for REFERRAL visibility.

    Case-level scoping is NOT sufficient here. Dev Spec §7 restricts partner
    staff to "own institution's referrals only", and a youth can hold referrals
    to several partners at once. Filtering only on
    `case__in=scoped_cases(user)` would show Partner A every referral on a
    shared youth, including the ones sent to Partner B.
    """
    qs = Referral.objects.filter(case__in=scoped_cases(user))

    if user.role in (Role.REFERRAL_PARTNER_STAFF, Role.EMPLOYER_LIAISON,
                     Role.ENTERPRISE_DEV_OFFICER, Role.TRAINER):
        qs = qs.filter(receiving_partner_id=user.partner_id)

    return qs.select_related("case__youth", "receiving_partner")
```

Required tests: these are the ones that matter most in the whole handoff:

| Test | Assertion |
|---|---|
| `test_case_manager_sees_only_own_caseload` | A case manager querying the dashboard cannot see a case assigned to another case manager, in any queue |
| `test_partner_staff_sees_only_own_institution_referrals` | Partner staff at Partner A cannot see a referral sent to Partner B, **even for a youth they also serve**. This is the test `scoped_referrals()` exists for; case-level scoping alone fails it. |
| `test_linked_only_roles_scoped` | Trainer, employer liaison and enterprise development officer each see only their linked cases, not their whole woreda |
| `test_supervisor_scoped_to_woreda` | A supervisor for Adama cannot see a Bishoftu case |
| `test_system_admin_sees_no_case_content` | Returns empty, not everything |
| `test_unknown_role_denied` | New roles default to deny, never to allow |
| `test_no_queue_bypasses_scoping` | AST walk over `queues.py`: every `<Model>.objects` expression must have `scoped_cases(` or `scoped_referrals(` somewhere in the same statement. A plain grep cannot do this: the reference implementations below legitimately use `Alert.objects` and `Referral.objects` *with* the scoping call applied |

## 5. The six cards

Card IDs are defined here and nowhere else; the prototype's tab 1 cards carry matching `data-card` attributes.

### CM-1: Needs action today

Open alerts assigned to me, past threshold or due today, **sorted by days overdue descending**.

```python
from django.db.models import DurationField, ExpressionWrapper, F, IntegerField, Value
from django.db.models.functions import ExtractDay

def needs_action(user):
    today = timezone.localdate()
    return (
        Alert.objects
        .filter(case__in=scoped_cases(user), status=Alert.Status.OPEN, assigned_to=user)
        # Two steps, deliberately. `Value(today) - F("triggered_date")` compiles to
        # an interval on Postgres, so subtracting the integer threshold_days
        # directly raises "operator does not exist: interval - integer".
        # ExtractDay converts to an integer first.
        .annotate(elapsed=ExpressionWrapper(
            Value(today) - F("triggered_date"), output_field=DurationField()))
        .annotate(days_overdue=ExpressionWrapper(
            ExtractDay("elapsed") - F("threshold_days"), output_field=IntegerField()))
        .filter(days_overdue__gte=0)
        .select_related("case", "case__youth")
        .order_by("-days_overdue")
    )
```

Display: youth name + ID, one-line reason derived from `alert_type`, and a badge showing `Nd overdue` or `Due today`. `threshold_days` is per alert type and configurable: never hard-code 7.

### CM-2: Referrals awaiting partner response

The Primero pattern: track **acceptance state**, not volume sent. "Referrals made" is the textbook vanity metric for a referral platform and must not appear anywhere on this screen.

```python
def awaiting_partner(user):
    today = timezone.localdate()
    return (
        scoped_referrals(user)                      # NOT case__in=scoped_cases()
        .filter(confirmation_status=Referral.Confirmation.PENDING)
        .annotate(waited=ExpressionWrapper(
            Value(today) - F("initiated_date"), output_field=DurationField()))
        .annotate(days_waiting=ExpressionWrapper(
            ExtractDay("waited"), output_field=IntegerField()))
        .order_by("-days_waiting")
    )
```

Hits `ix_referral_pending_by_initiator` (a partial index, `sql/004_indexes.sql`).

Badge thresholds come from `rpt.reporting_parameters.confirmation_threshold_days`: green under threshold, gold at threshold, red beyond it. Colour is paired with the day count as text: never colour alone.

### CM-3: My caseload by status

A **five-row table in semantic (workflow) order**, not a chart and not sorted by size. A status distribution ordered by count becomes unreadable across time because rows swap places.

```python
def caseload_by_status(user):
    """One query. STATUS_ORDER is workflow order and includes zero-count rows."""
    STATUS_ORDER = ["active", "referral_pending", "stalled", "placed", "exited"]
    today = timezone.localdate()

    # Max(Now() - F(date_field)) raises FieldError: Now() is a DateTimeField and
    # last_activity_date is a DateField, so the expression has mixed types with
    # no declared output_field. Use the local date as a Value instead.
    rows = (
        scoped_cases(user)
        .values("case_status")
        .annotate(
            n=Count("pk"),
            oldest=Max(ExpressionWrapper(
                Value(today) - F("last_activity_date"), output_field=DurationField())),
        )
    )
    by_status = {r["case_status"]: r for r in rows}
    return [
        {
            "status": s,
            "n": by_status.get(s, {}).get("n", 0),
            "oldest": by_status.get(s, {}).get("oldest"),
            "url": reverse("dashboard:queue", kwargs={"queue_slug": s}),
        }
        for s in STATUS_ORDER
    ]
```

### CM-4: Youth at risk of dropping out

An **exception list**, which is the highest-value and most under-used widget type in this class of system. The Salesforce "Contacts with 3 Consecutive Absences" pattern.

Union of four conditions, each with its own reason string:

| Condition | Source |
|---|---|
| No contact in 30+ days | `Case.last_activity_date` older than `stall_threshold_days` |
| 3 consecutive training absences | `TrainingEnrolment.attendance_rate` or an absence log |
| Left a placement, `exit_reason` blank | `Placement.exit_date IS NOT NULL AND exit_reason IS NULL` |
| 4+ failed contact attempts | `FollowUp.contact_outcome IN ('no_response','unreachable')` |

Implement as **one** `UNION` query over four `.values()` subqueries so the card costs a single round-trip (see the query budget in §8), then map to a dataclass. Deduplicate a youth matching several conditions, keeping the highest severity:

```python
@dataclass(frozen=True)
class RiskItem:
    case_id: UUID
    youth_name: str
    reason: str        # human-readable, e.g. "3 consecutive training absences"
    severity: int      # sort key, higher first
    badge: str         # e.g. "45d", "3×"
```

### CM-5: Week counts

Two plain numbers: cases opened this week, cases closed this week. Workload sense, nothing more.

### CM-6: Outcomes verified this month

Count of referrals moved to `completed` with `outcome_verified_by` set, this calendar month. The one positively-framed number on the page.

## 6. Referral stack timeline: the case detail component

Belongs on `CaseDetailView`, not on the dashboard. Extends `../../REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`, which specifies the React component and the `ReferralTimelineItem` data contract. This section adds the **server-rendered SVG fallback** and the rendering rules the prototype demonstrates. The `ReferralLane` dataclass in `referral_stack_svg.py` mirrors that contract field for field; if one changes, change both.

Reference implementation: `referral_stack_svg.py` in this directory.

Rules, all visible in `screenshots/06-referral-stack-timeline.png`:

- **One lane per referral**, ordered by `initiated_date`. Newest at the bottom. Pick one direction and never change it.
- **Intervals are bars, point events are marks.** Pending is a gold bar, active a green bar, and the end-cap encodes the terminal state.
- **Encode state redundantly.** Completed is a filled triangle end-cap; failed is a hollow dashed bar with a diamond end-cap. Never colour alone (WCAG 1.4.1).
- **Draw the gaps.** The valuable insight in a referral stack is dead time. A failure and its replacement are joined by a dotted connector labelled with the day count. "15 days dead time" is the finding; the bars alone hide it.
- **Fixed vertical scale, horizontal scroll** for long histories. Do not compress 18 months into 320 px.
- **Always ship the chronological event table beneath it.** That table is the WCAG 1.1.1 text alternative, the fallback when the SVG fails on a low-end browser, and the thing case managers actually read.

Render server-side as inline SVG. This is a rectangle-and-circle layout problem, not a charting problem: a few KB on the wire, one HTTP request, identical rendering on any Android browser, and it prints.

## 7. Front-end constraints

From `../../design_handoff_youth_employment/README.md`, which is authoritative for design tokens and component specs:

- Mobile-first, 360 px is the common case. Touch targets 48 px minimum.
- No icon fonts, no chart libraries. Inline SVG stroke paths, 24×24 viewBox, `stroke-width: 1.7`.
- Bars are CSS `width: N%` on a div. Do not add a charting dependency for this screen.
- Phone numbers masked by default with an explicit Reveal action.
- Queued / syncing / failed-to-sync states are part of the UI, not a toast.
- Sunlight legibility: no shadows, no gradients, no light-grey secondary text, weight 600+ on any number that matters.

## 8. Acceptance criteria

Definition of done for this tier.

**Correctness**

- [ ] Every card returns the same numbers as an equivalent hand-written SQL query against the same fixture data.
- [ ] `needs_action` sorts by days overdue descending, and uses each alert's own `threshold_days`, not a constant.
- [ ] `awaiting_partner` sorts by age descending and shows no count of referrals sent.
- [ ] `caseload_by_status` returns rows in workflow order, including zero-count statuses.
- [ ] The at-risk list deduplicates a youth who matches more than one condition, keeping the highest severity.

**Security**

- [ ] All six RBAC tests in §4 pass.
- [ ] Every `<Model>.objects` expression in `apps/dashboard/queues.py` has `scoped_cases(` or `scoped_referrals(` in the same statement. Enforce with an **AST walk**, not a grep: the reference implementations legitimately name `Alert.objects` and `Referral.objects` with scoping applied, so a substring ban would reject correct code.
- [ ] Phone numbers render masked by default in every list.

**Performance**

- [ ] The dashboard route issues **≤ 12 queries** total (assert with `assertNumQueries`), which requires `at_risk` to be a single `UNION` query and `week_counts` a single aggregate. Budget: needs_action 1 + its count 1 + awaiting_partner 1 + its count 1 + at_risk 1 + its count 1 + caseload_by_status 1 + week_counts 1 + outcomes_verified 1 + session/user 2 = 11.
- [ ] No N+1: every list uses `select_related` on `case`, `case__youth`, and `receiving_partner` where displayed.
- [ ] Rendered HTML is **under 100 KB** for a 200-case caseload.
- [ ] p95 response time under 800 ms with 1,000 youth and 3,000 referrals seeded.

**Accessibility**

- [ ] Every status pairs a colour with a word and a geometric mark.
- [ ] The referral stack SVG has an `aria-label` and is followed by the event table.
- [ ] Contrast: 4.5:1 for text, 3:1 for graphical objects, verified with an automated check in CI.
- [ ] The page is fully usable with CSS disabled (it is a set of lists and tables).

**Guard rails**

- [ ] No percentage appears anywhere on the rendered page. Assert it: a test that renders the dashboard with fixture data and fails if the HTML contains `%` outside a CSS width attribute.
- [ ] No chart library is imported by the dashboard bundle.
