"""Policy parameter resolution — handoff decision D6, backlog S4.1.

Resolution order is **most specific place first**, then global, each filtered by
effective date: a kebele override beats a woreda override beats a zone override
beats a region override beats the global value.

The handoff states the order as "woreda override, then region, then global". The
walk here is the same rule generalised over the four-level hierarchy this
platform already models, so a kebele-level pilot variation is expressible
without a schema change and nothing else about the order moves.

No gate logic anywhere reads a constant. A parameter change is an admin edit,
not a deployment.
"""

from django.utils import timezone

from .models import PolicyParameter, PolicyVersion

# Defaults of last resort, used only when the parameter table has no row at all
# — a fresh database before `seed_wlt_policy`, or a key added in code before it
# is seeded. They are the same values `seed_wlt_policy` writes, and they are
# deliberately here rather than sprinkled through the gate functions: one place
# to read the module's whole rule set, and one place a missing seed shows up.
#
# Several are marked NEEDS FSCO in the seed. A default is not an agreement.
FALLBACKS = {
    # Group composition. The handbook says 15-20, 15-25 and 20 in three places.
    "group.size.hard_min": 15,
    "group.size.hard_max": 25,
    "group.size.warn_min": 18,
    "group.size.warn_max": 22,
    # Formation lifecycle
    "formation.draft_expiry_days": 60,
    "formation.constituted_expiry_days": 30,
    "formation.event_expiry_days": 90,
    # Phase 1 exit gate
    "gate.p1.meeting_adherence_pct": 90,
    "gate.p1.attendance_pct": 80,
    "gate.p1.savings_compliance_pct": 80,
    "gate.p1.min_savings_meetings": 10,
    "gate.p1.max_par30_pct": 0,
    # Phase 2 exit gate
    "gate.p2.fund_adequacy_weeks": 12,
    "gate.p2.completed_loan_cycles": 1,
    "gate.p2.max_par30_pct": 0,
    "gate.p2.social_fund_required": True,
    "gate.p2.min_weeks_since_p1": 52,
    # Structural formation
    "gate.cla.min_groups": 8,
    "gate.cla.delegates_per_group": 2,
    "gate.federation.min_clas": 10,
    "gate.federation.min_cla_months": 12,
    # Credit facility — deliberately restrictive
    "gate.credit.min_phase": "P4",
    "gate.credit.allow_group_subject": False,
    "gate.credit.savings_account_months": 12,
    "gate.credit.min_completed_cycles": 2,
    "gate.credit.max_leverage_ratio": 1.0,
    "gate.credit.par30_clean_months": 6,
    # Savings account and market linkage
    "gate.savings_account.min_phase": "P2",
    "gate.market_offtake.min_phase": "P2",
    # Risk and dormancy
    "risk.dormant_cadence_multiple": 3,
    "risk.dormant_floor_days": 60,
    "risk.attendance_floor_pct": 60,
    "risk.par30_ceiling_pct": 20,
    # Loan discipline
    "loan.default_days_past_due": 30,
    "loan.delinquent_days_past_due": 1,
    "loan.min_meetings_before_lending": 10,
    # Indicator windows
    "indicator.rolling_meetings": 12,
    "indicator.member_compliance_pct": 90,
    # Enrolment controls
    "enrolment.allocation_warn_pct": 90,
    "enrolment.exception_route_alert_pct": 10,
    # Meeting content — handbook 3.6 asks for 15 to 30 minutes
    "meeting.social_minutes_min": 15,
}


def _location_chain(location):
    """The location and its ancestors, most specific first.

    Bounded by the hierarchy's four levels, so this is at most four queries and
    usually fewer — `parent` is already loaded when the caller selected it.
    """
    chain = []
    node = location
    while node is not None:
        chain.append(node)
        node = node.parent
    return chain


