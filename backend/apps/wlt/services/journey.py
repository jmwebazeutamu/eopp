"""One woman's path through the programme: registered → verified → in a group → linked.

The four stages already existed as services that refuse things. What did not
exist was anywhere to *read* them: a facilitator could be told "she is not
eligible" by `add_member` at the moment she tried, and had no screen that said
so beforehand, or said which of the four conditions was the problem.

This assembles the same refusals into a forward-looking answer, using the gate
vocabulary the readiness card already renders — every condition carries its
actual value beside its threshold, and "not measurable yet" is a third state
distinct from "not met". Nothing here decides anything: it reports what the
services would do, and every write still goes through them.

Two things it deliberately does not do:

- **It never merges the two programmes' stages.** A youth-side case, a referral
  and a placement are a different pipeline with a different subject, and a woman
  who is in both is two records by design (handoff decision D1). This is the
  group-side journey only.
- **It never claims a stage is reachable when only a person can decide.**
  Verification is a woreda officer's judgement, so a pending profile reads
  `waiting`, not `ready`. A screen that showed a facilitator a button for
  somebody else's decision would be lying about who is accountable.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _
from django.db.models import Sum

from apps.youth.models import PsnpStatus, Sex

from apps.users.models import Role
from ..models import (
    CLA,
    ChildType,
    GroupMembership,
    EntryType,
    GroupStatus,
    LinkageStatus,
    Phase,
    ServiceLinkage,
    LoanStatus,
    ServiceLinkageType,
    StructuralMembership,
    VerificationStatus,
)
from .gates import Condition

# The four stages, in order. `LINKED` is last because it is the only one that is
# not a precondition for anything else — a group works whether or not it ever
# reaches a bank.
REGISTERED = "REGISTERED"
VERIFIED = "VERIFIED"
GROUPED = "GROUPED"
LINKED = "LINKED"

# What a stage can be. Four, not two, for the same reason the readiness card has
# three states per condition: "blocked" and "waiting for somebody else" call for
# different actions from the person reading the screen, and "ready" is the only
# one that should carry a button.
DONE = "done"
READY = "ready"
WAITING = "waiting"
BLOCKED = "blocked"


@dataclass
class Stage:
    code: str
    label: str
    state: str
    conditions: list = field(default_factory=list)
    # Free-form, for the screen to link somewhere: a group id, a linkage id.
    detail: dict = field(default_factory=dict)

    @property
    def unmet(self):
        return [condition for condition in self.conditions if not condition.met]

    def as_dict(self):
        return {
            "code": self.code,
            "label": str(self.label),
            "state": self.state,
            "conditions": [condition.as_dict() for condition in self.conditions],
            "detail": self.detail,
        }


def _yes_no(value):
    return _("Yes") if value else _("No")


def _boolean_condition(code, label, actual):
    """A condition whose threshold is simply "yes"."""
    return Condition(
        code=code, label=str(label), threshold=str(_("Yes")), actual=str(_yes_no(actual)), met=bool(actual)
    )


def _value_condition(code, label, *, threshold, actual, met):
    return Condition(code=code, label=str(label), threshold=str(threshold), actual=str(actual), met=met)


def _state_from(conditions, *, done, waiting=False):
    if done:
        return DONE
    if any(not condition.met for condition in conditions):
        return BLOCKED
    return WAITING if waiting else READY


# ---------------------------------------------------------------------------
# The stages
# ---------------------------------------------------------------------------


def _registered(profile):
    """Reached by definition — but the two things the record needs are named.

    Consent is not a formality here. §9 of the youth spec makes it the basis for
    holding the record at all, and a profile whose person has none is a record
    that should not exist rather than one waiting for a next step.
    """
    person = profile.person
    conditions = [
        _boolean_condition("consent_recorded", _("Consent recorded"), person.consent_given),
        _boolean_condition("place_recorded", _("PSNP kebele recorded"), profile.psnp_kebele_id is not None),
    ]
    return Stage(
        code=REGISTERED,
        label=_("Registered"),
        state=DONE if all(c.met for c in conditions) else BLOCKED,
        conditions=conditions,
        detail={
            "person": str(person.pk),
            "full_name": person.full_name,
            "enrolment_route": profile.enrolment_route,
            "enrolment_route_display": str(profile.get_enrolment_route_display()),
            "registered_on": person.registration_date.isoformat() if person.registration_date else None,
        },
    )


def _verified(profile):
    """The control that stops the exception route becoming the main route (D5).

    A woman imported from the ELS extract arrives verified; one a facilitator
    added arrives pending, and only a woreda officer moves her. That is why a
    pending profile is `waiting` and not `ready` — there is no button here for
    the person most likely to be reading the screen.
    """
    status = profile.verification_status
    condition = _value_condition(
        "verification",
        _("Verified against PSNP records"),
        threshold=VerificationStatus.VERIFIED.label,
        actual=profile.get_verification_status_display(),
        met=status == VerificationStatus.VERIFIED,
    )
    if status == VerificationStatus.VERIFIED:
        state = DONE
    elif status == VerificationStatus.REJECTED:
        state = BLOCKED
    else:
        state = WAITING
    return Stage(
        code=VERIFIED,
        label=_("Verified"),
        state=state,
        conditions=[condition],
        detail={
            "status": status,
            "note": profile.verification_note,
            "verified_on": profile.verified_on.isoformat() if profile.verified_on else None,
        },
    )


def _grouped(profile):
    """Every refusal `formation.add_member` can raise, stated in advance.

    This is the stage the whole module turns on, and before this existed the only
    way to discover which of the six conditions blocked a woman was to try to add
    her and read the error.
    """
    person = profile.person
    open_membership = (
        GroupMembership.objects.filter(person=person, exited_on__isnull=True)
        .select_related("group", "group__kebele", "group__facilitator")
        .first()
    )

    conditions = [
        _value_condition(
            "verified",
            _("Verified"),
            threshold=VerificationStatus.VERIFIED.label,
            actual=profile.get_verification_status_display(),
            met=profile.verification_status == VerificationStatus.VERIFIED,
        ),
        _boolean_condition("female", _("Female"), person.sex == Sex.FEMALE),
        _boolean_condition("els_completed", _("ELS package completed"), profile.els_completed_on is not None),
        _boolean_condition("els_grant", _("ELS grant received"), profile.els_grant_received_on is not None),
        _value_condition(
            "psnp",
            _("PSNP status"),
            threshold=_("On the caseload"),
            actual=person.get_psnp_status_display(),
            met=person.psnp_status != PsnpStatus.NOT_PSNP,
        ),
    ]

    return Stage(
        code=GROUPED,
        label=_("In a savings group"),
        state=_state_from(conditions, done=open_membership is not None),
        conditions=conditions,
        # Enough to answer "which group, and how is it doing?" without opening
        # the group screen. Her profile is where a facilitator lands from the
        # register, and a bare group *name* sent her somewhere else to find out
        # whether that group was even operating.
        detail=(
            {
                "group": str(open_membership.group_id),
                "group_name": open_membership.group.name,
                "group_status": open_membership.group.status,
                "group_status_display": str(open_membership.group.get_status_display()),
                "group_phase": open_membership.group.current_phase,
                "group_phase_display": str(open_membership.group.get_current_phase_display() or ""),
                "kebele": str(open_membership.group.kebele_id) if open_membership.group.kebele_id else None,
                "kebele_name": open_membership.group.kebele.name if open_membership.group.kebele_id else "",
                "facilitator_name": (
                    open_membership.group.facilitator.full_name if open_membership.group.facilitator_id else ""
                ),
                "members_current": open_membership.group.current_members.count(),
                "joined_on": open_membership.joined_on.isoformat(),
            }
            if open_membership is not None
            else {
                "kebele": str(profile.psnp_kebele_id) if profile.psnp_kebele_id else None,
                "kebele_name": profile.psnp_kebele.name if profile.psnp_kebele_id else "",
            }
        ),
    )


def _next_approval_role(linkage):
    if linkage.status != LinkageStatus.PENDING_APPROVAL:
        return None
    approval = linkage.approvals.filter(decision="").order_by("level").first()
    if approval is None:
        return None
    try:
        return str(Role(approval.required_role).label)
    except ValueError:
        return approval.required_role.replace("_", " ").title()


def _linked(profile):
    """Service or structural linkage — the two ways a group reaches beyond itself.

    A service linkage is a bank account, a market offtake agreement, a credit
    facility. A structural one is the group joining a Cluster Level Association.
    Both are gated, and the gates belong to the *group*, not to her: a woman does
    not clear a phase threshold on her own. So the conditions here are her
    group's, and the stage reads `blocked` while she has no group at all.
    """
    person = profile.person
    membership = GroupMembership.objects.filter(person=person, exited_on__isnull=True).select_related("group").first()

    if membership is None:
        return Stage(
            code=LINKED,
            label=_("Linked to a service or a structure"),
            state=BLOCKED,
            # Deliberately not "In a savings group": that is the label of the
            # stage directly above this one, which is `ready` for a woman who
            # has none. Two rows with identical text, one green and one blocked,
            # read as a contradiction — and it was reported as one.
            conditions=[_boolean_condition("in_group", _("Must already be in a savings group"), False)],
            detail={},
        )

    group = membership.group

    # **Every** linkage her group holds, not only the live ones. `BLOCKED` is a
    # first-class state and the model says so — it names exactly what the group
    # still has to reach — and `DISTRESSED`, `DEFAULTED` and `PENDING_APPROVAL`
    # are each something somebody has to act on. Filtering to ACTIVE/APPROVED
    # meant her profile showed nothing at all for a group whose bank linkage was
    # sitting blocked, which reads as "no linkages" rather than "one, stuck".
    #
    # The stage's own `done` still keys off the live ones: a blocked linkage is
    # a thing to work on, not evidence that she is linked.
    all_linkages = (
        ServiceLinkage.objects.filter(subject_group=group)
        .select_related("linkage_type", "provider")
        .order_by("-opened_on")
    )
    active_linkages = ServiceLinkage.objects.filter(
        subject_group=group, status__in=[LinkageStatus.ACTIVE, LinkageStatus.APPROVED]
    )
    structural = StructuralMembership.objects.filter(
        child_type=ChildType.GROUP, child_id=group.pk, exited_on__isnull=True
    ).first()
    parent_cla = CLA.objects.filter(pk=structural.parent_id).first() if structural is not None else None

    conditions = [
        _boolean_condition("in_group", _("Must already be in a savings group"), True),
        _value_condition(
            "group_operating",
            _("Group operating"),
            threshold=GroupStatus.ACTIVE.label,
            actual=group.get_status_display(),
            met=group.status in GroupStatus.operating(),
        ),
    ]

    # Every linkage type her group could reach, with the phase it needs. This is
    # the "all the gates" part: a facilitator asking why the bank option is not
    # offered gets "needs Phase 2, group is at Phase 1" rather than an absence.
    available, blocked_types = [], []
    for linkage_type in ServiceLinkageType.objects.active():
        if not linkage_type.permits("GROUP"):
            continue
        row = {
            "code": linkage_type.code,
            "label": linkage_type.label,
            "min_phase": linkage_type.min_phase,
            "min_phase_display": str(Phase(linkage_type.min_phase).label) if linkage_type.min_phase else "",
            "group_phase": group.current_phase,
            "group_phase_display": str(group.get_current_phase_display()) if group.current_phase else "",
        }
        if _phase_clears(group.current_phase, linkage_type.min_phase):
            available.append(row)
        else:
            blocked_types.append(row)

    return Stage(
        code=LINKED,
        label=_("Linked to a service or a structure"),
        state=_state_from(conditions, done=active_linkages.exists() or structural is not None),
        conditions=conditions,
        detail={
            "group": str(group.pk),
            "group_name": group.name,
            "service_linkages": [
                {
                    "id": str(linkage.pk),
                    "type_label": linkage.linkage_type.label,
                    "status": linkage.status,
                    "status_display": str(linkage.get_status_display()),
                    "provider_name": linkage.provider.partner_name if linkage.provider_id else None,
                    "opened_on": linkage.opened_on.isoformat() if linkage.opened_on else None,
                    "activated_on": linkage.activated_on.isoformat() if linkage.activated_on else None,
                    "next_approval_role_display": _next_approval_role(linkage),
                    # Whether this one is still live, so the screen can lead with
                    # the ones somebody has to do something about rather than
                    # sorting a facilitator's attention by date.
                    "is_live": linkage.status in LinkageStatus.open_statuses(),
                    "is_settled": linkage.status in LinkageStatus.terminal(),
                }
                for linkage in all_linkages
            ],
            "structural_membership": (
                {
                    "parent_type": structural.parent_type,
                    "parent": str(structural.parent_id),
                    "parent_name": parent_cla.name if parent_cla is not None else "",
                    "joined_on": structural.joined_on.isoformat(),
                }
                if structural is not None
                else None
            ),
            "available_types": available,
            "blocked_types": blocked_types,
        },
    )


def _phase_clears(current, minimum):
    """No phase recorded clears only a type that asks for none."""
    if not minimum:
        return True
    if not current:
        return False
    return Phase.at_least(current, minimum)


# ---------------------------------------------------------------------------
# The journey
# ---------------------------------------------------------------------------


def _financials(profile):
    """The member's passbook totals across every group she has belonged to."""
    person = profile.person
    savings = (
        person.wlt_ledger_entries.filter(entry_type=EntryType.SAVINGS).aggregate(total=Sum("amount_etb"))["total"] or 0
    )
    loans = list(person.wlt_loans.filter(disbursed_on__isnull=False).prefetch_related("repayments"))
    disbursed = sum((loan.principal_etb for loan in loans), 0)
    principal_repaid = sum((loan.principal_repaid_etb for loan in loans), 0)
    charges_repaid = sum(
        (repayment.charge_etb for loan in loans for repayment in loan.repayments.all()),
        0,
    )
    outstanding = sum(
        (loan.outstanding_principal_etb for loan in loans if loan.status in LoanStatus.owing()),
        0,
    )
    return {
        "savings_etb": str(savings),
        "loans_disbursed_etb": str(disbursed),
        "repayments_etb": str(principal_repaid + charges_repaid),
        "principal_repaid_etb": str(principal_repaid),
        "charges_repaid_etb": str(charges_repaid),
        "outstanding_principal_etb": str(outstanding),
        "loans_disbursed_count": len(loans),
    }


def build(profile):
    """The four stages for one woman, in order.

    `next_action` names the first stage that is not done, which is the single
    thing the screen leads with. When everything is done it is null rather than
    a cheerful message — the absence is the finding.
    """
    stages = [_registered(profile), _verified(profile), _grouped(profile), _linked(profile)]
    outstanding = [stage for stage in stages if stage.state != DONE]
    return {
        "person": str(profile.person_id),
        "profile": str(profile.pk),
        "full_name": profile.person.full_name,
        "stages": [stage.as_dict() for stage in stages],
        "stages_done": len(stages) - len(outstanding),
        "stages_total": len(stages),
        "financials": _financials(profile),
        "next_action": outstanding[0].as_dict() if outstanding else None,
    }
