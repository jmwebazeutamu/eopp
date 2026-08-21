"""Service linkage lifecycle — handoff README §6.5 and §7, backlog stage 7.

Five rules, all of them from the handoff, all of them load-bearing:

1. **Gates are evaluated at screening and again at approval.** A subject can
   drift below threshold while an approval sits in a queue, and approving
   against stale numbers is how bad credit linkages happen.
2. **Every transition writes an immutable evidence snapshot** — indicator
   values, policy version, actor, timestamp.
3. **`BLOCKED` is a first-class state, not an error.** It tells the facilitator
   exactly what the subject still needs to reach. This is the single most
   behaviour-changing screen in the module, which is why `block_reasons` carries
   actual-next-to-threshold sentences rather than condition codes.
4. **An override needs a reason and escalates the chain by one level.** There
   are no silent overrides on a credit facility.
5. **Distress cascades downward.** A federation in default is its member SHGs'
   exposure too, so the risk flag reaches them.

Workflow W7 — a plain service referral — is deliberately absent from this module.
It rides `referrals.Referral` unchanged, which is what `create_service_referral`
below does: one function, no lifecycle of its own, the existing timeline.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.partners.models import Standing
from apps.users.models import Role

from .. import policy
from ..models import (
    Group,
    LinkageApproval,
    LinkageEvent,
    LinkageStatus,
    LinkageSubjectType,
    RiskReason,
    RiskSubjectType,
    ServiceLinkage,
    ServiceLinkageType,
)
from . import gates
from .ledger import clear_risk_flag, raise_risk_flag


class LinkageError(ValidationError):
    """A refused linkage operation."""


SUBJECT_FIELD = {
    LinkageSubjectType.GROUP: "subject_group",
    LinkageSubjectType.CLA: "subject_cla",
    LinkageSubjectType.FEDERATION: "subject_federation",
}

ESCALATION_ROLE = {
    Role.WLT_WOREDA_OFFICER: Role.WLT_REGION_OFFICER,
    Role.WLT_REGION_OFFICER: Role.WLT_FEDERAL_OFFICER,
}


def _can_take_approval_role(actor, required_role):
    """System administrators may act at any configured WLT approval level."""
    return actor is not None and (actor.role == Role.SYSTEM_ADMIN or not required_role or actor.role == required_role)


def subject_type_of(subject):
    from ..models import CLA, Federation

    if isinstance(subject, Group):
        return LinkageSubjectType.GROUP
    if isinstance(subject, CLA):
        return LinkageSubjectType.CLA
    if isinstance(subject, Federation):
        return LinkageSubjectType.FEDERATION
    raise LinkageError(_("A linkage subject must be an SHG, a CLA or a federation."))


def _subject_location(subject):
    return getattr(subject, "kebele", None) or getattr(subject, "woreda", None)


def _fresh_subject(linkage):
    """Re-read the subject before judging it.

    A caller holding a `ServiceLinkage` also holds whatever instance of the
    group was attached when it was loaded, and the gates are about to compare
    that instance's phase against a threshold. The same staleness the referral
    engine guards with `select_for_update`: the phase can have moved between
    proposal and approval, and re-evaluating at approval is pointless if it
    re-reads the numbers from memory.
    """
    subject = linkage.subject
    return type(subject).objects.get(pk=subject.pk)


def proposable_providers(linkage_type, subject):
    """Providers that may be proposed for this subject, here.

    A provider is only proposable where it actually operates — a bank present in
    Amhara is often absent in Afar, and a linkage proposed to one that has no
    branch in the woreda wastes a facilitator's month. Suspended and blacklisted
    organisations are excluded; blacklisting **does not close** existing
    linkages, because the obligation still exists.
    """
    from apps.partners.models import Partner

    location = _subject_location(subject)
    woreda = location
    from apps.locations.models import LocationLevel

    while woreda is not None and woreda.level != LocationLevel.WOREDA:
        woreda = woreda.parent

    queryset = Partner.objects.filter(active_status=True, standing=Standing.ACTIVE)
    if woreda is not None:
        queryset = queryset.filter(woreda_coverage__contains=[woreda.name])
    return queryset


@transaction.atomic
def propose(*, linkage_type, subject, provider=None, actor=None, value_etb=None, terms=None, on_date=None):
    """Raise a linkage. Screening happens immediately after, not later.

    The subject-type restriction is checked here **and** is data on the type
    row, which is what keeps it configuration: widening a type to accept a group
    is an administrator's decision, not a code change.
    """
    on_date = on_date or timezone.localdate()
    if isinstance(linkage_type, str):
        linkage_type = ServiceLinkageType.objects.get(code=linkage_type)

    subject_type = subject_type_of(subject)
    if not linkage_type.permits(subject_type):
        raise LinkageError(
            _("A %(type)s cannot be raised against a %(subject)s.")
            % {"type": linkage_type.label, "subject": LinkageSubjectType(subject_type).label}
        )

    if provider is None:
        raise LinkageError({"provider": _("Select a provider that operates in the subject's woreda.")})
    if provider.standing != Standing.ACTIVE or not provider.active_status:
        raise LinkageError(
            _("%(provider)s is %(standing)s and cannot take new linkages.")
            % {"provider": provider.partner_name, "standing": provider.get_standing_display().lower()}
        )
    if not proposable_providers(linkage_type, subject).filter(pk=provider.pk).exists():
        raise LinkageError(
            {
                "provider": _("%(provider)s does not operate in the subject's woreda.")
                % {"provider": provider.partner_name}
            }
        )

    linkage = ServiceLinkage.objects.create(
        linkage_type=linkage_type,
        provider=provider,
        status=LinkageStatus.PROPOSED,
        opened_on=on_date,
        value_etb=value_etb,
        terms=terms or {},
        initiated_by=actor,
        **{SUBJECT_FIELD[subject_type]: subject},
    )
    _build_chain(linkage)
    return screen(linkage, actor=actor, as_of=on_date)


@transaction.atomic
def record_resolution(linkage, *, reference, actor=None, meeting_id=None):
    """Record the collective decision required by SVC-8.

    The minute book remains the primary evidence. The linkage stores its stable
    reference (and, when available, the digital meeting UUID) so submission can
    prove the facilitator is acting on the group's decision.
    """
    if linkage.status not in (LinkageStatus.SCREENED, LinkageStatus.BLOCKED, LinkageStatus.RETURNED):
        raise LinkageError(_("A resolution can be recorded only after the linkage has screened."))
    if not str(reference or "").strip():
        raise LinkageError({"reference": _("Record the minute-book resolution reference.")})
    terms = dict(linkage.terms or {})
    terms["resolution_reference"] = str(reference).strip()
    if meeting_id:
        terms["resolution_meeting_id"] = str(meeting_id)
    terms["resolution_recorded_by"] = str(getattr(actor, "pk", ""))
    terms["resolution_recorded_at"] = timezone.now().isoformat()
    linkage.terms = terms
    linkage.save(update_fields=["terms", "updated_at"])
    LinkageEvent.objects.create(
        linkage=linkage,
        from_status=linkage.status,
        to_status=linkage.status,
        actor=actor,
        reason=_("Group resolution recorded: %(reference)s") % {"reference": str(reference).strip()},
        gate_snapshot={"resolution": {"reference": str(reference).strip(), "meeting_id": str(meeting_id or "")}},
    )
    return linkage


def _build_chain(linkage, extra_level=False):
    """Materialise the approval chain from the type row.

    Levels are rows rather than a counter so "no self-approval" is checkable at
    every level, and so an override can add one without renumbering the rest.
    """
    chain = list(linkage.linkage_type.approval_chain or [])
    if extra_level and chain:
        escalated_role = ESCALATION_ROLE.get(chain[-1])
        if escalated_role is None:
            raise LinkageError(_("This approval chain cannot be escalated beyond the federal level."))
        chain = chain + [escalated_role]
    for level, role in enumerate(chain, start=1):
        LinkageApproval.objects.get_or_create(
            linkage=linkage,
            level=level,
            defaults={"required_role": role, "is_escalation": extra_level and level == len(chain)},
        )
    return chain


@transaction.atomic
def screen(linkage, *, actor=None, as_of=None):
    """Evaluate the gates and move to SCREENED or BLOCKED.

    Blocked is where most linkages spend their first months, and it is the
    useful state: `block_reasons` is what the facilitator reads, and the same
    reasons aggregate into `mv_linkage_funnel`, which is the evidence for
    adjusting a threshold rather than guessing at one.
    """
    as_of = as_of or timezone.localdate()
    subject = _fresh_subject(linkage)
    gate_set = linkage.linkage_type.gate_set or linkage.linkage_type.code

    result = None
    if gate_set in gates._GATE_SETS:
        result = gates.evaluate(
            subject,
            gate_set,
            as_of=as_of,
            policy_set=policy.PolicySet(location=_subject_location(subject), on_date=as_of),
        )

    if result is None or result.passed:
        linkage.block_reasons = []
        return linkage.transition_to(
            LinkageStatus.SCREENED,
            actor=actor,
            gate_snapshot=result.as_snapshot() if result else None,
        )

    linkage.block_reasons = result.block_reasons
    return linkage.transition_to(
        LinkageStatus.BLOCKED,
        actor=actor,
        reason=_("Gate conditions not met."),
        gate_snapshot=result.as_snapshot(),
    )


@transaction.atomic
def submit_for_approval(linkage, *, actor=None, override_reason=""):
    """Send a screened linkage into the approval chain.

    A blocked linkage may be submitted only with an override reason, and the
    override adds a level to the chain: whoever waves a condition is not the
    person who then approves alone.
    """
    if linkage.status == LinkageStatus.BLOCKED:
        if not override_reason:
            raise LinkageError([_("This linkage is blocked.")] + list(linkage.block_reasons))
        if linkage.linkage_type.code == "credit_facility":
            phase_failure = any(
                condition.get("code") == "phase" and not condition.get("met")
                for event in linkage.events.order_by("-created_at")
                for condition in (event.gate_snapshot or {}).get("conditions", [])
            )
            if phase_failure:
                raise LinkageError(_("A credit facility cannot override the minimum-phase gate."))
        # The override escalates the chain by one level, for every type. On a
        # credit facility that is the difference between three approvals and
        # four, and it is what makes the override visible to a level that did
        # not raise it — there are no silent overrides on the pathway the
        # Ethiopian evidence warns about.
        _build_chain(linkage, extra_level=True)
        linkage.transition_to(
            LinkageStatus.SCREENED, actor=actor, reason=_("Override: %(reason)s") % {"reason": override_reason}
        )

    if linkage.status != LinkageStatus.SCREENED:
        raise LinkageError(_("Only a screened linkage can be submitted for approval."))

    if not (linkage.terms or {}).get("resolution_reference"):
        raise LinkageError(
            {"resolution_reference": _("Record the group's minute-book resolution before submission.")}
        )

    if not linkage.approvals.exists():
        # An empty chain means the facilitator alone decides — a plain service
        # referral, for instance. It goes straight to approved.
        return linkage.transition_to(LinkageStatus.APPROVED, actor=actor, reason=_("No approval required."))

    return linkage.transition_to(LinkageStatus.PENDING_APPROVAL, actor=actor, reason=override_reason)


@transaction.atomic
def approve(linkage, *, actor, note="", as_of=None):
    """Record one level's approval, re-evaluating the gates first.

    The re-evaluation is rule 1 and it is not a formality: a group whose PAR30
    rose while the paperwork moved is a different proposition from the one that
    was screened, and the approval chain has no other way to notice.
    """
    as_of = as_of or timezone.localdate()

    if linkage.status != LinkageStatus.PENDING_APPROVAL:
        raise LinkageError(_("This linkage is not waiting for approval."))

    level = linkage.approvals.filter(decision="").order_by("level").first()
    if level is None:
        raise LinkageError(_("Every level has already decided."))
    if not _can_take_approval_role(actor, level.required_role):
        raise LinkageError(_("This level is approved by a %(role)s.") % {"role": level.required_role})
    if actor is not None and linkage.initiated_by_id == getattr(actor, "pk", None):
        raise LinkageError(_("The person who proposed a linkage cannot approve it."))
    if linkage.approvals.filter(decided_by=actor).exists():
        raise LinkageError(_("You have already decided on this linkage at another level."))

    subject = _fresh_subject(linkage)
    gate_set = linkage.linkage_type.gate_set or linkage.linkage_type.code
    result = None
    if gate_set in gates._GATE_SETS:
        result = gates.evaluate(subject, gate_set, as_of=as_of)
        # A recorded override deliberately sends the failed conditions through
        # an extra approval level. Re-blocking here made that documented path
        # impossible to complete; the approvers still see the fresh snapshot.
        override_in_chain = linkage.approvals.filter(is_escalation=True).exists()
        if not result.passed and not override_in_chain:
            linkage.block_reasons = result.block_reasons
            return linkage.transition_to(
                LinkageStatus.BLOCKED,
                actor=actor,
                reason=_("Conditions no longer met at approval."),
                gate_snapshot=result.as_snapshot(),
            )

    level.decided_by = actor
    level.decided_at = timezone.now()
    level.decision = "APPROVED"
    level.note = note
    level.save(update_fields=["decided_by", "decided_at", "decision", "note", "updated_at"])

    if linkage.approvals.filter(decision="").exists():
        LinkageEvent.objects.create(
            linkage=linkage,
            from_status=LinkageStatus.PENDING_APPROVAL,
            to_status=LinkageStatus.PENDING_APPROVAL,
            actor=actor,
            reason=note or _("Approval level %(level)s completed.") % {"level": level.level},
            gate_snapshot=result.as_snapshot() if result else None,
        )
        return linkage

    return linkage.transition_to(
        LinkageStatus.APPROVED, actor=actor, reason=note, gate_snapshot=result.as_snapshot() if result else None
    )


@transaction.atomic
def return_for_revision(linkage, *, actor, reason):
    if not reason.strip():
        raise LinkageError({"reason": _("Say what has to change.")})
    level = linkage.approvals.filter(decision="").order_by("level").first()
    if level is None or not _can_take_approval_role(actor, level.required_role):
        raise LinkageError(_("Your role is not the current approval level."))
    if linkage.initiated_by_id == actor.pk or linkage.approvals.filter(decided_by=actor).exists():
        raise LinkageError(_("The proposer or a previous approver cannot return this linkage."))
    if level is not None:
        level.decided_by = actor
        level.decided_at = timezone.now()
        level.decision = "RETURNED"
        level.note = reason
        level.save(update_fields=["decided_by", "decided_at", "decision", "note", "updated_at"])
    return linkage.transition_to(LinkageStatus.RETURNED, actor=actor, reason=reason)


@transaction.atomic
def reject(linkage, *, actor, reason):
    if not reason.strip():
        raise LinkageError({"reason": _("Say why the linkage is refused.")})
    level = linkage.approvals.filter(decision="").order_by("level").first()
    if level is None or not _can_take_approval_role(actor, level.required_role):
        raise LinkageError(_("Your role is not the current approval level."))
    if linkage.initiated_by_id == actor.pk or linkage.approvals.filter(decided_by=actor).exists():
        raise LinkageError(_("The proposer or a previous approver cannot reject this linkage."))
    return linkage.transition_to(LinkageStatus.REJECTED, actor=actor, reason=reason)


@transaction.atomic
def activate(linkage, *, actor=None, on_date=None, terms=None):
    """The counterparty confirmed. From here the obligation is real.

    For a savings account this is the moment the ledger becomes two balances —
    cash and bank — and meeting close has to reconcile both. That is why the
    ledger service refuses a bank deposit until a savings linkage is active
    rather than the other way round.
    """
    if linkage.status != LinkageStatus.APPROVED:
        raise LinkageError(_("Only an approved linkage can be activated."))
    fields = {}
    if terms:
        merged_terms = dict(linkage.terms or {})
        merged_terms.update(terms)
        fields["terms"] = merged_terms
    return linkage.transition_to(LinkageStatus.ACTIVE, actor=actor, reason=_("Counterparty confirmed."), **fields)


@transaction.atomic
def mark_distressed(linkage, *, reason, actor=None):
    """An obligation was breached. Flag the subject and everything under it.

    A federation's default is its member SHGs' exposure: they guaranteed it,
    and a group whose federation is in default cannot honestly show green on its
    readiness card.
    """
    linkage.transition_to(LinkageStatus.DISTRESSED, actor=actor, reason=reason)
    _cascade_distress(linkage, reason)
    return linkage


@transaction.atomic
def mark_defaulted(linkage, *, reason, actor=None):
    linkage.transition_to(LinkageStatus.DEFAULTED, actor=actor, reason=reason)
    _cascade_distress(linkage, reason)
    return linkage


@transaction.atomic
def cure(linkage, *, actor=None, note=""):
    if (linkage.terms or {}).get("outstanding_obligation"):
        raise LinkageError(_("Settle the outstanding obligation before recording a cure."))
    linkage.transition_to(LinkageStatus.ACTIVE, actor=actor, reason=note or _("Obligation cured."))
    for group_id in linkage.subject_group_ids:
        clear_risk_flag(None, RiskReason.EXTERNAL_DISTRESS, subject_id=group_id)
    return linkage


def _cascade_distress(linkage, reason):
    detail = {"linkage_id": str(linkage.pk), "type": linkage.linkage_type.code, "reason": str(reason)}
    for group_id in linkage.subject_group_ids:
        raise_risk_flag(None, RiskReason.EXTERNAL_DISTRESS, detail=detail, subject_id=group_id)
    if linkage.subject_cla_id:
        raise_risk_flag(
            None,
            RiskReason.EXTERNAL_DISTRESS,
            detail=detail,
            subject_type=RiskSubjectType.CLA,
            subject_id=linkage.subject_cla_id,
        )
    if linkage.subject_federation_id:
        raise_risk_flag(
            None,
            RiskReason.EXTERNAL_DISTRESS,
            detail=detail,
            subject_type=RiskSubjectType.FEDERATION,
            subject_id=linkage.subject_federation_id,
        )


@transaction.atomic
def close(linkage, *, actor=None, reason=""):
    if (linkage.terms or {}).get("outstanding_obligation"):
        raise LinkageError(
            _(
                "This linkage still has an outstanding obligation. "
                "Settle, write off with approval, or transfer it first."
            )
        )
    if not str(reason or "").strip():
        raise LinkageError({"reason": _("Say why the linkage is closing.")})
    return linkage.transition_to(LinkageStatus.CLOSED, actor=actor, reason=reason)


@transaction.atomic
def record_obligation(linkage, *, kind, reference, actor=None, missed=False, outstanding=True, note=""):
    """Append an SVC-15 obligation event and update the linkage's exposure."""
    if linkage.status not in (LinkageStatus.ACTIVE, LinkageStatus.DISTRESSED):
        raise LinkageError(_("Obligations can be recorded only on an active or distressed linkage."))
    if not str(kind or "").strip() or not str(reference or "").strip():
        raise LinkageError(_("Obligation type and reference are required."))
    snapshot = {
        "obligation": {
            "kind": str(kind).strip(),
            "reference": str(reference).strip(),
            "outstanding": bool(outstanding),
            "missed": bool(missed),
        }
    }
    terms = dict(linkage.terms or {})
    terms["outstanding_obligation"] = bool(outstanding)
    linkage.terms = terms
    linkage.save(update_fields=["terms", "updated_at"])
    if missed and linkage.status == LinkageStatus.ACTIVE:
        linkage.transition_to(
            LinkageStatus.DISTRESSED,
            actor=actor,
            reason=note or _("Obligation missed."),
            gate_snapshot=snapshot,
        )
        _cascade_distress(linkage, note or _("Obligation missed."))
    else:
        # A same-state transition is intentionally not part of the lifecycle;
        # obligation activity is nevertheless immutable evidence on its timeline.
        LinkageEvent.objects.create(
            linkage=linkage,
            from_status=linkage.status,
            to_status=linkage.status,
            actor=actor,
            reason=note,
            gate_snapshot=snapshot,
        )
    return linkage