def resolve(key, location=None, on_date=None, default=None):
    """The value of `key` in force at `location` on `on_date`.

    `location` may be any level; the walk goes upward from it. Pass the group's
    kebele and the whole chain resolves.
    """
    on_date = on_date or timezone.localdate()

    rows = list(PolicyParameter.objects.in_force(on_date).filter(key=key).select_related("scope_location"))
    if not rows:
        return FALLBACKS.get(key, default)

    by_location = {}
    global_value = None
    for row in rows:
        if row.scope_location_id is None:
            # Several global rows for one key means somebody opened a new one
            # without closing the old. The later start wins, which is the same
            # rule the SQL helper uses.
            if global_value is None or row.effective_from > global_value[0]:
                global_value = (row.effective_from, row.value)
        else:
            current = by_location.get(row.scope_location_id)
            if current is None or row.effective_from > current[0]:
                by_location[row.scope_location_id] = (row.effective_from, row.value)

    if location is not None:
        for node in _location_chain(location):
            if node.pk in by_location:
                return by_location[node.pk][1]

    if global_value is not None:
        return global_value[1]
    return FALLBACKS.get(key, default)


def resolve_int(key, location=None, on_date=None, default=None):
    value = resolve(key, location, on_date, default)
    return None if value is None else int(value)


def resolve_decimal(key, location=None, on_date=None, default=None):
    from decimal import Decimal

    value = resolve(key, location, on_date, default)
    return None if value is None else Decimal(str(value))


def resolve_bool(key, location=None, on_date=None, default=None):
    value = resolve(key, location, on_date, default)
    return None if value is None else bool(value)


class PolicySet:
    """Every parameter for one place and date, read once.

    A gate evaluation asks for eight or ten thresholds. Resolving each one
    separately would be eight queries per group, and the readiness card renders
    a page of groups. This reads the table once and answers from memory, which
    also means every condition in one `GateResult` is measured against the same
    snapshot — a mid-evaluation admin edit cannot land between two conditions.
    """

    def __init__(self, location=None, on_date=None):
        self.location = location
        self.on_date = on_date or timezone.localdate()
        self._chain_ids = [node.pk for node in _location_chain(location)] if location is not None else []
        self._by_key = self._load()

    def _load(self):
        resolved = {}
        rows = PolicyParameter.objects.in_force(self.on_date).values(
            "key", "scope_location_id", "value", "effective_from"
        )
        best = {}
        for row in rows:
            scope = row["scope_location_id"]
            if scope is not None and scope not in self._chain_ids:
                continue
            # Lower rank is more specific; the global row ranks last. Within one
            # rank the later start wins, which is how a superseding row that
            # nobody closed still behaves predictably.
            rank = self._chain_ids.index(scope) if scope is not None else len(self._chain_ids)
            previous = best.get(row["key"])
            if previous is None or rank < previous[0] or (rank == previous[0] and row["effective_from"] > previous[1]):
                best[row["key"]] = (rank, row["effective_from"], row["value"])
        for key, (_rank, _from, value) in best.items():
            resolved[key] = value
        return resolved

    def get(self, key, default=None):
        if key in self._by_key:
            return self._by_key[key]
        return FALLBACKS.get(key, default)

    def get_int(self, key, default=None):
        value = self.get(key, default)
        return None if value is None else int(value)

    def get_decimal(self, key, default=None):
        from decimal import Decimal

        value = self.get(key, default)
        return None if value is None else Decimal(str(value))

    def get_bool(self, key, default=None):
        value = self.get(key, default)
        return None if value is None else bool(value)

    def as_dict(self):
        """The whole resolved set, for freezing into a decision record."""
        merged = dict(FALLBACKS)
        merged.update(self._by_key)
        return merged


def current_version(policy_set=None):
    """The `PolicyVersion` a decision taken now should reference.

    Reuses the latest version when the parameter set has not moved since, and
    mints a new one when it has. A version per decision would be honest and
    unreadable; a version per *change* is what makes "which rules applied in
    March" a question with a short answer.
    """
    policy_set = policy_set or PolicySet()
    parameters = policy_set.as_dict()

    latest = PolicyVersion.objects.order_by("-created_at").first()
    if latest is not None and latest.parameters == parameters:
        return latest

    return PolicyVersion.objects.create(label=timezone.localdate().isoformat(), parameters=parameters)
