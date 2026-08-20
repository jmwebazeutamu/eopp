"""Demo training and placement records — development only.

Built onto the cases `seed_demo_referrals` and `seed_pilot_scale` already
produce, because a placement with no case behind it demonstrates nothing. Every
shape the two new screens have to draw:

| Shape | Why it is here |
|---|---|
| Training running, past its end date | The trainer's queue sorts on it |
| Training completed, no onward referral | Raises the §4.5 onward prompt |
| Training dropped out, with a reason | The reason is the whole record |
| Failed assessment | Not a dropout, and the rate has to show that |
| Placement, all three checks answered retained | The reportable retention figure |
| Placement, checks overdue | The employer liaison's queue and the reminder |
| Placement exited for a better job | An exit that is a success |
| Placement exited dismissed | An exit that is not |
| Subsidised placement | Excluded from the reported anchor (OQ-3) |

Everything goes through `services`, so the rows are the ones the application
would produce; only the dates are seeded.
"""

import random
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cases.models import Case
from apps.partners.models import Partner, PartnerType
from apps.placements import services as placement_services
from apps.placements.models import ExitReason, Placement, PlacementType, RetentionStatus
from apps.referrals import services as referral_services
from apps.referrals.taxonomy import ReferralCategory
from apps.training import services as training_services
from apps.training.models import CertificateStatus, TrainingEnrolment, TrainingType
from apps.users.models import AccountStatus, Role, User

TRADES = ["Carpentry", "Welding", "Garment making", "Food processing", "Motorcycle repair"]
EMPLOYERS = [
    ("Adama Textiles", "Manufacturing"),
    ("Bishoftu Foods", "Agro-processing"),
    ("Rift Valley Logistics", "Transport"),
    ("Lume Construction", "Construction"),
]


