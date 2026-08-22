"""The phase machine — handoff README §8, backlog stage 6.

**The system computes readiness; a human approves.** Never auto-graduate. A
phase transition is a governance decision about twenty women's savings, and
letting a nightly job take it would make the readiness card a formality rather
than a conversation.

Two properties carry the audit, and both are database-enforced as well as
checked here: the submitter cannot be the approver (A24), and a decision cannot
be rewritten afterwards (A26). A submission that has not been decided *can*
still change — it is a request, not a record — which is why the immutability
trigger locks on `decided_at` rather than on insertion.

De-graduation is a normal transition in the other direction, not an error state.
A group that falls back to P1 has a phase event saying so, with the numbers that
justified it.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .. import policy
from ..models import GroupStatus, Phase, PhaseDirection, PhaseEvent
from . import gates


class PhaseError(ValidationError):
    """A refused phase operation."""


NEXT_PHASE = {None: Phase.P1, "": Phase.P1, Phase.P1: Phase.P2, Phase.P2: Phase.P3, Phase.P3: Phase.P4}


# The phase gate sets in order, with the label the card shows. Ordered because
# "which gates has this group already passed" is a walk along this list.
PHASE_GATE_SETS = [
    ("forming_to_p1", _("Forming → Phase 1")),
    ("p1_to_p2", _("Phase 1 → Phase 2")),
    ("p2_to_p3", _("Phase 2 → Phase 3")),
]


def readiness(group, as_of=None, gate_set=None):
    """The gate result for a phase gate — by default the group's next one.

    What the readiness card renders: every condition, with the actual value next
    to the threshold. Computed on demand so it changes the moment a meeting
    closes — that immediate feedback is most of the module's behaviour-change
    value, and a figure that only moves overnight does not produce it.

    `gate_set` names an earlier gate instead. A Phase 2 group asked for
    `p1_to_p2` gets those conditions **against today's data**, which answers a
    different and equally real question: does it still hold the discipline it
    was promoted on? Savings compliance and attendance are continuous, so a
    group can fall back below a gate it has already passed, and until this was
    reachable nothing on any screen would have shown it.
    """
    as_of = as_of or timezone.localdate()
    gate_set = gate_set or gates.gate_set_for_phase(group.current_phase or None)
    if gate_set is None:
        return None
    return gates.evaluate(group, gate_set, as_of=as_of)


def available_gate_sets(group):
    """The phase gates worth offering for this group: everything up to its next.

    A gate beyond the next one is not offered. Its conditions would be measured
    against a phase the group has not entered, so the numbers would be real and
    the comparison meaningless.
    """
    next_set = gates.gate_set_for_phase(group.current_phase or None)
    offered = []
    for name, label in PHASE_GATE_SETS:
        offered.append({"name": name, "label": str(label), "is_next": name == next_set})
        if name == next_set:
            break
    return offered


@transaction.atomic
def submit(group, *, actor, override_reason="", as_of=None):
    """Ask the woreda to promote this group.

    A submission against a failing gate is allowed **only** with an override
    reason: the handbook's thresholds are not the only thing a facilitator
    knows, and refusing the submission outright would push the conversation off
    the system entirely. What it cannot do is happen silently.
    """
    as_of = as_of or timezone.localdate()

    if group.status not in GroupStatus.operating():
        raise PhaseError(_("Only an operating group can be put forward for a phase transition."))

    target = NEXT_PHASE.get(group.current_phase or None)
    if target is None:
        raise PhaseError(_("This group is already at the highest phase."))

    pending = PhaseEvent.objects.filter(group=group, decided_at__isnull=True).first()
    if pending is not None:
        raise PhaseError(_("This group already has a phase transition waiting for a decision."))

    result = readiness(group, as_of=as_of)
    if result is not None and not result.passed and not override_reason:
        raise PhaseError(result.block_reasons)

    return PhaseEvent.objects.create(
        group=group,
        from_phase=group.current_phase or "",
        to_phase=target,
        direction=PhaseDirection.PROMOTION,
        submitted_by=actor,
        submitted_at=timezone.now(),
        policy_version=policy.current_version(),
        gate_snapshot=result.as_snapshot() if result else {},
        override_reason=override_reason,
    )


@transaction.atomic
def approve(event, *, actor, as_of=None):
    """Take the decision, on numbers computed now rather than at submission.

    Gates are evaluated **again** here. A group can drift below threshold while
    its submission sits in a woreda queue, and approving against stale numbers
    is how a group gets promoted on a month it was already failing. Both
    snapshots stay: the one it was submitted on and the one it was decided on.
    """
    as_of = as_of or timezone.localdate()
    group = event.group

    if event.decided_at is not None:
        raise PhaseError(_("This transition has already been decided."))
    if actor is not None and event.submitted_by_id == getattr(actor, "pk", None):
        # A24. Also a check constraint, because a thin woreda office is exactly
        # where one person holds both roles and the screen would let her.
        raise PhaseError(_("The person who submitted a transition cannot also approve it."))
    if actor is not None and actor.wlt_approval_level is None:
        raise PhaseError(_("Your role does not approve phase transitions."))

    result = readiness(group, as_of=as_of)
    snapshot = dict(event.gate_snapshot or {})
    snapshot["at_decision"] = result.as_snapshot() if result else None
    if result is not None and not result.passed and not event.override_reason:
        raise PhaseError([_("This group no longer meets the gate it was submitted against.")] + result.block_reasons)

    event.decided_by = actor
    event.decided_at = timezone.now()
    event.gate_snapshot = snapshot
    event.save(update_fields=["decided_by", "decided_at", "gate_snapshot", "updated_at"])

    group.current_phase = event.to_phase
    group.phase_entered_on = as_of
    group.save(update_fields=["current_phase", "phase_entered_on", "updated_at"])
    return event


@transaction.atomic
def reject(event, *, actor, reason):
    """Refuse a submission, with the reason on the record."""
    if event.decided_at is not None:
        raise PhaseError(_("This transition has already been decided."))
    if not reason.strip():
        raise PhaseError({"reason": _("Say why the transition is refused.")})
    if actor is not None and event.submitted_by_id == getattr(actor, "pk", None):
        raise PhaseError(_("The person who submitted a transition cannot also decide it."))

    snapshot = dict(event.gate_snapshot or {})
    snapshot["decision"] = "rejected"
    snapshot["decision_reason"] = reason
    event.decided_by = actor
    event.decided_at = timezone.now()
    event.gate_snapshot = snapshot
    event.save(update_fields=["decided_by", "decided_at", "gate_snapshot", "updated_at"])
    return event


@transaction.atomic
def demote(group, *, to_phase, actor, reason, as_of=None):
    """Move a group backwards. A normal transition, not an error state.

    Used by W8 when an SHG leaves a CLA and returns to P2, and by a woreda
    officer when a group's discipline has genuinely lapsed. It needs the same
    approval and leaves the same evidence as a promotion: a demotion nobody
    signed is indistinguishable from a data fix.
    """
    as_of = as_of or timezone.localdate()
    if not reason.strip():
        raise PhaseError({"reason": _("Say why the group is being moved back.")})

    result = readiness(group, as_of=as_of)
    # `submitted_by` is deliberately empty. Nobody submitted a demotion — the
    # condition was observed, and an officer decided on it. Naming the same
    # person on both sides would also trip the no-self-approval constraint,
    # which is the constraint working: a demotion is not a two-party approval
    # and should not be recorded as one.
    event = PhaseEvent.objects.create(
        group=group,
        from_phase=group.current_phase or "",
        to_phase=to_phase,
        direction=PhaseDirection.DEMOTION,
        decided_by=actor,
        decided_at=timezone.now(),
        policy_version=policy.current_version(),
        gate_snapshot=result.as_snapshot() if result else {},
        override_reason=reason,
    )

    group.current_phase = to_phase
    group.phase_entered_on = as_of
    group.save(update_fields=["current_phase", "phase_entered_on", "updated_at"])
    return event


def pending_for(user):
    """Phase submissions waiting on this user's level.

    Scoped through the same group scoping every other WLT queryset uses, so an
    approval queue cannot show a group the officer could not open.
    """
    from apps.users.permissions import scope_group_queryset

    from ..models import Group

    groups = scope_group_queryset(Group.objects.all(), user)
    return (
        PhaseEvent.objects.filter(group__in=groups, decided_at__isnull=True)
        .exclude(submitted_by=user)
        .select_related("group", "submitted_by")
    )
