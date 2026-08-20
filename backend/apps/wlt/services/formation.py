"""Group formation — handoff README §4, backlog stage 2.

Mobilisation → Draft → Constituted → Active. The split between a **hard block**
and a **soft warning** is the single most likely way to make this module unusable
in the field, so it is stated once, here, and nowhere else:

* Hard blocks are facts about eligibility and structure. A woman who is not
  programme-eligible, or is already in another group, cannot be added, and no
  reason overrides it.
* Soft warnings are the handbook's *preferences*. Group size 18 to 22, someone
  literate, someone with a phone, one kebele. Every one of them is overridable
  with a recorded reason, because the handbook is explicit that participation is
  voluntary and a facilitator standing in a kebele knows things this system does
  not.

Every override writes a `ValidationOverride` row. It is reviewed at woreda level,
and it also tells you which validation rules are wrong for the field: a rule
overridden in nine kebeles out of ten does not describe the programme.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .. import policy
from ..models import (
    BeneficiaryProfile,
    BylawVersion,
    EnrolmentAllocation,
    Group,
    GroupMembership,
    GroupStatus,
    MeetingStatus,
    OfficeHolder,
    OfficeRole,
    Phase,
    ValidationOverride,
    VerificationStatus,
)
from . import gates


class FormationError(ValidationError):
    """A hard block. Not overridable."""


class Finding:
    """One validation result: a block or a warning, with what to do about it."""

    def __init__(self, code, message, blocking, detail=None):
        self.code = code
        self.message = message
        self.blocking = blocking
        self.detail = detail or {}

    def as_dict(self):
        return {
            "code": self.code,
            "message": str(self.message),
            "blocking": self.blocking,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------


def candidate_pool(kebele):
    """Eligible, verified, unassigned women in a kebele (backlog S1.5).

    Carries literacy, device access and primary IGA, because a facilitator
    composing a workable group needs to see them — the "at least one member with
    a device" rule is unenforceable if the screen cannot show who has one.
    """
    return (
        BeneficiaryProfile.objects.programme_eligible()
        .verified()
        .unassigned()
        .filter(psnp_kebele=kebele)
        .select_related("person", "psnp_kebele")
    )


# ---------------------------------------------------------------------------
# Roster validation
# ---------------------------------------------------------------------------


def validate_roster(group, person_ids=None, policy_set=None):
    """Every finding for a draft roster, blocking and advisory alike."""
    policy_set = policy_set or policy.PolicySet(location=group.kebele)
    findings = []

    if person_ids is None:
        person_ids = list(group.current_members.values_list("person_id", flat=True))

    profiles = {
        profile.person_id: profile
        for profile in BeneficiaryProfile.objects.filter(person_id__in=person_ids).select_related("person")
    }

    # -- hard blocks, per member ------------------------------------------
    for person_id in person_ids:
        profile = profiles.get(person_id)
        if profile is None:
            findings.append(
                Finding(
                    "no_profile",
                    _("This woman has no WLT profile, so her eligibility cannot be established."),
                    blocking=True,
                    detail={"person_id": str(person_id)},
                )
            )
            continue
        if profile.verification_status != VerificationStatus.VERIFIED:
            # D5's control on the exception route. A facilitator addition starts
            # pending and cannot join a group until a woreda officer verifies
            # her against PSNP records; without this the exception path becomes
            # the main path.
            findings.append(
                Finding(
                    "not_verified",
                    _("%(name)s is not verified against PSNP records yet.") % {"name": profile.person.full_name},
                    blocking=True,
                    detail={"person_id": str(person_id)},
                )
            )
        elif not profile.is_programme_eligible:
            findings.append(
                Finding(
                    "not_eligible",
                    _("%(name)s does not meet the programme eligibility criteria.")
                    % {"name": profile.person.full_name},
                    blocking=True,
                    detail={"person_id": str(person_id)},
                )
            )

    already = GroupMembership.objects.filter(person_id__in=person_ids, exited_on__isnull=True).exclude(group=group)
    for membership in already.select_related("person", "group"):
        # A7 at the service layer, so the message points at the other group
        # rather than surfacing a unique-index violation. Whichever draft
        # constitutes first wins; the second is told which one to talk to.
        findings.append(
            Finding(
                "already_in_a_group",
                _("%(name)s is already a member of %(group)s.")
                % {"name": membership.person.full_name, "group": membership.group.name},
                blocking=True,
                detail={"person_id": str(membership.person_id), "group_id": str(membership.group_id)},
            )
        )

    # -- hard blocks, about the group -------------------------------------
    size = len(person_ids)
    hard_min = policy_set.get_int("group.size.hard_min", 15)
    hard_max = policy_set.get_int("group.size.hard_max", 25)
    if size < hard_min:
        findings.append(
            Finding(
                "below_minimum_size",
                _("A group needs at least %(min)s members; this one has %(count)s.") % {"min": hard_min, "count": size},
                blocking=True,
            )
        )
    if size > hard_max:
        findings.append(
            Finding(
                "above_maximum_size",
                _("A group may have at most %(max)s members; this one has %(count)s.")
                % {"max": hard_max, "count": size},
                blocking=True,
            )
        )

    # -- soft warnings -----------------------------------------------------
    warn_min = policy_set.get_int("group.size.warn_min", 18)
    warn_max = policy_set.get_int("group.size.warn_max", 22)
    if size and not (warn_min <= size <= warn_max):
        findings.append(
            Finding(
                "size_outside_preferred_range",
                _("The handbook prefers %(min)s to %(max)s members. This group has %(count)s.")
                % {"min": warn_min, "max": warn_max, "count": size},
                blocking=False,
            )
        )

    listed = [profiles[pid] for pid in person_ids if pid in profiles]
    if listed and not any(profile.literacy_level in {"BASIC", "FUNCTIONAL"} for profile in listed):
        findings.append(
            Finding(
                "no_literate_member",
                _("No member has basic literacy. The group will need help keeping its books."),
                blocking=False,
            )
        )
    if listed and not any(profile.has_device for profile in listed):
        findings.append(
            Finding(
                "no_device",
                _("No member has a mobile device, so this group cannot record its own meetings."),
                blocking=False,
            )
        )

    kebeles = {profile.psnp_kebele_id for profile in listed if profile.psnp_kebele_id}
    if len(kebeles) > 1:
        findings.append(
            Finding(
                "mixed_kebele",
                _("Members are drawn from more than one kebele, which makes weekly meetings harder to keep."),
                blocking=False,
            )
        )

    allocation = allocation_status(group.kebele)
    if allocation and allocation["pct_of_allocation"] is not None:
        warn_at = policy_set.get_int("enrolment.allocation_warn_pct", 90)
        if allocation["pct_of_allocation"] >= warn_at:
            findings.append(
                Finding(
                    "allocation_near_ceiling",
                    _("%(region)s is at %(pct)s%% of its pre-pilot allocation.")
                    % {"region": allocation["region"], "pct": allocation["pct_of_allocation"]},
                    blocking=False,
                    detail=allocation,
                )
            )

    return findings


def blocking_findings(findings):
    return [finding for finding in findings if finding.blocking]


# ---------------------------------------------------------------------------
# Allocation ceiling — README §3.5, backlog S1.4
# ---------------------------------------------------------------------------


def allocation_status(location):
    """Progress against the region's pre-pilot allocation.

    Warned at 90%; activation past the ceiling is blocked unless a region-level
    override is recorded with a reason. Allocations are policy data, editable
    without a deployment (assertion A31).
    """
    from apps.locations.models import LocationLevel

    node = location
    while node is not None and node.level != LocationLevel.REGION:
        node = node.parent
    if node is None:
        return None

    allocation = EnrolmentAllocation.objects.filter(location=node).order_by("-effective_from").first()
    if allocation is None:
        return None

    enrolled = GroupMembership.objects.filter(
        exited_on__isnull=True, group__kebele__parent__parent__parent=node
    ).count()
    pct = round(100 * enrolled / allocation.target_members) if allocation.target_members else None
    return {
        "region": node.name,
        "region_id": node.pk,
        "target_members": allocation.target_members,
        "target_groups": allocation.target_groups,
        "members_enrolled": enrolled,
        "pct_of_allocation": pct,
        "at_ceiling": enrolled >= allocation.target_members,
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def open_draft(*, name, kebele, facilitator, mobilisation_event=None, created_by=None, on_date=None):
    """Start a group. Nothing about it is real yet except the intention."""
    on_date = on_date or timezone.localdate()
    if mobilisation_event is not None and not mobilisation_event.endorsement_obtained:
        # A refused endorsement closes the mobilisation; it does not open a
        # draft. Recording the refusal is the point — a kebele that produced no
        # groups is programme learning (A30).
        raise FormationError(_("The community meeting did not endorse this group, so no group can be drafted."))

    return Group.objects.create(
        name=name,
        kebele=kebele,
        facilitator=facilitator,
        mobilisation_event=mobilisation_event,
        created_by=created_by or facilitator,
        status=GroupStatus.DRAFT,
        drafted_on=on_date,
    )


@transaction.atomic
def add_member(group, person, *, on_date=None, actor=None):
    """Add a woman to a draft or an active group.

    Her savings compliance counts from her join date, not the group's, which is
    what the dated membership range is for.
    """
    on_date = on_date or timezone.localdate()

    profile = BeneficiaryProfile.objects.filter(person=person).first()
    if profile is None:
        raise FormationError(_("This woman has no WLT profile, so her eligibility cannot be established."))
    if profile.verification_status != VerificationStatus.VERIFIED:
        raise FormationError(_("A woman awaiting verification cannot be added to a group."))
    if not profile.is_programme_eligible:
        raise FormationError(_("This woman does not meet the programme eligibility criteria."))

    existing = GroupMembership.objects.filter(person=person, exited_on__isnull=True).first()
    if existing is not None:
        raise FormationError(
            _("%(name)s is already a member of %(group)s.") % {"name": person.full_name, "group": existing.group.name}
        )

    return GroupMembership.objects.create(group=group, person=person, joined_on=on_date)


@transaction.atomic
def exit_member(membership, *, reason, on_date=None, note=""):
    """Close a membership. Blocked while she has an outstanding loan (A11).

    The block is a database trigger as well as this check, because the exit can
    also arrive through the admin and through the sync reconciler. Here it gets
    a sentence a facilitator can act on.
    """
    from ..models import Loan, LoanStatus

    on_date = on_date or timezone.localdate()
    outstanding = sum(
        loan.outstanding_principal_etb
        for loan in Loan.objects.filter(person=membership.person, group=membership.group, status__in=LoanStatus.owing())
    )
    if outstanding > 0:
        raise FormationError(
            _("%(name)s owes ETB %(amount)s. Settle it, write it off with approval, or transfer it before she exits.")
            % {"name": membership.person.full_name, "amount": outstanding}
        )

    membership.exited_on = on_date
    membership.exit_reason = reason
    membership.exit_note = note
    membership.save(update_fields=["exited_on", "exit_reason", "exit_note", "updated_at"])
    return membership


@transaction.atomic
def record_bylaws(group, *, effective_from=None, recorded_by=None, **fields):
    """Open a new bylaw version, closing the one in force.

    Never an edit. A group that raises its contribution in month 8 still has to
    be measured against the old figure for months 1 to 7 (A27, A28).
    """
    effective_from = effective_from or timezone.localdate()

    if not fields.get("service_charge_basis"):
        # Open question Q4. A flat 5% per loan and 5% per month on a three-month
        # loan differ by a factor of three, so the system must not pick one.
        raise FormationError(
            {"service_charge_basis": _("Choose how the service charge is calculated. There is no default.")}
        )

    current = group.current_bylaw
    version_no = 1
    if current is not None:
        if effective_from <= current.effective_from:
            raise FormationError(_("A new bylaw version must start after the one it supersedes."))
        current.effective_to = effective_from
        current.save(update_fields=["effective_to", "updated_at"])
        version_no = current.version_no + 1

    return BylawVersion.objects.create(
        group=group,
        version_no=version_no,
        effective_from=effective_from,
        recorded_by=recorded_by,
        **fields,
    )


@transaction.atomic
def elect_officer(group, *, person, role, from_date=None):
    """Open a term, closing the sitting officer's.

    Never an edit in place: "who was treasurer on the date of that disbursement"
    is a question that gets asked (A8).
    """
    from_date = from_date or timezone.localdate()

    if not group.memberships.filter(person=person, exited_on__isnull=True).exists():
        raise FormationError(_("Only a current member can hold office."))

    sitting = group.office_holders.filter(role=role, to_date__isnull=True).first()
    if sitting is not None:
        if sitting.person_id == person.pk:
            return sitting
        sitting.to_date = from_date
        sitting.save(update_fields=["to_date", "updated_at"])

    return OfficeHolder.objects.create(group=group, person=person, role=role, from_date=from_date)


@transaction.atomic
def record_override(group, *, rule_code, reason, actor=None):
    """Accept a soft warning, with the facilitator's reason on the record."""
    if not reason.strip():
        raise FormationError({"reason": _("Say why this warning is being overridden.")})
    return ValidationOverride.objects.create(group=group, rule_code=rule_code, reason=reason, overridden_by=actor)


