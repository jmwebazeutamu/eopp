"""Seed a pilot-scale dataset so the dashboards and the reporting layer are testable.

`seed_demo_referrals` builds six hand-shaped cases for the §6.4 timeline. That is
the right size to look at and the wrong size to measure: the case manager
dashboard is specified against a caseload of 80-200 (CASE_MANAGER_DASHBOARD.md
§2), its acceptance criteria name 1,000 youth and 3,000 referrals, and the
reporting layer's suppression bands only do anything once denominators clear 10
and 30. On fourteen youth every rate on the programme dashboard is suppressed,
which is correct but proves nothing.

So this builds the pilot as described in spec §1: 500-1,000 youth across the
seeded woredas, with cases, referrals, outcomes and alerts distributed the way a
year of operation would leave them.

    python manage.py seed_pilot_scale                # ~600 youth
    python manage.py seed_pilot_scale --youth 1000   # the acceptance-criteria size
    python manage.py seed_pilot_scale --refresh      # delete and rebuild
    python manage.py seed_pilot_scale --reset        # delete only

Every referral goes through `services.initiate_referral` and
`Referral.transition_to`, so the §6.2 table, the §6.3 cap and the parallel-group
stamping are the application's, not this file's. Only the dates are ours — they
are backdated so cohorts, maturation windows and stall thresholds have something
to bite on.

Deterministic: names, dates and outcomes derive from a seeded `Random`, and ids
from `uuid5`, so two runs of the same size produce the same database and a
`--refresh` keeps the same URLs.

Development data only. It writes youth and case records, so it refuses unless
DEBUG is on or --i-know-this-is-not-production is passed.
"""

import random
import uuid
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.alerts.models import Alert, AlertStatus
from apps.cases.models import Case, CaseStatus, Pathway, PathwayAssignment, ProfilingRecord
from apps.partners.models import Partner
from apps.referrals import services
from apps.referrals.models import Referral, ReferralStatus, VerificationSource
from apps.referrals.taxonomy import FailureReasonCode, OutcomeType, ReferralCategory
from apps.users.models import Role, User
from apps.youth.models import DisabilityStatus, EducationLevel, PsnpStatus, SettlementType, Sex, Youth

PILOT_NAMESPACE = uuid.UUID("2b1f6a30-7c44-4b0e-9b2f-5f3a1d9c8e77")
PILOT_NOTE = "Pilot-scale seed data."

# Amharic and Oromo given names in Latin transcription, as the register would
# carry them. Enough combinations that duplicate names are rare rather than
# impossible — the import's duplicate detection should have something to find.
FIRST = [
    "Abebe",
    "Almaz",
    "Bekele",
    "Bontu",
    "Chaltu",
    "Dawit",
    "Ebisa",
    "Fikadu",
    "Genet",
    "Hawi",
    "Ibrahim",
    "Kalkidan",
    "Lensa",
    "Meseret",
    "Nardos",
    "Obsa",
    "Rahel",
    "Sisay",
    "Tigist",
    "Yonas",
    "Zewditu",
    "Gadisa",
    "Hirut",
    "Tolosa",
    "Selam",
    "Birhanu",
    "Alemitu",
    "Dereje",
    "Feven",
    "Girma",
]
LAST = [
    "Tesfaye",
    "Bekele",
    "Alemu",
    "Girma",
    "Haile",
    "Wondimu",
    "Deressa",
    "Roba",
    "Mekonnen",
    "Jemal",
    "Assefa",
    "Gutema",
    "Nagawo",
    "Dinku",
    "Feyisa",
    "Kebede",
    "Abera",
    "Tadesse",
    "Regassa",
    "Bulti",
]

EDUCATION = [c for c in EducationLevel.values]
DISABILITY = [DisabilityStatus.NONE] * 12 + [
    DisabilityStatus.PHYSICAL,
    DisabilityStatus.VISUAL,
    DisabilityStatus.HEARING,
    DisabilityStatus.UNDISCLOSED,
]
PSNP = [PsnpStatus.ENROLLED] * 6 + [PsnpStatus.GRADUATED] * 3 + [PsnpStatus.NOT_PSNP]
# OQ-11. Weighted rural because PSNP's caseload is; a blank share is kept so the
# "Not recorded" row on the disaggregation is exercised rather than assumed away.
SETTLEMENT = [SettlementType.RURAL] * 6 + [SettlementType.PERI_URBAN] * 2 + [SettlementType.URBAN] * 2 + [""]


def pilot_id(*parts):
    return uuid.uuid5(PILOT_NAMESPACE, ":".join(str(p) for p in parts))


