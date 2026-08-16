"""Seed backdated demo cases whose referrals exercise the §6.4 stack timeline.

The referrals created by hand during development all carry today's date, so the
timeline draws them as a single column and demonstrates nothing about the axis,
the open-ended Active bars, or the gap between a failure and its replacement.
This builds cases that span months, one per shape the timeline has to handle.

Everything goes through `services` and `Referral.transition_to`, so the rows are
the ones the application itself would produce: the §6.2 table is enforced, the
§6.3 cap is enforced, and the parallel group is stamped by the same code that
stamps it in production. Only the dates are ours.

    python manage.py seed_demo_referrals            # create what is missing
    python manage.py seed_demo_referrals --refresh  # delete and rebuild
    python manage.py seed_demo_referrals --reset    # delete, create nothing

Development data only. It writes youth and case records, so do not point it at
an environment holding real ones — it refuses unless DEBUG is on or
--i-know-this-is-not-production is passed.
"""

import uuid
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.cases.models import Case, Pathway, PathwayAssignment, ProfilingRecord
from apps.partners.models import Partner
from apps.referrals import services
from apps.referrals.models import Referral, ReferralStatus
from apps.referrals.taxonomy import FailureReasonCode, OutcomeType, ReferralCategory
from apps.users.models import Role, User
from apps.youth.models import Sex, Youth

# Fixed namespace: ids are derived from it, so re-running finds the rows it made
# last time instead of creating a second set.
DEMO_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

DEMO_NOTE = "Demo data for the referral stack timeline."


def demo_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, ":".join(parts))