@transaction.atomic
def constitute(group, *, on_date=None, overrides=None, actor=None):
    """Lock the roster. Later changes go through the membership flow.

    `overrides` is a mapping of rule code to reason. A soft warning with no
    reason is not overridden — it blocks, and the error names it.
    """
    on_date = on_date or timezone.localdate()
    overrides = overrides or {}

    if group.status != GroupStatus.DRAFT:
        raise FormationError(_("Only a draft can be constituted."))

    findings = validate_roster(group)
    blocking = blocking_findings(findings)
    if blocking:
        raise FormationError([finding.message for finding in blocking])

    unaddressed = [finding for finding in findings if not finding.blocking and finding.code not in overrides]
    if unaddressed:
        raise FormationError(
            [
                _("%(message)s Record a reason to go ahead anyway.") % {"message": finding.message}
                for finding in unaddressed
            ]
        )

    for rule_code, reason in overrides.items():
        record_override(group, rule_code=rule_code, reason=reason, actor=actor)

    if not group.has_treasurer:
        raise FormationError(_("Elect a treasurer before constituting the group."))
    for role in (OfficeRole.CHAIR, OfficeRole.SECRETARY):
        if not group.office_holders.filter(role=role, to_date__isnull=True).exists():
            raise FormationError(
                _("Elect a %(role)s before constituting the group.") % {"role": OfficeRole(role).label}
            )
    if group.current_bylaw is None:
        raise FormationError(_("Record the group's bylaws before constituting it."))

    group.status = GroupStatus.CONSTITUTED
    group.constituted_on = on_date
    group.save(update_fields=["status", "constituted_on", "updated_at"])
    return group


