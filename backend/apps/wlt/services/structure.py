"""CLA and federation formation — handoff README §7 (W1, W2, W3, W8), stage 8.

W1 is the hardest workflow in the module, and the reason is structural: forming a
CLA is a **many-to-one event**, not a per-record action. A facilitator opens one
event, selects the eligible SHGs in a kebele, and each of those SHGs then elects
two delegates at its own meeting. The event stays open until every selected group
has recorded its pair. Only then can it be submitted, and only then can a woreda
approve it — at which point the CLA is created, the structural memberships open,
the delegates activate and every member SHG moves to P3 under **one shared event
id**, so the promotion can be traced back to the decision that caused it.

Nothing here creates a `StructuralMembership` by direct write. That is the point
of D3: a group does not join a CLA, eight groups form one.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .. import policy
from ..models import (
    CLA,
    ChildType,
    Delegate,
    Federation,
    FormationCandidate,
    FormationEvent,
    FormationStatus,
    Group,
    ParentType,
    Phase,
    PhaseDirection,
    PhaseEvent,
    StructuralMembership,
)
from . import gates


class StructureError(ValidationError):
    """A refused structural operation."""


@transaction.atomic
def open_formation_event(*, target_type, geography, groups=None, actor=None, on_date=None):
    """Start a CLA (or federation) formation with its candidate list."""
    on_date = on_date or timezone.localdate()
    expiry_days = policy.resolve_int("formation.event_expiry_days", location=geography, default=90)

    event = FormationEvent.objects.create(
        target_type=target_type,
        geography=geography,
        status=FormationStatus.OPEN,
        opened_on=on_date,
        expires_on=on_date + timedelta(days=expiry_days),
    )
    child_type = ChildType.GROUP if target_type == ParentType.CLA else ChildType.CLA
    for child in groups or []:
        FormationCandidate.objects.create(formation_event=event, child_type=child_type, child_id=child.pk)
    return event


@transaction.atomic
def exclude_candidate(event, *, child, reason):
    """Drop a group from a formation, explicitly and with a reason.

    Visible on that group's own record afterwards. A group quietly removed from
    a CLA it was told it would join is how a facilitator loses a kebele's trust.
    """
    if not reason.strip():
        raise StructureError({"reason": _("Say why this group is being excluded.")})
    candidate = event.candidates.filter(child_id=child.pk).first()
    if candidate is None:
        raise StructureError(_("That group is not part of this formation."))
    candidate.included = False
    candidate.exclusion_reason = reason
    candidate.save(update_fields=["included", "exclusion_reason", "updated_at"])
    return candidate


@transaction.atomic
def record_delegates(event, *, group, people, elected_at_meeting=None, from_date=None):
    """A group's elected pair. Captured offline; submission is online only.

    Exactly the number the policy asks for — two, by default. Fewer is an
    incomplete election and the event stays open; more is refused by the
    database as well as here.
    """
    from_date = from_date or timezone.localdate()
    required = policy.resolve_int("gate.cla.delegates_per_group", location=group.kebele, default=2)

    if event.status not in {FormationStatus.OPEN, FormationStatus.RETURNED}:
        raise StructureError(_("This formation is no longer open for delegate elections."))
    if len(people) != required:
        raise StructureError(
            _("Each group elects %(required)s delegates; %(given)s were recorded.")
            % {"required": required, "given": len(people)}
        )
    for person in people:
        if not group.memberships.filter(person=person, exited_on__isnull=True).exists():
            raise StructureError(_("A delegate has to be a current member of the group."))

    # Held as pending elections on the candidate row until the formation is
    # approved: a delegate seat means nothing until the CLA exists, and creating
    # `Delegate` rows against a CLA that may never be formed would leave
    # orphans nobody closes.
    candidate = event.candidates.filter(child_id=group.pk).first()
    if candidate is None:
        raise StructureError(_("That group is not part of this formation."))
    event.gate_snapshot = event.gate_snapshot or {}
    elections = event.gate_snapshot.setdefault("delegates", {})
    elections[str(group.pk)] = {
        "people": [str(person.pk) for person in people],
        "meeting": str(elected_at_meeting.pk) if elected_at_meeting else None,
        "from_date": from_date.isoformat(),
    }
    event.save(update_fields=["gate_snapshot", "updated_at"])
    return elections[str(group.pk)]


def readiness(event):
    """Whether this formation can be submitted, and what it still needs."""
    included = event.candidates.filter(included=True)
    elections = (event.gate_snapshot or {}).get("delegates", {})
    missing = [candidate for candidate in included if str(candidate.child_id) not in elections]
    threshold_result = gates.evaluate(event.geography, f"{event.target_type.lower()}_formation")
    return {
        "candidates": included.count(),
        "delegates_recorded": len(elections),
        "awaiting_delegates": [str(candidate.child_id) for candidate in missing],
        "gate": threshold_result,
        "can_submit": not missing and threshold_result.passed,
    }


@transaction.atomic
def submit(event, *, actor):
    """Send the formation to the woreda. Online only.

    Delegate capture works offline because it happens in a kebele; submission
    and approval do not, because they are conversations with an office.
    """
    state = readiness(event)
    if state["awaiting_delegates"]:
        raise StructureError(
            _("%(count)s group(s) have not recorded their delegates yet.") % {"count": len(state["awaiting_delegates"])}
        )
    if not state["gate"].passed:
        raise StructureError(state["gate"].block_reasons)

    event.status = FormationStatus.SUBMITTED
    event.submitted_by = actor
    event.submitted_at = timezone.now()
    event.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
    return event


@transaction.atomic
def approve(event, *, actor, name, formed_on=None, constitution_ref="", meeting_cadence=""):
    """Create the body, open the memberships, seat the delegates, move the phases.

    All under one event id. Every group promoted here carries
    `formation_event` on its phase event, so "why did these eight groups all
    move to P3 on the same day" has an answer that is one row.

    The gate is re-evaluated: a group that dropped below threshold while the
    approval sat in the queue is flagged here rather than carried in silently.
    """
    formed_on = formed_on or timezone.localdate()

    if event.status != FormationStatus.SUBMITTED:
        raise StructureError(_("Only a submitted formation can be approved."))
    if actor is not None and event.submitted_by_id == getattr(actor, "pk", None):
        raise StructureError(_("The person who submitted a formation cannot also approve it."))

    state = readiness(event)
    if not state["gate"].passed:
        raise StructureError([_("This formation no longer meets its threshold.")] + state["gate"].block_reasons)

    included = list(event.candidates.filter(included=True))
    if event.target_type == ParentType.CLA:
        body = CLA.objects.create(
            name=name,
            kebele=event.geography,
            formed_on=formed_on,
            constitution_ref=constitution_ref,
            meeting_cadence=meeting_cadence,
        )
        child_type = ChildType.GROUP
    else:
        body = Federation.objects.create(
            name=name, woreda=event.geography, formed_on=formed_on, constitution_ref=constitution_ref
        )
        child_type = ChildType.CLA

    elections = (event.gate_snapshot or {}).get("delegates", {})
    for candidate in included:
        StructuralMembership.objects.create(
            parent_type=event.target_type,
            parent_id=body.pk,
            child_type=child_type,
            child_id=candidate.child_id,
            joined_on=formed_on,
            formation_event=event,
        )
        if child_type != ChildType.GROUP:
            continue

        group = Group.objects.get(pk=candidate.child_id)
        election = elections.get(str(candidate.child_id), {})
        for person_id in election.get("people", []):
            Delegate.objects.create(
                cla=body,
                group=group,
                person_id=person_id,
                from_date=formed_on,
                elected_at_meeting_id=election.get("meeting"),
            )

        PhaseEvent.objects.create(
            group=group,
            from_phase=group.current_phase or "",
            to_phase=Phase.P3,
            direction=PhaseDirection.PROMOTION,
            submitted_by=event.submitted_by,
            submitted_at=event.submitted_at,
            decided_by=actor,
            decided_at=timezone.now(),
            policy_version=policy.current_version(),
            gate_snapshot=state["gate"].as_snapshot(),
            formation_event=event,
        )
        group.current_phase = Phase.P3
        group.phase_entered_on = formed_on
        group.save(update_fields=["current_phase", "phase_entered_on", "updated_at"])

    event.status = FormationStatus.APPROVED
    event.target_id = body.pk
    event.decided_by = actor
    event.decided_at = timezone.now()
    event.save(update_fields=["status", "target_id", "decided_by", "decided_at", "updated_at"])
    return body


@transaction.atomic
def return_event(event, *, actor, reason):
    if not reason.strip():
        raise StructureError({"reason": _("Say what has to change.")})
    event.status = FormationStatus.RETURNED
    event.return_reason = reason
    event.decided_by = actor
    event.decided_at = timezone.now()
    event.save(update_fields=["status", "return_reason", "decided_by", "decided_at", "updated_at"])
    return event


def expire_stale_events(as_of=None):
    """Formations nobody finished. Retained, not deleted."""
    as_of = as_of or timezone.localdate()
    return FormationEvent.objects.filter(
        status__in=[FormationStatus.OPEN, FormationStatus.RETURNED], expires_on__lt=as_of
    ).update(status=FormationStatus.EXPIRED)


# ---------------------------------------------------------------------------
# W2. Delegate rotation
# ---------------------------------------------------------------------------


@transaction.atomic
def rotate_delegate(*, outgoing, incoming_person, from_date=None, elected_at_meeting=None):
    """Close the old row, open a new one. Never an edit.

    "Who represented this group at the CLA meeting that approved the loan" is a
    question that gets asked, and a rotation that overwrote the row could not
    answer it.
    """
    from_date = from_date or timezone.localdate()
    outgoing.to_date = from_date
    outgoing.save(update_fields=["to_date", "updated_at"])
    return Delegate.objects.create(
        cla=outgoing.cla,
        group=outgoing.group,
        person=incoming_person,
        from_date=from_date,
        elected_at_meeting=elected_at_meeting,
    )


def delegates_past_rotation(as_of=None):
    """Delegates serving past their group's bylaw rotation period.

    Small, easy to forget, and it causes audit problems when it is missed.
    """
    as_of = as_of or timezone.localdate()
    overdue = []
    for delegate in Delegate.objects.filter(to_date__isnull=True).select_related("group"):
        bylaw = delegate.group.current_bylaw
        if not bylaw or not bylaw.officer_rotation_months:
            continue
        if (as_of - delegate.from_date).days > bylaw.officer_rotation_months * 30:
            overdue.append(delegate)
    return overdue


# ---------------------------------------------------------------------------
# W8. De-linkage and exit
# ---------------------------------------------------------------------------


@transaction.atomic
def withdraw_group(*, group, reason, actor=None, on_date=None):
    """An SHG leaves its CLA.

    Closes the membership and the delegate seats, and demotes the group to P2 —
    P3 *is* CLA membership, so a group outside a CLA cannot hold it. If the CLA
    drops below threshold as a result it is **flagged for a human**, never
    auto-dissolved: dissolving a governance body because a count moved is a
    decision no rule should take.
    """
    from . import phase as phase_service

    on_date = on_date or timezone.localdate()
    membership = StructuralMembership.objects.filter(
        child_type=ChildType.GROUP, child_id=group.pk, exited_on__isnull=True
    ).first()
    if membership is None:
        raise StructureError(_("This group is not in a CLA."))

    membership.exited_on = on_date
    membership.exit_reason = reason
    membership.save(update_fields=["exited_on", "exit_reason", "updated_at"])
    Delegate.objects.filter(group=group, to_date__isnull=True).update(to_date=on_date)

    if group.current_phase == Phase.P3:
        phase_service.demote(group, to_phase=Phase.P2, actor=actor, reason=reason, as_of=on_date)

    remaining = StructuralMembership.objects.filter(
        parent_type=ParentType.CLA, parent_id=membership.parent_id, exited_on__isnull=True
    ).count()
    threshold = policy.resolve_int("gate.cla.min_groups", location=group.kebele, default=8)
    below_threshold = remaining < threshold

    return {"membership": membership, "remaining": remaining, "below_threshold": below_threshold}


@transaction.atomic
def dissolve_cla(cla, *, reason, actor=None, on_date=None):
    """Close a CLA and everything hanging off it.

    Cascades: child memberships close, member SHGs demote to P2, CLA-level
    linkages close, and an active credit facility escalates rather than closing
    — the obligation survives the body that took it on.
    """
    from . import linkage as linkage_service
    from . import phase as phase_service

    on_date = on_date or timezone.localdate()
    memberships = StructuralMembership.objects.filter(
        parent_type=ParentType.CLA, parent_id=cla.pk, exited_on__isnull=True
    )
    for membership in memberships:
        group = Group.objects.filter(pk=membership.child_id).first()
        membership.exited_on = on_date
        membership.exit_reason = reason
        membership.save(update_fields=["exited_on", "exit_reason", "updated_at"])
        Delegate.objects.filter(cla=cla, to_date__isnull=True).update(to_date=on_date)
        if group and group.current_phase == Phase.P3:
            phase_service.demote(group, to_phase=Phase.P2, actor=actor, reason=reason, as_of=on_date)

    escalated = []
    for open_linkage in cla.linkages.open():
        if open_linkage.linkage_type.code == "credit_facility":
            escalated.append(open_linkage)
            continue
        linkage_service.close(open_linkage, actor=actor, reason=reason)

    cla.status = "DISSOLVED"
    cla.save(update_fields=["status", "updated_at"])
    return {"escalated_linkages": escalated}
