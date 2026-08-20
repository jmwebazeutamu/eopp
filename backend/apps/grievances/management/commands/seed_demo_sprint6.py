"""Demo enterprises, follow-ups and grievances — development only.

Every shape the three Sprint 6 screens have to draw:

| Shape | Why it is here |
|---|---|
| Approved plan, nothing disbursed | The officer's queue — the delay is ours |
| Disbursed, not trading | A transfer is not a result, and the card must show both |
| Trading, milestones part-achieved | The normal case |
| Closed business, with a reason | Survival is measured over these too |
| Four failed contact attempts | CM-4's fourth condition, live |
| Reached and verified | Moves an outcome into the reportable figure |
| Overdue grievance | The channel's own service standard, breached |
| Safeguarding grievance | Visible only to its assignee — the narrowing, demonstrable |
| Referral-delay grievance about a partner | The partner performance panel's input |

Everything goes through `services`, so the rows are the ones the application
would produce; only the dates are seeded.
"""

import random
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cases.models import Case
from apps.enterprises import services as enterprise_services
from apps.enterprises.models import BusinessPlanStatus, Enterprise, SupportType
from apps.followups import services as followup_services
from apps.followups.models import ContactMethod, ContactOutcome, FollowUp
from apps.grievances import services as grievance_services
from apps.grievances.models import ComplaintType, Grievance, RaisedBy
from apps.partners.models import Partner
from apps.referrals import services as referral_services
from apps.referrals.models import Referral, ReferralStatus, VerificationSource
from apps.referrals.taxonomy import ReferralCategory
from apps.users.models import AccountStatus, Role, User

MARKER = "[demo] seeded by seed_demo_sprint6"

BUSINESSES = [
    ("Hana's Poultry", "Livestock"),
    ("Rift Valley Tailoring", "Garments"),
    ("Adama Injera Bakery", "Food"),
    ("Bishoftu Phone Repair", "Services"),
]