@transaction.atomic
def activate(group, *, on_date=None, allocation_override_reason="", actor=None):
    """A group becomes real when it has saved money.

    Activation requires a first savings meeting closed with a balanced till —
    the till check is the meeting's, not this one's, so a group cannot activate
    on a meeting that never reconciled.
    """
    on_date = on_date or timezone.localdate()

    if group.status != GroupStatus.CONSTITUTED:
        raise FormationError(_("Only a constituted group can be activated."))

    if not group.meetings.filter(status=MeetingStatus.CLOSED).exists():
        raise FormationError(_("Close the first savings meeting with a balanced till before activating."))

    allocation = allocation_status(group.kebele)
    if allocation and allocation["at_ceiling"] and not allocation_override_reason:
        raise FormationError(
            _(
                "%(region)s has reached its pre-pilot allocation of %(target)s women. "
                "A region-level override with a reason is needed to activate another group."
            )
            % {"region": allocation["region"], "target": allocation["target_members"]}
        )
    if allocation_override_reason:
        record_override(group, rule_code="allocation_ceiling", reason=allocation_override_reason, actor=actor)

    result = gates.evaluate(group, "forming_to_p1", as_of=on_date)
    if not result.passed:
        raise FormationError(result.block_reasons)

    group.status = GroupStatus.ACTIVE
    group.activated_on = on_date
    group.current_phase = Phase.P1
    group.phase_entered_on = on_date
    group.save(update_fields=["status", "activated_on", "current_phase", "phase_entered_on", "updated_at"])
    return group