def obligation_register(linkage):
    """Current state of every obligation reference, reconstructed from immutable events."""
    register = {}
    events = linkage.events.order_by("occurred_at", "pk")
    for event in events:
        obligation = (event.gate_snapshot or {}).get("obligation")
        if not obligation or not obligation.get("reference"):
            continue
        register[str(obligation["reference"])] = {
            **obligation,
            "occurred_at": event.occurred_at,
            "note": event.reason,
        }
    return list(register.values())


@transaction.atomic
def resolve_obligation(linkage, *, reference, resolution, actor=None, note="", transfer_reference=""):
    current = {row["reference"]: row for row in obligation_register(linkage)}
    obligation = current.get(str(reference))
    if not obligation or not obligation.get("outstanding"):
        raise LinkageError({"reference": _("Choose an outstanding obligation.")})
    if resolution == "WRITE_OFF" and not str(note or "").strip():
        raise LinkageError({"note": _("Explain why this obligation is being written off.")})
    if resolution == "TRANSFER" and not str(transfer_reference or "").strip():
        raise LinkageError({"transfer_reference": _("Name the receiving obligation reference.")})

    snapshot = {"obligation": {**obligation, "outstanding": False, "resolution": resolution}}
    snapshot["obligation"].pop("occurred_at", None)
    snapshot["obligation"].pop("note", None)
    LinkageEvent.objects.create(
        linkage=linkage,
        from_status=linkage.status,
        to_status=linkage.status,
        actor=actor,
        reason=note or {"SETTLED": _("Obligation settled."), "WRITE_OFF": _("Obligation written off."), "TRANSFER": _("Obligation transferred.")}[resolution],
        gate_snapshot=snapshot,
    )
    current[str(reference)] = snapshot["obligation"]
    if resolution == "TRANSFER":
        record_obligation(
            linkage,
            kind=obligation.get("kind", "transfer"),
            reference=str(transfer_reference).strip(),
            outstanding=True,
            missed=False,
            note=_("Transferred from %(reference)s") % {"reference": reference},
            actor=actor,
        )
        current[str(transfer_reference).strip()] = {"outstanding": True}
    terms = dict(linkage.terms or {})
    terms["outstanding_obligation"] = any(row.get("outstanding") for row in current.values())
    linkage.terms = terms
    linkage.save(update_fields=["terms", "updated_at"])
    return linkage


