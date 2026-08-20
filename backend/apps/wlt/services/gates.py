"""Gate evaluation — handoff README §8, `django/MODELS.md`.

One service evaluates every gate in the module, phase transitions and linkage
screening alike. Two rules govern the whole of it:

1. **Always return the actual value next to the threshold.** "Attendance 74%
   (need 80%)" changes what a facilitator does next week. A red dot does not.
   Every `Condition` carries both, and the screens render both.
2. **Snapshot the whole result into the decision record.** Not `passed`, not a
   summary — the conditions, the thresholds, the actuals and the policy version.
   It is the audit defence when somebody questions a graduation two years later.

Thresholds resolve through the policy layer, never from constants, so a mid-pilot
revision by FSCO is an admin edit. And gates are evaluated **twice** — at
screening and again at approval — because a subject can drift below threshold
while an approval sits in a queue, and approving against stale numbers is how bad
credit linkages happen.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from .. import policy
from ..models import (
    ChildType,
    Group,
    GroupStatus,
    LinkageStatus,
    LinkageSubjectType,
    OfficeRole,
    ParentType,
    Phase,
    StructuralMembership,
)
from . import indicators as indicator_service


@dataclass
class Condition:
    """One thing a subject must satisfy, with what it actually has."""

    code: str
    label: str
    threshold: Any
    actual: Any
    met: bool
    # "%" or "" — carried so the screen can render "74% (need 80%)" rather than
    # "74 (need 80)". The handoff's own example of the rule this card exists for
    # has the sign in it, and a bare number invites the wrong reading of a rate.
    unit: str = ""
    # Set when the condition cannot be measured rather than failed — no closed
    # meetings yet, no bylaw recorded. A facilitator reading "not measurable"
    # does something different from one reading "below threshold", and a screen
    # that showed both as red would tell her the wrong thing.
    unmeasurable: bool = False

    def as_dict(self):
        """JSON-safe, because this lands in a `JSONField` snapshot.

        Both conversions are load-bearing. A `Decimal` would serialise as a
        float and lose the exactness a birr figure needs; a lazy translation
        proxy raises outright, which is how the first credit-facility gate — the
        only one whose threshold is a phrase rather than a number — took the
        whole proposal path down.
        """
        return {key: _json_safe(value) for key, value in asdict(self).items()}


@dataclass
class GateResult:
    gate_set: str
    passed: bool
    conditions: list = field(default_factory=list)
    policy_version_id: str = ""
    computed_at: str = ""

    @property
    def unmet(self):
        return [condition for condition in self.conditions if not condition.met]

    @property
    def block_reasons(self):
        """What the subject still needs, in the words the blocked screen shows."""
        return [f"{condition.label}: {condition.actual} (need {condition.threshold})" for condition in self.unmet]

    def as_snapshot(self):
        return {
            "gate_set": self.gate_set,
            "passed": self.passed,
            "policy_version_id": self.policy_version_id,
            "computed_at": self.computed_at,
            "conditions": [condition.as_dict() for condition in self.conditions],
        }


def _json_safe(value):
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _condition(code, label, threshold, actual, met, unmeasurable=False, unit=""):
    return Condition(
        code=code,
        label=label,
        threshold=threshold,
        actual=actual,
        met=met,
        unmeasurable=unmeasurable,
        unit=unit,
    )


def _at_least(code, label, threshold, actual, unit=""):
    """`actual >= threshold`, treating an absent actual as unmeasurable.

    None means the indicator has no denominator yet — no closed meetings, no
    bylaw. It is not a failure and it is not a pass; it is a gate that cannot be
    judged, and it blocks while saying so.
    """
    if actual is None:
        return _condition(code, label, threshold, None, met=False, unmeasurable=True, unit=unit)
    return _condition(code, label, threshold, actual, met=actual >= threshold, unit=unit)


def _at_most(code, label, threshold, actual, unit=""):
    if actual is None:
        return _condition(code, label, threshold, None, met=False, unmeasurable=True, unit=unit)
    return _condition(code, label, threshold, actual, met=actual <= threshold, unit=unit)


def evaluate(subject, gate_set, as_of=None, policy_set=None, policy_version=None):
    """`evaluate(subject, gate_set, as_of) -> GateResult`, the §8 contract."""
    as_of = as_of or timezone.localdate()
    location = getattr(subject, "kebele", None) or getattr(subject, "woreda", None)
    policy_set = policy_set or policy.PolicySet(location=location, on_date=as_of)
    policy_version = policy_version or policy.current_version(policy_set)

    builder = _GATE_SETS.get(gate_set)
    if builder is None:
        raise ValueError(f"unknown gate set {gate_set!r}")

    conditions = builder(subject, as_of, policy_set)
    return GateResult(
        gate_set=gate_set,
        passed=all(condition.met for condition in conditions),
        conditions=conditions,
        policy_version_id=str(policy_version.pk),
        computed_at=timezone.now().isoformat(),
    )


# ---------------------------------------------------------------------------
# Phase gates — DEFINITIONS.md §2
# ---------------------------------------------------------------------------


def _forming_to_p1(group, as_of, policy_set):
    """What activation requires. Checked by `services.formation.activate`."""
    bylaw = group.current_bylaw
    size = group.current_members.count()
    hard_min = policy_set.get_int("group.size.hard_min", 15)
    hard_max = policy_set.get_int("group.size.hard_max", 25)
    offices = {
        role: group.office_holders.filter(role=role, to_date__isnull=True).exists() for role in OfficeRole.values
    }
    from ..models import MeetingStatus

    first_closed = group.meetings.filter(status=MeetingStatus.CLOSED).exists()

    return [
        _condition("bylaws_recorded", _("Bylaws recorded"), True, bylaw is not None, met=bylaw is not None),
        _condition(
            "roster_size",
            _("Roster size"),
            f"{hard_min}–{hard_max}",
            size,
            met=hard_min <= size <= hard_max,
        ),
        _condition(
            "officers_elected",
            _("Chair, secretary and treasurer elected"),
            3,
            sum(1 for held in offices.values() if held),
            met=all(offices.values()),
        ),
        _condition(
            "first_savings_meeting",
            _("First savings meeting closed with a balanced till"),
            True,
            first_closed,
            met=first_closed,
        ),
    ]


def _p1_to_p2(group, as_of, policy_set):
    figures = indicator_service.compute(group, as_of=as_of, policy_set=policy_set)
    return [
        _at_least(
            "meeting_adherence",
            _("Meeting adherence"),
            policy_set.get_int("gate.p1.meeting_adherence_pct", 90),
            figures.meeting_adherence_pct,
            unit="%",
        ),
        _at_least(
            "attendance",
            _("Attendance"),
            policy_set.get_int("gate.p1.attendance_pct", 80),
            figures.attendance_pct,
            unit="%",
        ),
        _at_least(
            "savings_compliance",
            _("Savings compliance"),
            policy_set.get_int("gate.p1.savings_compliance_pct", 80),
            figures.savings_compliance_pct,
            unit="%",
        ),
        _at_least(
            "savings_meetings",
            _("Savings meetings held"),
            policy_set.get_int("gate.p1.min_savings_meetings", 10),
            figures.meetings_held_total,
        ),
        _at_most(
            "par30",
            _("Portfolio at risk over 30 days"),
            policy_set.get_int("gate.p1.max_par30_pct", 0),
            figures.par30_pct,
            unit="%",
        ),
    ]


def _p2_to_p3(group, as_of, policy_set):
    figures = indicator_service.compute(group, as_of=as_of, policy_set=policy_set)
    social_required = policy_set.get_bool("gate.p2.social_fund_required", True)
    conditions = [
        _at_least(
            "fund_adequacy",
            _("Fund adequacy, in weeks of contribution"),
            policy_set.get_int("gate.p2.fund_adequacy_weeks", 12),
            figures.fund_weeks_of_contribution,
        ),
        _at_least(
            "completed_cycles",
            _("Completed loan cycles"),
            policy_set.get_int("gate.p2.completed_loan_cycles", 1),
            figures.completed_loan_cycles,
        ),
        _at_most(
            "par30",
            _("Portfolio at risk over 30 days"),
            policy_set.get_int("gate.p2.max_par30_pct", 0),
            figures.par30_pct,
            unit="%",
        ),
        _at_least(
            "weeks_since_p1",
            _("Weeks since entering Phase 1"),
            policy_set.get_int("gate.p2.min_weeks_since_p1", 52),
            figures.weeks_since_phase_entry,
        ),
    ]
    if social_required:
        # Open question Q9: the social fund appears in the handbook's Phase 2
        # indicators and is defined nowhere. Modelled as a ledger entry type
        # with no rules, so this asks only whether the group has one — which is
        # the most the handbook supports and is honest about being so.
        conditions.append(
            _condition(
                "social_fund",
                _("Social fund active"),
                True,
                figures.social_fund_active,
                met=figures.social_fund_active,
            )
        )
    return conditions


# ---------------------------------------------------------------------------
# Structural formation gates
# ---------------------------------------------------------------------------


def _cla_formation(location, as_of, policy_set):
    """Evaluated against a **kebele**, not a group: forming a CLA is something
    eight groups do together."""
    threshold = policy_set.get_int("gate.cla.min_groups", 8)
    eligible = Group.objects.cla_eligible().filter(kebele=location).count()
    return [_at_least("eligible_groups", _("P2-eligible SHGs in this kebele"), threshold, eligible)]


def _federation_formation(location, as_of, policy_set):
    """Evaluated against a woreda. Not reachable in the pre-pilot (D8).

    Phase 4 needs 10 CLAs of 8 to 12 SHGs — 80 to 120 groups in one woreda —
    and the largest regional allocation is 80 groups across a whole region. The
    gate exists so the arithmetic is visible rather than assumed.
    """
    from ..models import CLA

    threshold = policy_set.get_int("gate.federation.min_clas", 10)
    min_months = policy_set.get_int("gate.federation.min_cla_months", 12)
    clas = CLA.objects.filter(kebele__parent=location, status="ACTIVE")
    mature = [cla for cla in clas if (as_of - cla.formed_on).days >= min_months * 30]
    return [
        _at_least("cla_count", _("CLAs in this woreda"), threshold, clas.count()),
        _at_least("cla_maturity", _("CLAs operating long enough"), threshold, len(mature)),
    ]


# ---------------------------------------------------------------------------
# Linkage gates — README §7, workflows W4 to W7
# ---------------------------------------------------------------------------


def _subject_phase(subject):
    return getattr(subject, "current_phase", None) or None


def _min_phase_condition(subject, minimum):
    actual = _subject_phase(subject)
    if minimum is None:
        return None
    met = Phase.at_least(actual, minimum) if actual else False
    return _condition(
        "min_phase",
        _("Phase reached"),
        Phase.short_label(minimum),
        Phase.short_label(actual) if actual else _("not yet in a phase"),
        met=met,
    )


def _savings_account(subject, as_of, policy_set):
    """W4. Low risk, and it should happen early.

    Deliberately not gated behind Phase 3: a locked cash box in a pastoralist
    kebele is a worse custodian than a bank account, and early *savings* linkage
    is not what the Ethiopian evidence warns about — early *credit* linkage is.
    """
    conditions = []
    minimum = policy_set.get("gate.savings_account.min_phase", "P2")
    phase_condition = _min_phase_condition(subject, minimum)
    if phase_condition:
        conditions.append(phase_condition)

    if isinstance(subject, Group):
        officers = subject.office_holders.filter(to_date__isnull=True).values_list("role", flat=True)
        conditions.append(
            _condition(
                "three_officers", _("Three officers on record"), 3, len(set(officers)), met=len(set(officers)) >= 3
            )
        )
        bylaw = subject.current_bylaw
        signatories = bool(bylaw and bylaw.clauses_local_language)
        conditions.append(
            _condition(
                "signatory_bylaw",
                _("Signatory rule recorded in the bylaws"),
                True,
                signatories,
                met=signatories,
            )
        )
    return conditions


def _market_offtake(subject, as_of, policy_set):
    """W6. Lower ceremony, higher volume, no debt risk."""
    conditions = []
    phase_condition = _min_phase_condition(subject, policy_set.get("gate.market_offtake.min_phase", "P2"))
    if phase_condition:
        conditions.append(phase_condition)
    if isinstance(subject, Group):
        active = subject.status in GroupStatus.operating()
        conditions.append(_condition("subject_active", _("Group is operating"), True, active, met=active))
    return conditions


def _cooperative_membership(subject, as_of, policy_set):
    conditions = []
    phase_condition = _min_phase_condition(subject, "P3")
    if phase_condition:
        conditions.append(phase_condition)
    return conditions


def _credit_facility(subject, as_of, policy_set):
    """W5. High risk, so the friction is the point.

    Six conditions and a four-level chain. Group subjects are blocked outright
    in the pilot, which is a policy flag rather than a hardcoded type check, so
    FSCO can lift it without a deploy — and lifting it is a decision somebody
    signs, not a side effect.
    """
    conditions = []

    allow_group = policy_set.get_bool("gate.credit.allow_group_subject", False)
    is_group = isinstance(subject, Group)
    conditions.append(
        _condition(
            "subject_type",
            _("Subject may hold external credit"),
            _("CLA or federation") if not allow_group else _("any subject"),
            LinkageSubjectType.GROUP.label if is_group else type(subject).__name__,
            met=allow_group or not is_group,
        )
    )

    phase_condition = _min_phase_condition(subject, policy_set.get("gate.credit.min_phase", "P4"))
    if phase_condition:
        conditions.append(phase_condition)

    savings_months = policy_set.get_int("gate.credit.savings_account_months", 12)
    savings = (
        subject.linkages.filter(linkage_type__code="savings_account", status=LinkageStatus.ACTIVE)
        .order_by("activated_on")
        .first()
        if hasattr(subject, "linkages")
        else None
    )
    months_held = ((as_of - savings.activated_on).days // 30) if savings and savings.activated_on else 0
    conditions.append(
        _at_least("savings_account_age", _("Months holding a savings account"), savings_months, months_held)
    )

    member_groups = _member_groups(subject)
    min_cycles = policy_set.get_int("gate.credit.min_completed_cycles", 2)
    worst_cycles = min(
        (indicator_service._completed_cycles(group) for group in member_groups),
        default=0,
    )
    conditions.append(_at_least("member_cycles", _("Completed cycles in every member SHG"), min_cycles, worst_cycles))

    worst_par = Decimal("0.0")
    for group in member_groups:
        figures = indicator_service.compute(group, as_of=as_of, policy_set=policy_set)
        if figures.par30_pct is not None:
            worst_par = max(worst_par, figures.par30_pct)
    conditions.append(_at_most("aggregate_par30", _("Highest PAR30 across member SHGs"), 0, worst_par, unit="%"))

    return conditions


def _member_groups(subject):
    """The SHGs underneath a CLA or federation, or the group itself."""
    if isinstance(subject, Group):
        return [subject]
    from ..models import CLA

    if isinstance(subject, CLA):
        return list(subject.member_groups)

    cla_ids = StructuralMembership.objects.filter(
        parent_type=ParentType.FEDERATION,
        parent_id=subject.pk,
        child_type=ChildType.CLA,
        exited_on__isnull=True,
    ).values_list("child_id", flat=True)
    group_ids = StructuralMembership.objects.filter(
        parent_type=ParentType.CLA,
        parent_id__in=list(cla_ids),
        child_type=ChildType.GROUP,
        exited_on__isnull=True,
    ).values_list("child_id", flat=True)
    return list(Group.objects.filter(pk__in=list(group_ids)))


def _service_referral(subject, as_of, policy_set):
    """W7, the thinnest workflow: no gates beyond an active subject."""
    active = getattr(subject, "status", None) in GroupStatus.operating()
    return [_condition("subject_active", _("Subject is operating"), True, active, met=active)]


_GATE_SETS = {
    "forming_to_p1": _forming_to_p1,
    "p1_to_p2": _p1_to_p2,
    "p2_to_p3": _p2_to_p3,
    "cla_formation": _cla_formation,
    "federation_formation": _federation_formation,
    "savings_account": _savings_account,
    "market_offtake": _market_offtake,
    "cooperative_membership": _cooperative_membership,
    "cooperative_registration": _cooperative_membership,
    "credit_facility": _credit_facility,
    "service_referral": _service_referral,
}


def gate_set_for_phase(from_phase):
    """Which gate set governs leaving `from_phase`."""
    return {
        None: "forming_to_p1",
        "": "forming_to_p1",
        Phase.P1: "p1_to_p2",
        Phase.P2: "p2_to_p3",
    }.get(from_phase)
