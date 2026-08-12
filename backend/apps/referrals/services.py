"""Referral domain services — spec §2.3.

The state machine itself lives on the model (`Referral.transition_to`). This
module holds the operations that span more than one row: creating the onward and
replacement referrals that §6.2 prompts for, which must link two referrals and
move a status together or not at all.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import ConfirmationStatus, Referral, ReferralStatus, ReferralTrigger


def _partner_can_receive(partner):
    if not partner.can_receive_referrals:
        raise ValidationError(
            {
                "receiving_partner": _("%(name)s is not active and cannot receive referrals.")
                % {"name": partner.partner_name}
            }
        )


@transaction.atomic
def initiate_referral(*, case, referral_category, receiving_partner, initiated_by, **fields):
    """Create a manual referral in Pending Confirmation — spec §6.2, first row.

    The cap in §6.3 is deliberately NOT checked here. A referral only occupies a
    concurrency slot once the partner confirms it and it becomes Active, so
    blocking initiation would stop a case manager queuing the next step while
    the current one is still awaiting a response.
    """
    _partner_can_receive(receiving_partner)

    referral = Referral(
        case=case,
        referral_category=referral_category,
        receiving_partner=receiving_partner,
        initiated_by=initiated_by,
        referral_trigger=ReferralTrigger.MANUAL,
        status=ReferralStatus.PENDING_CONFIRMATION,
        confirmation_status=ConfirmationStatus.PENDING,
        **fields,
    )
    referral.full_clean(exclude=["parallel_group_id"], validate_unique=False)
    referral.save()

    case.touch()
    return referral


@transaction.atomic
def create_onward_referral(*, parent, referral_category, receiving_partner, initiated_by, **fields):
    """Confirm the Onward prompt — spec §6.2, last row.

    "Prompted automatically when a prior referral in the case reaches Completed
    status. The case manager reviews and confirms before the new referral is
    created, to manage data entry burden." The parent stays Completed; only a
    new referral appears.
    """
    if parent.status != ReferralStatus.COMPLETED:
        raise ValidationError(
            {
                "parent_referral": _("An onward referral follows a completed referral, not a %(status)s one.")
                % {"status": parent.get_status_display()}
            }
        )

    _partner_can_receive(receiving_partner)

    referral = Referral(
        case=parent.case,
        referral_category=referral_category,
        receiving_partner=receiving_partner,
        initiated_by=initiated_by,
        referral_trigger=ReferralTrigger.ONWARD,
        parent_referral=parent,
        status=ReferralStatus.PENDING_CONFIRMATION,
        confirmation_status=ConfirmationStatus.PENDING,
        **fields,
    )
    referral.full_clean(exclude=["parallel_group_id"], validate_unique=False)
    referral.save()

    parent.case.touch()
    return referral


@transaction.atomic
def create_replacement_referral(*, failed_referral, referral_category, receiving_partner, initiated_by, **fields):
    """Confirm the Replacement prompt — spec §6.2, Failed -> Replaced.

    Three things happen together: the new referral is created with
    `referral_trigger = Replacement` and `parent_referral` pointing at the failed
    one, the failed one's `replacement_referral` forward link is set, and it
    moves to Replaced. A partial application would leave a failed referral that
    still prompts for a replacement it already has, so this is atomic.
    """
    if failed_referral.status != ReferralStatus.FAILED:
        raise ValidationError(
            {
                "parent_referral": _("Only a failed referral can be replaced; this one is %(status)s.")
                % {"status": failed_referral.get_status_display()}
            }
        )
    if failed_referral.replacement_referral_id:
        raise ValidationError({"parent_referral": _("This referral has already been replaced.")})

    _partner_can_receive(receiving_partner)

    replacement = Referral(
        case=failed_referral.case,
        referral_category=referral_category,
        receiving_partner=receiving_partner,
        initiated_by=initiated_by,
        referral_trigger=ReferralTrigger.REPLACEMENT,
        parent_referral=failed_referral,
        status=ReferralStatus.PENDING_CONFIRMATION,
        confirmation_status=ConfirmationStatus.PENDING,
        **fields,
    )
    replacement.full_clean(exclude=["parallel_group_id"], validate_unique=False)
    replacement.save()

    # Passed as a transition kwarg rather than assigned beforehand:
    # transition_to re-reads the row under a lock, so an assignment made before
    # the call would be applied to a stale instance.
    failed_referral.transition_to(ReferralStatus.REPLACED, actor=initiated_by, replacement_referral=replacement)

    return replacement