class Command(BaseCommand):
    help = "Seed backdated demo cases and referrals for the stack timeline (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo records and stop.")
        parser.add_argument("--refresh", action="store_true", help="Delete the demo records, then rebuild them.")
        parser.add_argument(
            "--i-know-this-is-not-production",
            action="store_true",
            dest="force",
            help="Required to run with DEBUG off.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "This writes youth and case records. Re-run with --i-know-this-is-not-production "
                "if that is really what you want here."
            )

        self.today = date.today()
        self.quiet = options["verbosity"] == 0

        if options["reset"] or options["refresh"]:
            self.delete_demo_records()
            if options["reset"]:
                return

        self.case_manager = self.pick_user(Role.CASE_MANAGER)
        self.outreach_worker = self.pick_user(Role.OUTREACH_WORKER) or self.case_manager
        self.partners = {p.partner_name: p for p in Partner.objects.filter(active_status=True)}
        if len(self.partners) < 3:
            raise CommandError("Needs at least three active partners; run the partner seed first.")

        scenarios = [
            ("sequential", self.sequential_chain),
            ("parallel", self.parallel_pair),
            ("replacement", self.failure_and_replacement),
            ("onward3", self.three_onward_hops),
            ("mixed", self.pending_and_cancelled),
            ("empty", self.no_referrals_yet),
        ]

        self.say("")
        for slug, build in scenarios:
            # Idempotent on the case, not just on the youth: the referrals are
            # created through the domain services, which have no natural key to
            # update against, so a second plain run would stack a duplicate set
            # on top. --refresh is the way to rebuild.
            existing = Case.objects.filter(id=demo_id("case", slug)).first()
            if existing:
                count = Referral.objects.filter(case=existing).count()
                self.say(f"  {slug:<12} already seeded, left alone   {count} referral(s)")
                continue
            name, case, count = build()
            self.say(f"  {name:<26} {count} referral(s)  /cases/{case.id}")

        self.say("")
        self.say(self.style.SUCCESS(f"Demo cases ready for {self.case_manager.username}."))

    # -- helpers -----------------------------------------------------------

    def say(self, message):
        if not self.quiet:
            self.stdout.write(message)

    def pick_user(self, role):
        return User.objects.filter(role=role, is_active=True).order_by("username").first()

    def day(self, offset: int) -> date:
        """A date `offset` days from today; offsets are negative, into the past."""
        return self.today + timedelta(days=offset)

    def partner(self, name: str) -> Partner:
        try:
            return self.partners[name]
        except KeyError:
            raise CommandError(f"No active partner named {name!r}.")

    def category(self, code: str) -> ReferralCategory:
        return ReferralCategory.objects.get(code=code)

    def delete_demo_records(self):
        cases = Case.objects.filter(id__in=[demo_id("case", slug) for slug in SCENARIO_SLUGS])
        referrals = Referral.objects.filter(case__in=cases).count()
        # Youth is PROTECTed by Case, so the case has to go first.
        youth_ids = list(cases.values_list("youth_id", flat=True))
        removed = cases.count()
        cases.delete()
        Youth.objects.filter(id__in=youth_ids).delete()
        self.say(self.style.WARNING(f"Removed {removed} demo case(s) and {referrals} referral(s)."))

    def make_case(self, slug: str, full_name: str, opened_offset: int) -> Case:
        """A youth and their case, both with ids derived from the scenario slug."""
        youth, _ = Youth.objects.update_or_create(
            id=demo_id("youth", slug),
            defaults={
                "full_name": full_name,
                "sex": Sex.FEMALE if slug in FEMALE_SCENARIOS else Sex.MALE,
                # Mid-band, so the age check has nothing to say about it.
                "date_of_birth": self.day(-22 * 365),
                "region": "Oromia",
                "zone": "East Shewa",
                "woreda": "Adama",
                "kebele": "Adama 01",
                "consent_given": True,
                "consent_date": self.day(opened_offset - 1),
                "registering_worker": self.outreach_worker,
            },
        )
        case, _ = Case.objects.update_or_create(
            id=demo_id("case", slug),
            defaults={
                "youth": youth,
                "case_manager": self.case_manager,
                "opened_date": self.day(opened_offset),
                "next_action": DEMO_NOTE,
            },
        )
        return case

    def profile_and_assign(self, case, pathway, day, revise_to=None, revise_day=None):
        """Give the case the §4.3 profiling and §4.4 pathway a real one would have.

        Without these the case screen has no pathway to show and the goal panel
        counts a journey that never left step one, which makes the demo look
        like a bug rather than like a case.
        """
        ProfilingRecord.objects.create(
            case=case,
            work_history_summary="Casual farm labour, no formal employment.",
            skills_list=["Basic literacy", "Numeracy"],
            eligibility_flags=[pathway],
            assessed_date=self.day(day),
            assessor=self.case_manager,
        )
        assignment = PathwayAssignment.objects.create(
            case=case,
            selected_pathway=pathway,
            assessed_interests="Wants a trade with local demand.",
            capacities="Completed grade 10.",
            barriers="No transport from kebele; limited tools.",
            assessment_date=self.day(day),
            assessor=self.case_manager,
            is_current=True,
        )
        case.current_pathway_assignment = assignment
        case.save(update_fields=["current_pathway_assignment", "updated_at"])

        # One case carries a revision so the §9 rationale trail has something in
        # it — the history is the part the pathway card exists to show.
        if revise_to:
            assignment.revise(
                selected_pathway=revise_to,
                assessor=self.case_manager,
                revision_reason="TVET place fell through; youth redirected to wage employment.",
                assessment_date=self.day(revise_day),
            )
        return assignment

    def initiate(self, case, category_code, partner_name, day):
        return services.initiate_referral(
            case=case,
            referral_category=self.category(category_code),
            receiving_partner=self.partner(partner_name),
            initiated_by=self.case_manager,
            initiated_date=self.day(day),
            notes=DEMO_NOTE,
        )

    def confirm(self, referral, day):
        referral.transition_to(
            ReferralStatus.ACTIVE,
            actor=self.case_manager,
            confirmed_date=self.day(day),
            confirmed_by="Demo partner focal point",
        )
        return referral

    def complete(self, referral, outcome_code, day):
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=self.case_manager,
            outcome_type=OutcomeType.objects.get(code=outcome_code),
            outcome_date=self.day(day),
            outcome_verification_method="Follow-up visit",
        )
        return referral

    def fail(self, referral, reason_code, day):
        referral.transition_to(
            ReferralStatus.FAILED,
            actor=self.case_manager,
            failure_reason_code=FailureReasonCode.objects.get(code=reason_code),
            failure_date=self.day(day),
        )
        return referral

    def cancel(self, referral, day):
        referral.transition_to(ReferralStatus.CANCELLED, actor=self.case_manager)
        # §6.2 stamps no date on a withdrawal, so the timeline closes a Cancelled
        # bar at updated_at. That field is auto_now, hence the queryset update —
        # a save() would overwrite it with now() again.
        Referral.objects.filter(pk=referral.pk).update(
            updated_at=timezone.make_aware(datetime.combine(self.day(day), time(9, 0)))
        )
        return referral

    def onward(self, parent, category_code, partner_name, day):
        return services.create_onward_referral(
            parent=parent,
            referral_category=self.category(category_code),
            receiving_partner=self.partner(partner_name),
            initiated_by=self.case_manager,
            initiated_date=self.day(day),
            notes=DEMO_NOTE,
        )

    def replace(self, failed, category_code, partner_name, day):
        return services.create_replacement_referral(
            failed_referral=failed,
            referral_category=self.category(category_code),
            receiving_partner=self.partner(partner_name),
            initiated_by=self.case_manager,
            initiated_date=self.day(day),
            notes=DEMO_NOTE,
        )

    def settle(self, case, last_activity_offset):
        """Leave the case looking as old as its referrals.

        `Case.touch()` has stamped today on every transition above. Left that
        way, a case whose last real event was five months ago would read as
        active this morning, and the §4.13 stall detection would never see it.
        """
        Case.objects.filter(pk=case.pk).update(last_activity_date=self.day(last_activity_offset))
        return case

    # -- scenarios ---------------------------------------------------------

    def sequential_chain(self):
        """Completed training, then the onward referral it prompted. No parallel, no failure."""
        case = self.make_case("sequential", "Marta Girma", -170)
        self.profile_and_assign(case, Pathway.TRAINING, -165, revise_to=Pathway.WAGE_EMPLOYMENT, revise_day=-112)
        first = self.initiate(case, "TRAINING", "Adama Polytechnic College", -150)
        self.confirm(first, -146)
        self.complete(first, "TRAINING_COMPLETION", -110)
        second = self.onward(first, "EMPLOYMENT", "Bishoftu Automotive Plc", -105)
        self.confirm(second, -99)
        self.settle(case, -99)
        return ("Sequential chain", case, 2)

    def parallel_pair(self):
        """Two concurrent referrals, plus an exempt third stream (§6.3)."""
        case = self.make_case("parallel", "Hanna Wolde", -140)
        self.profile_and_assign(case, Pathway.SELF_EMPLOYMENT, -135)
        training = self.initiate(case, "TRAINING", "Adama Skills Hub", -120)
        self.confirm(training, -115)
        finance = self.initiate(case, "FINANCE_ACCESS", "Oromia Credit and Savings", -100)
        # Confirming this one while training is Active is what opens the group.
        self.confirm(finance, -96)
        # Complementary Service sits outside the cap, so it runs alongside both
        # without joining their bracket — the §11 working default, visible.
        support = self.initiate(case, "COMPLEMENTARY_SERVICE", "Adama Health Centre", -80)
        self.confirm(support, -78)
        self.settle(case, -78)
        return ("Parallel pair + exempt", case, 3)

    def failure_and_replacement(self):
        """A failed referral, its replacement, and the replacement's outcome."""
        case = self.make_case("replacement", "Yonas Alemu", -180)
        self.profile_and_assign(case, Pathway.TRAINING, -175)
        failed = self.initiate(case, "TRAINING", "Adama Skills Hub", -160)
        self.confirm(failed, -155)
        self.fail(failed, "PARTNER_CAPACITY", -120)
        replacement = self.replace(failed, "TRAINING", "Adama Polytechnic College", -118)
        self.confirm(replacement, -112)
        self.complete(replacement, "TRAINING_COMPLETION", -60)
        self.settle(case, -60)
        return ("Failure and replacement", case, 2)

    def three_onward_hops(self):
        """The long chain: training to apprenticeship to employment, over ~7 months."""
        case = self.make_case("onward3", "Selam Bekele", -230)
        self.profile_and_assign(case, Pathway.TRAINING, -225, revise_to=Pathway.APPRENTICESHIP, revise_day=-168)
        first = self.initiate(case, "TRAINING", "Adama Skills Hub", -200)
        self.confirm(first, -196)
        self.complete(first, "TRAINING_COMPLETION", -170)
        second = self.onward(first, "APPRENTICESHIP", "Bishoftu Automotive Plc", -165)
        self.confirm(second, -160)
        self.complete(second, "APPRENTICESHIP_START", -120)
        third = self.onward(second, "EMPLOYMENT", "Rift Valley Enterprise Agency", -115)
        self.confirm(third, -110)
        self.settle(case, -110)
        return ("Three onward hops", case, 3)

    def pending_and_cancelled(self):
        """The two quiet statuses: one withdrawn, one still waiting on a partner."""
        case = self.make_case("mixed", "Tigist Haile", -60)
        self.profile_and_assign(case, Pathway.WAGE_EMPLOYMENT, -55)
        withdrawn = self.initiate(case, "MARKET_LINKAGE", "Rift Valley Enterprise Agency", -45)
        self.cancel(withdrawn, -40)
        # Left in Pending Confirmation: the partner has not answered yet.
        self.initiate(case, "EMPLOYMENT", "Bishoftu Automotive Plc", -5)
        self.settle(case, -5)
        return ("Pending and cancelled", case, 2)

    def no_referrals_yet(self):
        """A case with nothing on it, for the empty state."""
        case = self.make_case("empty", "Bereket Assefa", -10)
        self.settle(case, -10)
        return ("No referrals yet", case, 0)


SCENARIO_SLUGS = ["sequential", "parallel", "replacement", "onward3", "mixed", "empty"]
FEMALE_SCENARIOS = {"sequential", "parallel", "onward3", "mixed"}