# ---------------------------------------------------------------------------
# Attrition sweeps
# ---------------------------------------------------------------------------


def expire_stale_drafts(as_of=None):
    """Drafts nobody constituted, and constitutions nobody activated.

    Both are retained, never deleted: three abandoned constitutions in one
    kebele is a mobilisation problem, and it is invisible if only successes are
    stored. Members return to the candidate pool because their memberships close
    with them.
    """
    as_of = as_of or timezone.localdate()
    expired = 0

    draft_days = policy.resolve_int("formation.draft_expiry_days", default=60)
    for group in Group.objects.filter(status=GroupStatus.DRAFT, drafted_on__lt=as_of - timedelta(days=draft_days)):
        group.memberships.filter(exited_on__isnull=True).update(
            exited_on=as_of, exit_reason="WITHDREW", exit_note="Draft expired"
        )
        group.status = GroupStatus.ABANDONED
        group.closed_on = as_of
        group.closure_reason = str(_("Draft expired without being constituted."))
        group.save(update_fields=["status", "closed_on", "closure_reason", "updated_at"])
        expired += 1

    constituted_days = policy.resolve_int("formation.constituted_expiry_days", default=30)
    for group in Group.objects.filter(
        status=GroupStatus.CONSTITUTED, constituted_on__lt=as_of - timedelta(days=constituted_days)
    ):
        group.status = GroupStatus.ABANDONED
        group.closed_on = as_of
        group.closure_reason = str(_("Constituted but never held a first savings meeting."))
        group.save(update_fields=["status", "closed_on", "closure_reason", "updated_at"])
        expired += 1

    return expired