def default_overdue_distress(as_of=None):
    """Move distress beyond the policy cure window to default (SVC-16)."""
    as_of = as_of or timezone.localdate()
    defaulted = 0
    for linkage in ServiceLinkage.objects.filter(status=LinkageStatus.DISTRESSED).select_related(
        "subject_group", "subject_cla", "subject_federation"
    ):
        location = _subject_location(linkage.subject)
        cure_days = policy.PolicySet(location=location, on_date=as_of).get("linkage.distress_cure_days")
        distress_event = linkage.events.filter(to_status=LinkageStatus.DISTRESSED).order_by("-created_at").first()
        if distress_event and as_of > distress_event.occurred_at.date() + timedelta(days=int(cure_days)):
            mark_defaulted(linkage, reason=_("Distress was not cured within the policy window."))
            defaulted += 1
    return defaulted


def lapse_stale_approvals(as_of=None):
    """Approved linkages the counterparty never activated.

    A bank that agreed to open an account and never did is not an open case for
    a facilitator to chase forever; it is a lapsed one, and the funnel should say
    so. Only runs for types that carry a lapse window.
    """
    as_of = as_of or timezone.localdate()
    lapsed = 0
    for linkage in ServiceLinkage.objects.filter(
        status=LinkageStatus.APPROVED, linkage_type__lapse_days__isnull=False
    ).select_related("linkage_type"):
        deadline = linkage.approved_on + timedelta(days=linkage.linkage_type.lapse_days)
        if as_of > deadline:
            linkage.transition_to(LinkageStatus.LAPSED, reason=_("Not activated within the agreed window."))
            lapsed += 1
    return lapsed