class Command(BaseCommand):
    help = "Seed demonstration enterprises, follow-ups and grievances. Development only."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Delete the demo rows and rebuild them.")
        parser.add_argument("--reset", action="store_true", help="Delete the demo rows and stop.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off.")
        parser.add_argument("--seed", type=int, default=6, help="Random seed. Same seed, same database.")

    @transaction.atomic
    def handle(self, *args, **options):
        # The same guard the other demo seeders carry: this writes case data.
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to run with DEBUG off. Pass --force if this really is a demo environment.")

        random.seed(options["seed"])

        if options["refresh"] or options["reset"]:
            removed = self._reset()
            self.stdout.write(f"  removed {removed} demo row(s).")
            if options["reset"]:
                return

        cases = list(Case.objects.select_related("youth").order_by("opened_date")[:60])
        if len(cases) < 20:
            raise CommandError("Not enough cases. Run seed_demo_referrals or seed_pilot_scale first.")

        officer = self._user("eo1", "Meseret Alemu", Role.ENTERPRISE_OFFICER)
        mne = self._user("mne1", "Dawit Haile", Role.MNE_STAFF)
        supervisor = User.objects.filter(role=Role.SUPERVISOR).first() or self._user(
            "sup-demo", "Woreda Supervisor", Role.SUPERVISOR
        )

        enterprises = self._seed_enterprises(cases[24:32], officer)
        contacts = self._seed_follow_ups(cases[32:44], mne)
        verified = self._verify_outcomes(mne)
        grievances = self._seed_grievances(cases[44:48], supervisor)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sprint 6 demo seeded: {enterprises} enterprise(s), {contacts} contact attempt(s), "
                f"{verified} outcome(s) verified, {grievances} grievance(s)."
            )
        )
        self.stdout.write(f"  Enterprise officer: {officer.username}   M&E: {mne.username}")

    # -- scaffolding ------------------------------------------------------

    def _reset(self):
        removed = 0
        for model, field in ((Enterprise, "notes"), (FollowUp, "notes"), (Grievance, "summary")):
            queryset = model.objects.filter(**{f"{field}__contains": MARKER})
            removed += queryset.count()
            queryset.delete()
        return removed

    def _user(self, username, full_name, role):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "full_name": full_name,
                "role": role,
                "account_status": AccountStatus.ACTIVE,
                "woreda_assignment": ["Adama", "Bishoftu", "Lume"],
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _case_suffix(self, case, ordinal):
        return f"{case.youth.full_name} · {str(case.pk)[:8]} · {ordinal + 1}"

    # -- enterprises ------------------------------------------------------

    def _seed_enterprises(self, cases, officer):
        enterprise_category = ReferralCategory.objects.get(code="ENTERPRISE")
        finance_category = ReferralCategory.objects.get(code="FINANCE_ACCESS")
        support_partner = Partner.objects.filter(active_status=True).first()
        if support_partner is None:
            raise CommandError("No active partner exists to receive enterprise referrals.")
        shapes = ["awaiting", "awaiting", "disbursed", "trading", "trading", "closed", "drafted", "revision"]
        made = 0
        for case, shape in zip(cases, shapes, strict=False):
            name, sector = BUSINESSES[made % len(BUSINESSES)]
            label = self._case_suffix(case, made)
            referral = referral_services.initiate_referral(
                case=case,
                referral_category=finance_category if shape == "awaiting" else enterprise_category,
                receiving_partner=support_partner,
                initiated_by=case.case_manager,
                notes=f"[demo] source referral for enterprise · {label}",
            )
            enterprise = enterprise_services.open_enterprise(
                case=case,
                recorded_by=officer,
                source_referral=referral,
                business_name=f"{name} · {label}",
                sector=sector,
                notes=f"{MARKER} · {label}",
            )

            if shape == "drafted":
                enterprise_services.set_plan_status(enterprise, status=BusinessPlanStatus.DRAFTED)
            elif shape == "revision":
                enterprise_services.set_plan_status(enterprise, status=BusinessPlanStatus.REVISION_REQUESTED)
            else:
                enterprise_services.set_plan_status(enterprise, status=BusinessPlanStatus.APPROVED)

            if shape in {"disbursed", "trading", "closed"}:
                age = 250 if shape == "closed" else random.choice([40, 120, 210])
                enterprise_services.record_disbursement(
                    enterprise,
                    amount=random.choice([5000, 7500, 12000]),
                    support_type=random.choice([SupportType.GRANT, SupportType.LOAN, SupportType.IN_KIND]),
                    disbursed_on=date.today() - timedelta(days=age),
                )
                enterprise_services.add_milestone(
                    enterprise,
                    milestone_name="Buy initial stock",
                    target_date=date.today() - timedelta(days=age - 14),
                )
                enterprise_services.add_milestone(
                    enterprise,
                    milestone_name="Register with the woreda",
                    target_date=date.today() - timedelta(days=age - 45),
                )

            if shape in {"trading", "closed"}:
                enterprise_services.record_trading(
                    enterprise, started_on=enterprise.disbursement_date + timedelta(days=21)
                )
                first = enterprise.milestones.first()
                if first:
                    enterprise_services.achieve_milestone(first, completion_date=first.target_date)

            if shape == "closed":
                enterprise_services.close_enterprise(
                    enterprise,
                    reason="Stock was lost when the shed flooded and could not be replaced.",
                    closed_on=date.today() - timedelta(days=20),
                )
            made += 1
        return made

    # -- follow-ups -------------------------------------------------------

    def _seed_follow_ups(self, cases, actor):
        made = 0
        for index, case in enumerate(cases):
            if index < 3:
                # CM-4's fourth condition, live: four failures and no answer.
                for attempt in range(4):
                    followup_services.record_attempt(
                        case=case,
                        contact_method=ContactMethod.PHONE,
                        contact_outcome=random.choice([ContactOutcome.NO_RESPONSE, ContactOutcome.UNREACHABLE]),
                        conducted_by=actor,
                        attempt_date=date.today() - timedelta(days=20 - attempt * 4),
                        notes=MARKER,
                    )
                    made += 1
                continue

            followup_services.record_attempt(
                case=case,
                contact_method=random.choice([ContactMethod.PHONE, ContactMethod.HOME_VISIT]),
                contact_outcome=random.choice([ContactOutcome.REACHED_ENGAGED, ContactOutcome.REACHED_NOT_ENGAGED]),
                conducted_by=actor,
                attempt_date=date.today() - timedelta(days=random.randint(2, 30)),
                notes=MARKER,
            )
            made += 1
        return made

    def _verify_outcomes(self, actor):
        """Move a handful of recorded outcomes into the reportable figure.

        Deliberately a handful and not all of them: the gap between the recorded
        rate and the verified one is what the M&E screen exists to show, and a
        demo where it is closed shows nothing.
        """
        verified = 0
        completed = Referral.objects.youth_side().filter(status=ReferralStatus.COMPLETED)[:6]
        for referral in completed:
            contact = followup_services.record_attempt(
                case=referral.case,
                contact_method=ContactMethod.PHONE,
                contact_outcome=ContactOutcome.REACHED_ENGAGED,
                conducted_by=actor,
                related_referral=referral,
                attempt_date=date.today() - timedelta(days=random.randint(1, 20)),
                notes=MARKER,
            )
            followup_services.verify_referral_outcome(
                contact,
                verification_source=random.choice(
                    [VerificationSource.PROVIDER_CONFIRMED, VerificationSource.EMPLOYER_CONFIRMED]
                ),
                actor=actor,
            )
            verified += 1
        return verified

    # -- grievances -------------------------------------------------------

    def _seed_grievances(self, cases, supervisor):
        partner = Partner.objects.filter(active_status=True).first()
        rows = [
            {
                "complaint_type": ComplaintType.REFERRAL_DELAY,
                "raised_by": RaisedBy.YOUTH,
                "summary": f"Waited five weeks for the training centre to confirm my place. {MARKER}",
                "about_partner": partner,
                "date_raised": date.today() - timedelta(days=30),
            },
            {
                "complaint_type": ComplaintType.REFERRAL_QUALITY,
                "raised_by": RaisedBy.EMPLOYER,
                "summary": f"The youth sent to us had no experience of the trade at all. {MARKER}",
                "about_partner": partner,
                "date_raised": date.today() - timedelta(days=8),
                "complainant_name": "Adama Textiles",
            },
            {
                "complaint_type": ComplaintType.PAYMENT,
                "raised_by": RaisedBy.YOUTH,
                "summary": f"The transport stipend has not arrived for two months. {MARKER}",
                "date_raised": date.today() - timedelta(days=4),
            },
            {
                "complaint_type": ComplaintType.SAFEGUARDING,
                "raised_by": RaisedBy.YOUTH,
                "summary": f"A matter I will only discuss with the focal point. {MARKER}",
                "date_raised": date.today() - timedelta(days=2),
            },
        ]
        made = 0
        for index, fields in enumerate(rows):
            case = cases[index] if index < len(cases) else None
            grievance_services.raise_grievance(
                assigned_staff=supervisor,
                case=case,
                woreda=case.woreda if case else "Adama",
                **fields,
            )
            made += 1
        return made