class Command(BaseCommand):
    help = "Seed demonstration training enrolments and placements. Development only."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Delete the demo rows and rebuild them.")
        parser.add_argument("--reset", action="store_true", help="Delete the demo rows and stop.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off.")
        parser.add_argument("--seed", type=int, default=5, help="Random seed. Same seed, same database.")

    @transaction.atomic
    def handle(self, *args, **options):
        # The same guard the other demo seeders carry: this writes case data.
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to run with DEBUG off. Pass --force if this really is a demo environment.")

        random.seed(options["seed"])

        if options["refresh"] or options["reset"]:
            trainings = TrainingEnrolment.objects.filter(notes__startswith="[demo]").count()
            placements = Placement.objects.filter(notes__startswith="[demo]").count()
            TrainingEnrolment.objects.filter(notes__startswith="[demo]").delete()
            Placement.objects.filter(notes__startswith="[demo]").delete()
            self.stdout.write(f"  removed {trainings} training enrolment(s) and {placements} placement(s).")
            if options["reset"]:
                return

        cases = list(Case.objects.select_related("youth").order_by("opened_date")[:40])
        if len(cases) < 12:
            raise CommandError(
                "Not enough cases to demonstrate against. Run seed_demo_referrals or seed_pilot_scale first."
            )

        trainer = self._user("trainer1", "Hana Girma", Role.TRAINER)
        liaison = self._user("liaison1", "Yonas Tesfaye", Role.EMPLOYER_LIAISON)
        provider = self._provider("Adama Polytechnic College", PartnerType.TVET_INSTITUTION)
        employer_partner = self._provider("Adama Textiles", PartnerType.EMPLOYER)

        trainings = self._seed_trainings(cases[:12], provider, trainer)
        placements = self._seed_placements(cases[12:24], liaison)

        self.stdout.write(
            self.style.SUCCESS(f"Sprint 5 demo seeded: {trainings} training enrolment(s), {placements} placement(s).")
        )
        self.stdout.write(f"  Trainer: {trainer.username}   Employer liaison: {liaison.username}")
        self.stdout.write(f"  Employer partner on file: {employer_partner.partner_name}")
        self.stdout.write(
            "  Raise the reminders with: manage.py shell -c "
            "'from apps.alerts import tasks; tasks.run_all_detections()'"
        )

    # -- scaffolding ------------------------------------------------------

    def _user(self, username, full_name, role):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "full_name": full_name,
                "role": role,
                "account_status": AccountStatus.ACTIVE,
                "woreda_assignment": ["Adama", "Bishoftu"],
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _provider(self, name, partner_type):
        provider, _created = Partner.objects.get_or_create(
            partner_name=name,
            partner_type=partner_type,
            defaults={
                "woreda_coverage": ["Adama", "Bishoftu", "Lume"],
                "contact_name": "Registrar",
                "phone": "+251911000200",
                "email": "registrar@example.et",
            },
        )
        return provider

    def _case_suffix(self, case, ordinal):
        return f"{case.youth.full_name} · {str(case.pk)[:8]} · {ordinal + 1}"

    # -- training ---------------------------------------------------------

    def _seed_trainings(self, cases, provider, trainer):
        training_category = ReferralCategory.objects.get(code="TRAINING")
        shapes = [
            "running",
            "running",
            "overdue",
            "completed",
            "completed",
            "completed_certificate",
            "dropped",
            "dropped",
            "failed",
            "running",
            "completed",
            "overdue",
        ]
        made = 0
        for case, shape in zip(cases, shapes, strict=False):
            training_type = TrainingType.TVET if made % 2 else TrainingType.LIFE_SKILLS
            start = date.today() - timedelta(days=random.randint(40, 160))
            end = start + timedelta(days=90)
            label = self._case_suffix(case, made)
            referral = referral_services.initiate_referral(
                case=case,
                referral_category=training_category,
                receiving_partner=provider,
                initiated_by=case.case_manager,
                notes=f"[demo] source referral for training enrolment · {label}",
            )

            enrolment = training_services.enrol(
                case=case,
                training_type=training_type,
                training_provider=provider,
                start_date=start,
                end_date=end if shape != "overdue" else date.today() - timedelta(days=15),
                recorded_by=trainer,
                trade_or_skill_area=random.choice(TRADES) if training_type == TrainingType.TVET else "",
                attendance_rate=random.choice([72.0, 84.5, 91.0, 96.5]),
                source_referral=referral,
                notes=f"[demo] seeded by seed_demo_sprint5 · {label}",
            )

            if shape.startswith("completed"):
                training_services.complete(
                    enrolment,
                    completion_date=end,
                    assessment_result="Pass",
                    certificate_status=(
                        CertificateStatus.AWARDED if shape == "completed_certificate" else CertificateStatus.PENDING
                    ),
                )
            elif shape == "dropped":
                training_services.drop_out(
                    enrolment,
                    reason=random.choice(
                        [
                            "Moved to another woreda for family reasons.",
                            "Could not meet the transport cost to the centre.",
                        ]
                    ),
                    dropout_date=start + timedelta(days=30),
                )
            elif shape == "failed":
                training_services.fail_assessment(
                    enrolment,
                    assessment_result="Did not reach the pass mark on the practical assessment.",
                    completion_date=end,
                )
            made += 1
        return made

    # -- placements -------------------------------------------------------

    def _seed_placements(self, cases, liaison):
        employment_category = ReferralCategory.objects.get(code="EMPLOYMENT")
        apprenticeship_category = ReferralCategory.objects.get(code="APPRENTICESHIP")
        shapes = [
            "retained",
            "retained",
            "retained_subsidised",
            "checks_overdue",
            "checks_overdue",
            "partly_checked",
            "exited_better_job",
            "exited_dismissed",
            "exited_contract",
            "unreachable",
            "recent",
            "retained",
        ]
        made = 0
        for case, shape in zip(cases, shapes, strict=False):
            employer, sector = EMPLOYERS[made % len(EMPLOYERS)]
            employer_name = f"{employer} · {self._case_suffix(case, made)}"
            placement_type = PlacementType.APPRENTICESHIP if made % 4 == 3 else PlacementType.JOB
            age = {
                "recent": 12,
                "checks_overdue": 45,
                "partly_checked": 70,
            }.get(shape, 130)
            referral = referral_services.initiate_referral(
                case=case,
                referral_category=(
                    apprenticeship_category if placement_type == PlacementType.APPRENTICESHIP else employment_category
                ),
                receiving_partner=self._provider(employer_name, PartnerType.EMPLOYER),
                initiated_by=case.case_manager,
                notes=f"[demo] source referral for placement · {self._case_suffix(case, made)}",
            )

            placement = placement_services.record_placement(
                case=case,
                employer_name=employer_name,
                sector=sector,
                placement_type=placement_type,
                placement_date=date.today() - timedelta(days=age),
                recorded_by=liaison,
                wage_amount=random.choice([2500, 3200, 4000, None]),
                is_subsidised=shape == "retained_subsidised",
                source_referral=referral,
                notes=f"[demo] seeded by seed_demo_sprint5 · {self._case_suffix(case, made)}",
            )

            if shape in {"retained", "retained_subsidised"}:
                self._answer(placement, liaison, RetentionStatus.RETAINED)
            elif shape == "partly_checked":
                self._answer(placement, liaison, RetentionStatus.RETAINED, only=(30,))
            elif shape == "unreachable":
                self._answer(placement, liaison, RetentionStatus.UNREACHABLE)
            elif shape.startswith("exited_"):
                reason = {
                    "exited_better_job": ExitReason.BETTER_JOB,
                    "exited_dismissed": ExitReason.DISMISSED,
                    "exited_contract": ExitReason.CONTRACT_ENDED,
                }[shape]
                placement_services.record_exit(
                    placement,
                    exit_date=date.today() - timedelta(days=random.randint(10, 60)),
                    exit_reason=reason,
                    actor=liaison,
                    note="[demo]",
                )
            made += 1
        return made

    def _answer(self, placement, actor, status, only=None):
        for check in placement.retention_checks.due():
            if only and check.checkpoint not in only:
                continue
            placement_services.record_check(check, status=status, actor=actor, checked_on=check.due_date)