def flag_blacklisted_providers():
    """Blacklisting flags open linkages for review; it does not close them.

    The obligation still exists — the group's money is still in that account —
    so closing them automatically would misstate the group's position and lose
    the thread to recover it.
    """
    from apps.partners.models import Partner

    flagged = []
    blacklisted = Partner.objects.filter(standing=Standing.BLACKLISTED)
    for linkage in ServiceLinkage.objects.filter(provider__in=blacklisted).open().select_related("provider"):
        detail = {"provider": linkage.provider.partner_name, "linkage_id": str(linkage.pk)}
        for group_id in linkage.subject_group_ids:
            raise_risk_flag(None, RiskReason.EXTERNAL_DISTRESS, detail=detail, subject_id=group_id)
        flagged.append(linkage)
    return flagged


# ---------------------------------------------------------------------------
# Workflow W7 — the one that rides the referral engine unchanged
# ---------------------------------------------------------------------------


@transaction.atomic
def create_service_referral(*, subject, category, partner, actor, notes=""):
    """Refer a group or a woman to a service, through `referrals.Referral`.

    No gates beyond an active subject, no approval chain, no lifecycle of its
    own: this is the thin workflow the handoff describes, and the whole point of
    generalising the referral subject was that it needs no new machinery. The
    category's `allowed_subject_types` is what refuses a protection referral
    against a group.
    """
    from apps.referrals.models import Referral, SubjectType

    from ..models import CLA, Federation

    if isinstance(subject, Group):
        field, subject_type = "subject_group", SubjectType.GROUP
    elif isinstance(subject, CLA):
        field, subject_type = "subject_cla", SubjectType.CLA
    elif isinstance(subject, Federation):
        field, subject_type = "subject_federation", SubjectType.FEDERATION
    else:
        field, subject_type = "subject_youth", SubjectType.YOUTH

    if not category.permits(subject_type):
        raise LinkageError(
            _("A %(category)s referral cannot be raised against a %(subject)s.")
            % {"category": category.label, "subject": SubjectType(subject_type).label}
        )

    referral = Referral(
        referral_category=category,
        receiving_partner=partner,
        initiated_by=actor,
        notes=notes,
        **{field: subject},
    )
    referral.full_clean(exclude=["subject_type"], validate_unique=False)
    referral.save()
    return referral
