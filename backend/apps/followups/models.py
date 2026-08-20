"""Follow-Up / Contact Log — spec §4.9. Sprint 6.

Every attempt to reach a youth, whether or not it worked. The failures are the
point: §5's CM-4 asks for "4+ failed contact attempts" as an at-risk condition,
and that number does not exist unless the attempts that failed are written down.
A log of successful calls is a log of nothing.

Two jobs beyond the log itself:

* **It closes the referral loop.** §6.2's Active → Completed row reads "outcome
  recorded and verified via follow-up visit", and `related_referral` is that
  link. A follow-up that reached the youth is what turns a self-reported outcome
  into a verified one — see `services.verify_referral_outcome`.
* **It triggers a pathway revision.** §4.9's `pathway_revision_flag` marks a
  contact after which the plan has to change. The revision itself is a
  `PathwayAssignment` (§4.4) with its own approval; this only records that the
  conversation called for one.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class ContactMethod(models.TextChoices):
    """TODO(spec-gap): §4.9 types this as an Enum and does not enumerate it.

    These are the channels the pilot woredas actually use. `THIRD_PARTY` covers
    reaching a youth through a relative or a kebele official, which happens
    constantly and is not the same as reaching her.
    """

    PHONE = "PHONE", _("Phone call")
    SMS = "SMS", _("SMS")
    HOME_VISIT = "HOME_VISIT", _("Home visit")
    OFFICE_VISIT = "OFFICE_VISIT", _("Youth came to the office")
    PARTNER_VISIT = "PARTNER_VISIT", _("Visit to the partner or employer")
    THIRD_PARTY = "THIRD_PARTY", _("Message left with a family member or official")


class ContactOutcome(models.TextChoices):
    """Spec §4.9, verbatim.

    The four values are two questions at once — did you reach her, and did she
    engage — which is why "Reached, not engaged" is not a failure to contact and
    "No response" is not a refusal. Conflating them would put a youth who said
    no in the same queue as one whose phone is off, and those need different
    people to do different things.
    """

    REACHED_ENGAGED = "REACHED_ENGAGED", _("Reached — engaged")
    REACHED_NOT_ENGAGED = "REACHED_NOT_ENGAGED", _("Reached — not engaged")
    NO_RESPONSE = "NO_RESPONSE", _("No response")
    UNREACHABLE = "UNREACHABLE", _("Unreachable")

    @classmethod
    def reached(cls):
        return (cls.REACHED_ENGAGED, cls.REACHED_NOT_ENGAGED)

    @classmethod
    def failed(cls):
        """Attempts that did not reach the youth at all.

        The CM-4 condition counts these, and only these: a youth who answered
        and declined has been reached, and the case manager knows where she
        stands.
        """
        return (cls.NO_RESPONSE, cls.UNREACHABLE)


class ReEngagementStatus(models.TextChoices):
    """TODO(spec-gap): §4.9 names the field and not its values.

    What happens next, as the youth described it. `NOT_APPLICABLE` is the
    default because most follow-ups are routine verification, not re-engagement
    of somebody who had dropped out.
    """

    NOT_APPLICABLE = "NOT_APPLICABLE", _("Not applicable")
    AGREED = "AGREED", _("Agreed to re-engage")
    CONSIDERING = "CONSIDERING", _("Considering")
    DECLINED = "DECLINED", _("Declined")
    UNABLE = "UNABLE", _("Willing but unable")


class FollowUpQuerySet(models.QuerySet):
    def reached(self):
        return self.filter(contact_outcome__in=ContactOutcome.reached())

    def failed(self):
        return self.filter(contact_outcome__in=ContactOutcome.failed())

    def verifying(self):
        """Follow-ups made against a specific referral outcome."""
        return self.filter(related_referral__isnull=False)

    def cases_with_failed_attempts(self, minimum=4, since=None):
        """CM-4's fourth condition: youth nobody can reach.

        Counted per case rather than per referral, because the question is
        whether the *youth* has gone quiet. `since` bounds it to the current
        episode — four failures last year and a conversation last week is not a
        youth who has disappeared.
        """
        queryset = self.failed()
        if since is not None:
            queryset = queryset.filter(attempt_date__gte=since)
        return (
            queryset.values("case_id")
            .annotate(attempts=models.Count("id"))
            .filter(attempts__gte=minimum)
            .values_list("case_id", flat=True)
        )


class FollowUp(BaseModel):
    """Spec §4.9. `followup_id` is `id`, per the §4 type-translation guide."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="follow_ups",
        verbose_name=_("case"),
    )
    related_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="follow_ups",
        verbose_name=_("related referral"),
        help_text=_("Set when this contact verifies a specific referral outcome."),
    )

    attempt_date = models.DateField(_("attempt date"), default=date.today, db_index=True)
    contact_method = models.CharField(_("contact method"), max_length=16, choices=ContactMethod.choices)
    contact_outcome = models.CharField(
        _("contact outcome"), max_length=24, choices=ContactOutcome.choices, db_index=True
    )

    re_engagement_status = models.CharField(
        _("re-engagement"),
        max_length=16,
        choices=ReEngagementStatus.choices,
        default=ReEngagementStatus.NOT_APPLICABLE,
        blank=True,
    )
    # §4.9 links this to a Pathway Assignment revision. It records that the
    # conversation called for one; the revision itself is a §4.4 assignment with
    # its own assessor and its own date, and nothing here creates it.
    pathway_revision_flag = models.BooleanField(
        _("pathway revision needed"),
        default=False,
        help_text=_("The plan has to change. Raise the revision on the case; this only records the finding."),
    )

    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="follow_ups",
        verbose_name=_("conducted by"),
    )
    notes = models.TextField(_("notes"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = FollowUpQuerySet.as_manager()

    class Meta:
        verbose_name = _("follow-up")
        verbose_name_plural = _("follow-ups")
        ordering = ["-attempt_date", "-created_at"]
        constraints = [
            # A conversation that never happened cannot have found anything.
            models.CheckConstraint(
                condition=models.Q(contact_outcome__in=ContactOutcome.reached())
                | models.Q(re_engagement_status__in=["", ReEngagementStatus.NOT_APPLICABLE]),
                name="followup_reengagement_needs_contact",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-attempt_date"]),
            models.Index(fields=["contact_outcome", "attempt_date"]),
            models.Index(fields=["related_referral"]),
        ]

    def __str__(self):
        return f"{self.get_contact_method_display()} on {self.attempt_date}"

    @property
    def reached_the_youth(self):
        return self.contact_outcome in ContactOutcome.reached()

    def clean(self):
        errors = {}

        if self.attempt_date and self.attempt_date > date.today():
            errors["attempt_date"] = _("A contact attempt cannot be in the future.")

        if not self.reached_the_youth and self.re_engagement_status not in ("", ReEngagementStatus.NOT_APPLICABLE):
            errors["re_engagement_status"] = _("Nobody was reached, so there is no answer to record.")

        if self.related_referral_id and self.related_referral.case_id != self.case_id:
            errors["related_referral"] = _("That referral belongs to a different case.")

        if self.pathway_revision_flag and not self.reached_the_youth:
            # The finding has to come from the youth. A revision decided without
            # her is a decision about her, which §4.4's assessment is not.
            errors["pathway_revision_flag"] = _("A pathway revision has to come from a conversation with the youth.")

        if errors:
            raise ValidationError(errors)