class Command(BaseCommand):
    help = "Seed a pilot-scale youth/case/referral dataset for dashboard and reporting testing."

    def add_arguments(self, parser):
        parser.add_argument("--youth", type=int, default=600, help="How many youth to register (default 600).")
        parser.add_argument(
            "--woredas",
            nargs="+",
            help="Woredas to register into. Defaults to the pilot sites named in the design brief.",
        )
        parser.add_argument("--seed", type=int, default=20260817, help="RNG seed; same seed, same database.")
        parser.add_argument("--reset", action="store_true", help="Delete the pilot records and stop.")
        parser.add_argument("--refresh", action="store_true", help="Delete the pilot records, then rebuild.")
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

        self.quiet = options["verbosity"] == 0
        self.today = date.today()
        self.rng = random.Random(options["seed"])
        self.requested_woredas = options.get("woredas")

        if options["reset"] or options["refresh"]:
            self.delete_pilot_records()
            if options["reset"]:
                return

        self.youth_count = options["youth"]
        self.load_reference_data()

        count = self.youth_count
        self.say(f"Seeding {count} youth across {', '.join(self.woredas)} …")

        youth = self.make_youth(count)
        self.say(f"  youth              {len(youth)}")

        cases = self.make_cases(youth)
        self.say(f"  cases              {len(cases)}")

        referrals = self.make_referrals(cases)
        self.say(f"  referrals          {referrals}")

        self.settle()

        alerts = self.make_alerts(cases)
        self.say(f"  open alerts        {alerts}")

        self.say("")
        self.say(self.style.SUCCESS("Pilot-scale data ready."))
        self.say(f"  case manager dashboard:  /dashboard/  (as {self.case_managers[0].username})")
        self.say("  programme dashboard:     /api/v1/dashboard/")

    # -- reference data ----------------------------------------------------

    def load_reference_data(self):
        from apps.locations.models import Location

        available = list(Location.objects.active().woredas().values_list("name", flat=True).order_by("name"))
        if not available:
            raise CommandError("No woredas. Run `manage.py seed_locations` first.")

        # The design brief names three live sites. Seeding into all twelve
        # reference woredas would leave a case manager assigned to cases in
        # woredas nobody covers, and a supervisor's woreda filter matching a
        # handful of rows — realistic-looking data that models nothing real.
        wanted = self.requested_woredas or [w for w in ("Adama", "Bishoftu", "Lume") if w in available]
        self.woredas = [w for w in wanted if w in available] or available[:3]

        # region/zone per woreda, so the youth serializer's chain check would pass.
        self.chain = {}
        for woreda in Location.objects.active().woredas().select_related("parent__parent"):
            self.chain[woreda.name] = (woreda.parent.parent.name, woreda.parent.name)

        self.categories = list(ReferralCategory.objects.filter(is_active=True))
        self.outcomes = {o.code: o for o in OutcomeType.objects.all()}
        self.failures = list(FailureReasonCode.objects.filter(is_active=True))
        if not self.categories or not self.outcomes:
            raise CommandError("No referral taxonomy. Run `manage.py seed_referral_taxonomy` first.")

        self.partners = list(Partner.objects.filter(active_status=True))
        if len(self.partners) < 3:
            raise CommandError("Needs at least three active partners.")

        self.case_managers = list(User.objects.filter(role=Role.CASE_MANAGER, is_active=True).order_by("username"))
        if not self.case_managers:
            raise CommandError("No case managers. Seed users first.")

        # The dashboard is specified against a caseload of 80-200
        # (CASE_MANAGER_DASHBOARD.md §2), and the supervisor tier compares one
        # case manager with another. One account holding every case tests
        # neither. Top up to enough accounts to spread the intake.
        wanted = max(1, -(-self.youth_count // 150))
        for index in range(len(self.case_managers), wanted):
            self.case_managers.append(
                User.objects.create_user(
                    f"cm{index + 1}",
                    "pw-Seeded-12345",
                    full_name=f"Case Manager {'One Two Three Four Five Six'.split()[index % 6]}",
                    role=Role.CASE_MANAGER,
                    woreda_assignment=self.woredas,
                )
            )
        self.outreach = (
            User.objects.filter(role=Role.OUTREACH_WORKER, is_active=True).order_by("username").first()
            or self.case_managers[0]
        )

        # Which outcomes each category actually accepts (§5.3), so completions
        # never trip the applicability check.
        self.outcomes_for = {}
        for category in self.categories:
            valid = [o for o in self.outcomes.values() if o.is_valid_for(category)]
            self.outcomes_for[category.pk] = valid

    # -- youth -------------------------------------------------------------

    def make_youth(self, count):
        existing = {y.id: y for y in Youth.objects.filter(id__in=[pilot_id("youth", i) for i in range(count)])}
        rows = []
        for index in range(count):
            youth_id = pilot_id("youth", index)
            if youth_id in existing:
                rows.append(existing[youth_id])
                continue

            woreda = self.woredas[index % len(self.woredas)]
            region, zone = self.chain[woreda]
            # Registration spread over the last 18 months, so cohorts and
            # maturation windows have a range to work with.
            registered = self.today - timedelta(days=self.rng.randint(20, 540))
            age = self.rng.randint(15, 29)
            rows.append(
                Youth(
                    id=youth_id,
                    full_name=f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}",
                    sex=self.rng.choice([Sex.FEMALE, Sex.FEMALE, Sex.MALE, Sex.MALE, Sex.OTHER]),
                    date_of_birth=self.today - timedelta(days=365 * age + self.rng.randint(0, 364)),
                    phone_number=f"09{self.rng.randint(10_000_000, 99_999_999)}",
                    national_or_kebele_id=f"YE-{index:05d}",
                    region=region,
                    zone=zone,
                    woreda=woreda,
                    kebele=f"{woreda} {self.rng.randint(1, 12):02d}",
                    settlement_type=self.rng.choice(SETTLEMENT),
                    household_id=f"PSNP-{self.rng.randint(10000, 99999)}",
                    psnp_status=self.rng.choice(PSNP),
                    education_level=self.rng.choice(EDUCATION),
                    disability_status=self.rng.choice(DISABILITY),
                    consent_given=True,
                    consent_date=registered,
                    registration_date=registered,
                    registering_worker=self.outreach,
                )
            )

        fresh = [row for row in rows if row.id not in existing]
        # bulk_create skips save() and therefore simple-history. Acceptable for
        # seed data at this volume — 600 history rows per entity would treble the
        # seed time and the audit trail of fabricated records has no value.
        # `registration_date` is auto_now_add. The INSERT stamps every row with
        # today AND writes today back onto the in-memory instance, so the
        # intended dates have to be kept aside here — reading them off the
        # objects after bulk_create returns today, and the whole seed collapses
        # to a single day: no case old enough to stall, and every "median days
        # in stage" on the pipeline card is 0.
        intended = {row.id: row.registration_date for row in fresh}

        Youth.objects.bulk_create(fresh, batch_size=200)

        # auto_now_add fires only on insert, so a follow-up UPDATE sticks.
        for row in fresh:
            row.registration_date = intended[row.id]
        if fresh:
            Youth.objects.bulk_update(fresh, ["registration_date"], batch_size=200)
        return rows

    # -- cases -------------------------------------------------------------

    def make_cases(self, youth):
        """Roughly 85% of registered youth get a case, the rest are the backlog."""
        existing = set(Case.objects.filter(youth__in=youth).values_list("youth_id", flat=True))
        cases, profiles, pathways = [], [], []
        self.intent = {}

        for index, person in enumerate(youth):
            if person.id in existing or self.rng.random() > 0.85:
                continue

            opened = person.registration_date + timedelta(days=self.rng.randint(1, 25))
            if opened > self.today:
                opened = self.today
            manager = self.case_managers[index % len(self.case_managers)]
            age_days = (self.today - opened).days

            # Status is conditioned on how long the case has existed. A case
            # opened last week cannot be Stalled — the threshold is 30 days —
            # and seeding one produces a case the §4.13 detector will never
            # raise an alert for. That is how the first version of this command
            # quietly seeded an empty alert inbox.
            statuses = [CaseStatus.ACTIVE, CaseStatus.REFERRAL_PENDING, CaseStatus.PLACED, CaseStatus.EXITED]
            weights = [46, 18, 16, 8]
            if age_days >= settings.STALL_ALERT_THRESHOLD_DAYS + 10:
                statuses.insert(2, CaseStatus.STALLED)
                weights.insert(2, 12)
            status = self.rng.choices(statuses, weights=weights)[0]
            closed = None
            if status == CaseStatus.EXITED:
                closed = opened + timedelta(days=self.rng.randint(40, 300))
                if closed > self.today:
                    closed = self.today
            # A stalled case is quiet by construction — that is what makes the
            # at-risk list and the §4.13 stall alerts non-empty. It can never be
            # quiet for longer than it has existed, and it must never open before
            # its youth registered: backdating it to carry the silence produced
            # cases older than their own youth, which made every "days in stage"
            # median negative and then zero.
            if status == CaseStatus.STALLED:
                quiet_days = self.rng.randint(settings.STALL_ALERT_THRESHOLD_DAYS + 5, min(120, age_days))
            else:
                quiet_days = self.rng.randint(0, min(25, age_days)) if age_days else 0

            case = Case(
                id=pilot_id("case", str(person.id)),
                youth=person,
                case_manager=manager,
                woreda=person.woreda,
                case_status=status,
                opened_date=opened,
                closed_date=closed,
                exit_reason="Programme complete" if closed else "",
                last_activity_date=self.today - timedelta(days=quiet_days),
                next_action=self.rng.choice(
                    [
                        "Call to confirm training start",
                        "Chase partner confirmation",
                        "Home visit",
                        "Verify placement outcome",
                        "",
                    ]
                ),
            )
            cases.append(case)
            # Remembered, not trusted: `transition_to` stamps the case's status
            # and last_activity_date every time a referral moves (§4.2), so
            # anything written here is overwritten as soon as make_referrals
            # runs. The intent is re-applied in settle() once the referral
            # history exists.
            self.intent[case.id] = (status, quiet_days, closed)
            profiles.append(
                ProfilingRecord(
                    id=pilot_id("profile", str(person.id)),
                    case=case,
                    work_history_summary="Seasonal farm labour",
                    vulnerability_index_score=round(self.rng.uniform(0.1, 0.95), 2),
                    priority_flag=self.rng.random() < 0.18,
                    assessed_date=opened,
                    assessor=manager,
                )
            )
            pathways.append(
                PathwayAssignment(
                    id=pilot_id("pathway", str(person.id)),
                    case=case,
                    selected_pathway=self.rng.choice(list(Pathway.values)),
                    assessment_date=opened,
                    assessor=manager,
                    is_current=True,
                )
            )

        Case.objects.bulk_create(cases, batch_size=200)
        ProfilingRecord.objects.bulk_create(profiles, batch_size=200)
        PathwayAssignment.objects.bulk_create(pathways, batch_size=200)
        return list(Case.objects.filter(youth__in=youth).select_related("youth"))

    # -- referrals ---------------------------------------------------------

    def make_referrals(self, cases):
        """Zero to three referrals per case, driven to a realistic mix of states.

        Through the domain services, so every row is one the application would
        have produced. That is slower than bulk_create by a wide margin and it is
        the point: a seed that bypasses `transition_to` cannot exercise the §6.2
        table, and the dashboards are only worth testing against rows the state
        machine actually allows.
        """
        made = 0
        for case in cases:
            if Referral.objects.filter(case=case).exists():
                continue
            how_many = self.rng.choices([0, 1, 2, 3], weights=[15, 40, 30, 15])[0]
            for _ in range(how_many):
                made += self.one_referral(case)
        return made

    def one_referral(self, case):
        category = self.rng.choice(self.categories)
        initiated = case.opened_date + timedelta(days=self.rng.randint(2, 60))
        if initiated > self.today:
            initiated = self.today

        referral = services.initiate_referral(
            case=case,
            referral_category=category,
            receiving_partner=self.rng.choice(self.partners),
            initiated_by=case.case_manager,
            initiated_date=initiated,
            notes=PILOT_NOTE,
        )

        roll = self.rng.random()
        age = (self.today - initiated).days

        # Only a *recent* referral is plausibly still awaiting a decision. The
        # first version of this left 14% pending regardless of age and produced
        # referrals waiting 513 days, which reads as a broken state machine
        # rather than as a backlog.
        if roll < 0.14 and age <= 45:
            return 1  # still pending — the "awaiting partner" queue

        confirmed = min(initiated + timedelta(days=self.rng.randint(0, 21)), self.today)
        if roll < 0.22:
            referral.transition_to(ReferralStatus.CANCELLED, actor=case.case_manager, notes="Youth withdrew.")
            return 1

        try:
            # OQ-1. Most confirmed referrals see the youth turn up, some weeks
            # later; the ones that do not are the largest loss in the pipeline.
            attended = None
            if self.rng.random() < 0.72:
                attended = min(confirmed + timedelta(days=self.rng.randint(3, 60)), self.today)
            referral.transition_to(
                ReferralStatus.ACTIVE,
                actor=case.case_manager,
                confirmed_date=confirmed,
                service_start_date=attended,
            )
        except Exception:
            # The §6.3 parallel cap refused it. Queued behind the cap is a real
            # state — but only briefly. A case manager withdraws one that has sat
            # there for months rather than leaving it pending for a year, which
            # is what produced 472-day waits in the first version of this seed.
            if age > 45:
                referral.transition_to(
                    ReferralStatus.CANCELLED, actor=case.case_manager, notes="Withdrawn: blocked behind the cap."
                )
            return 1

        if roll < 0.55:
            return 1  # active, still running

        closed = min(confirmed + timedelta(days=self.rng.randint(10, 150)), self.today)
        if roll < 0.78:
            # §5.3 admits one specific outcome per category plus "Other", so
            # choosing uniformly made "Other" half of every completed referral —
            # which is a reporting failure, not a distribution. Weighted so the
            # specific outcome dominates and Other stays the exception it is
            # meant to be.
            valid = self.outcomes_for.get(category.pk) or list(self.outcomes.values())
            specific = [o for o in valid if o.code != "OTHER"] or valid
            outcome = self.rng.choice(specific) if self.rng.random() < 0.9 else self.rng.choice(valid)
            referral.transition_to(
                ReferralStatus.COMPLETED,
                actor=case.case_manager,
                outcome_type=outcome,
                outcome_date=closed,
                outcome_verification_method=self.rng.choice(
                    ["Employer confirmation", "Provider register", "Self-reported"]
                ),
                # OQ-2. Weighted toward external verification, but with enough
                # self-reported rows that the verified-subset headline differs
                # from the raw count — which is the point of carrying both.
                verification_source=self.rng.choices(
                    [
                        VerificationSource.EMPLOYER_CONFIRMED,
                        VerificationSource.PROVIDER_CONFIRMED,
                        VerificationSource.DOCUMENT_VERIFIED,
                        VerificationSource.SELF_REPORTED,
                    ],
                    weights=[25, 35, 15, 25],
                )[0],
            )
        else:
            referral.transition_to(
                ReferralStatus.FAILED,
                actor=case.case_manager,
                failure_reason_code=self.rng.choice(self.failures),
                failure_date=closed,
            )
        return 1

    def settle(self):
        """Re-apply the intended status and quiet date, after the referrals.

        Written with `update()` rather than `save()` on purpose: `save()` is what
        maintains `last_activity_date`, and the whole point here is to backdate
        it past what the engine just stamped. This is the one place the seed
        deliberately goes around the domain layer, and it is why it is a separate
        pass with its own name rather than a quiet kwarg somewhere.
        """
        settled = 0
        for case_id, (status, quiet_days, closed) in self.intent.items():
            settled += Case.objects.filter(id=case_id).update(
                case_status=status,
                closed_date=closed,
                last_activity_date=self.today - timedelta(days=quiet_days),
            )
        return settled

    # -- alerts ------------------------------------------------------------

    def make_alerts(self, cases):
        """Run the real detection jobs rather than inventing alert rows.

        §4.13's jobs are the definition of what an alert is; a hand-written row
        could describe a state the detectors would never produce, and the
        dashboard's first card is built entirely out of them.
        """
        from apps.alerts.tasks import run_all_detections

        run_all_detections()

        # The detectors do not assign; CM-1 shows alerts assigned to *me*, so
        # route each one to the case's own manager.
        unassigned = Alert.objects.filter(status=AlertStatus.OPEN, assigned_to__isnull=True).select_related("case")
        for alert in unassigned:
            alert.assigned_to = alert.case.case_manager
        Alert.objects.bulk_update(unassigned, ["assigned_to"], batch_size=200)
        return Alert.objects.filter(status=AlertStatus.OPEN).count()

    # -- teardown ----------------------------------------------------------

    def delete_pilot_records(self):
        youth = Youth.objects.filter(national_or_kebele_id__startswith="YE-")
        cases = Case.objects.filter(youth__in=youth)
        counts = (
            Referral.objects.filter(case__in=cases).count(),
            cases.count(),
            youth.count(),
        )
        Alert.objects.filter(case__in=cases).delete()
        Referral.objects.filter(case__in=cases).update(parent_referral=None, replacement_referral=None)
        Referral.objects.filter(case__in=cases).delete()
        ProfilingRecord.objects.filter(case__in=cases).delete()
        PathwayAssignment.objects.filter(case__in=cases).delete()
        cases.delete()
        youth.delete()
        self.say(f"Deleted {counts[0]} referrals, {counts[1]} cases, {counts[2]} youth.")

    def say(self, message):
        if not self.quiet:
            self.stdout.write(message)
