"""Follow-up operations — spec §4.9, and §6.2's verification path.

The interesting function here is `verify_referral_outcome`. §6.2's Active →
Completed row reads "outcome recorded and verified via follow-up visit", and
until Sprint 6 there was no follow-up to verify it *with*: an outcome was
recorded by whoever typed it, `verification_source` was whatever they chose, and
the externally-verified figure the §8.3 donor tier reports as its headline had
no route to become true except by a staff member asserting it.

A follow-up that reached the youth is that route. It stamps the source, the
verifier and the method together, so the three cannot disagree — which they
could, and did, when each was set by hand on a different screen.
"""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import ContactOutcome, FollowUp, ReEngagementStatus


class FollowUpError(ValidationError):
    """A refused follow-up operation."""


@transaction.atomic
def record_attempt(
    *, case, contact_method, contact_outcome, conducted_by, related_referral=None, attempt_date=None, **fields
):
    """Log one contact attempt, successful or not.

    **The failures matter most.** CM-4's "4+ failed contact attempts" cannot be
    computed unless the attempts that failed are written down, and a log that
    only records successful calls is a log of nothing.

    Case activity is stamped either way: trying to reach a youth is work on the
    case, and a case manager who called four times should not have her case
    counted as stalled for lack of activity.
    """
    follow_up = FollowUp(
        case=case,
        related_referral=related_referral,
        attempt_date=attempt_date or date.today(),
        contact_method=contact_method,
        contact_outcome=contact_outcome,
        conducted_by=conducted_by,
        **fields,
    )
    follow_up.full_clean()
    follow_up.save()
    case.touch()
    return follow_up


@transaction.atomic
def verify_referral_outcome(follow_up, *, verification_source, method="", actor=None):
    """Turn a recorded outcome into a verified one — §6.2, §8.3.

    Three refusals, each of which was reachable before this existed:

    * The follow-up must name a referral. Verification is about a specific
      outcome, not about a case in general.
    * The follow-up must have **reached the youth**. A verification founded on a
      call nobody answered is the self-reported figure wearing a better label.
    * The referral must be Completed with an outcome. There is nothing to verify
      about a referral that has not produced a result yet.

    Everything else — the source, the verifier, the method — is stamped
    together, because these are the three fields that drifted apart when each
    was set by hand.
    """
    from apps.referrals.models import ReferralStatus, VerificationSource

    referral = follow_up.related_referral
    if referral is None:
        raise FollowUpError(_("Name the referral this contact verifies."))
    if not follow_up.reached_the_youth:
        raise FollowUpError(_("This contact did not reach the youth, so it cannot verify anything about her outcome."))
    if referral.status != ReferralStatus.COMPLETED or not referral.outcome_type_id:
        raise FollowUpError(_("That referral has no recorded outcome to verify."))
    if verification_source == VerificationSource.SELF_REPORTED:
        # Permitted as a *record* — the youth said so — but it is not
        # verification, and stamping the verifier would make it look like one.
        referral.verification_source = verification_source
        referral.outcome_verification_method = method or str(_("Follow-up contact with the youth"))
        referral.save(update_fields=["verification_source", "outcome_verification_method", "updated_at"])
        return referral

    referral.verification_source = verification_source
    referral.outcome_verified_by = actor or follow_up.conducted_by
    referral.outcome_verification_method = method or str(
        _("Verified at a %(method)s on %(date)s")
        % {"method": follow_up.get_contact_method_display().lower(), "date": follow_up.attempt_date}
    )
    referral.save(
        update_fields=[
            "verification_source",
            "outcome_verified_by",
            "outcome_verification_method",
            "updated_at",
        ]
    )
    follow_up.case.touch()
    return referral


def unverified_outcomes(referrals):
    """Completed referrals whose outcome nobody has stood behind.

    The M&E queue. `externally_verified()` excludes a blank source *and* a
    self-reported one, so this is its complement over recorded outcomes — the
    work that stands between the recorded rate and the reportable one.
    """
    return referrals.with_recorded_outcome().exclude(pk__in=referrals.externally_verified().values("pk"))


def awaiting_follow_up(referrals, threshold_days, as_of=None):
    """Active referrals nobody has followed up since the service started.

    The condition behind the §4.13 Follow-Up Due alert. The spec names the alert
    type and never defines its trigger, so this is the working definition:

        a referral that has been Active longer than the threshold, with no
        contact attempt recorded against it since it was confirmed.

    Anchored on the referral rather than on the case because that is what §6.2
    asks the follow-up to close: the referral is Active, the youth is supposed to
    be attending something, and nobody has checked.

    TODO(open-question): §11 — `FOLLOW_UP_DUE_DAYS` and this definition both
    need programme sign-off. 14 days is the confirmation standard reused, not an
    agreed follow-up standard.
    """
    from apps.referrals.models import ReferralStatus

    as_of = as_of or date.today()
    cutoff = as_of - timedelta(days=threshold_days)

    active = referrals.filter(status=ReferralStatus.ACTIVE).filter(
        Q(confirmed_date__lte=cutoff) | Q(confirmed_date__isnull=True, initiated_date__lte=cutoff)
    )
    followed = FollowUp.objects.filter(related_referral__in=active, attempt_date__gte=cutoff).values(
        "related_referral_id"
    )
    return active.exclude(pk__in=followed)


def contact_summary(case, since=None):
    """What has been tried, and what it found.

    Read by the case screen and by CM-4. Returned as counts rather than a
    verdict: "three no-responses and one reached, not engaged" is a different
    conversation from "four failures", and the screen should be able to say so.
    """
    attempts = case.follow_ups.all()
    if since is not None:
        attempts = attempts.filter(attempt_date__gte=since)

    by_outcome = {
        outcome: attempts.filter(contact_outcome=outcome).count() for outcome, _label in ContactOutcome.choices
    }
    failed = sum(by_outcome[outcome] for outcome in ContactOutcome.failed())
    last = attempts.order_by("-attempt_date").first()

    return {
        "attempts": attempts.count(),
        "failed": failed,
        "reached": sum(by_outcome[outcome] for outcome in ContactOutcome.reached()),
        "by_outcome": by_outcome,
        "last_attempt_on": last.attempt_date.isoformat() if last else None,
        "last_outcome": last.contact_outcome if last else None,
        "pathway_revision_flagged": attempts.filter(pathway_revision_flag=True).exists(),
        "re_engagement": (
            attempts.exclude(re_engagement_status__in=["", ReEngagementStatus.NOT_APPLICABLE])
            .order_by("-attempt_date")
            .values_list("re_engagement_status", flat=True)
            .first()
        ),
    }
