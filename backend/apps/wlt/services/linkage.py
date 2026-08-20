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

from .. import policy
from ..models import (
    Group,
    LinkageApproval,
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

    if provider is not None:
        if provider.standing != Standing.ACTIVE or not provider.active_status:
            raise LinkageError(
                _("%(provider)s is %(standing)s and cannot take new linkages.")
                % {"provider": provider.partner_name, "standing": provider.get_standing_display().lower()}
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


def _build_chain(linkage, extra_level=False):
    """Materialise the approval chain from the type row.

    Levels are rows rather than a counter so "no self-approval" is checkable at
    every level, and so an override can add one without renumbering the rest.
    """
    chain = list(linkage.linkage_type.approval_chain or [])
    if extra_level and chain:
        chain = chain + [chain[-1]]
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
    if actor is not None and level.required_role and actor.role != level.required_role:
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
        if not result.passed:
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
        return linkage

    return linkage.transition_to(
        LinkageStatus.APPROVED, actor=actor, gate_snapshot=result.as_snapshot() if result else None
    )


@transaction.atomic
def return_for_revision(linkage, *, actor, reason):
    if not reason.strip():
        raise LinkageError({"reason": _("Say what has to change.")})
    level = linkage.approvals.filter(decision="").order_by("level").first()
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
    fields = {"terms": terms} if terms else {}
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
    return linkage.transition_to(LinkageStatus.CLOSED, actor=actor, reason=reason)


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
