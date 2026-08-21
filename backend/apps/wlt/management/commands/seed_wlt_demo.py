"""Demo data for the WLT module — development only.

Six groups in one kebele, one per shape the screens have to draw:

| Group | Shape |
|---|---|
| Temsalet | Twelve months of clean meetings at P2, a savings account active |
| Adey | At P1 and close to the P2 gate, so the readiness card shows near-misses |
| Bezawit | A blocked savings account: still at P1, and the screen says so |
| Selam | Dormant — stopped meeting, which is what the adherence rule catches |
| Hiwot | A draft that never constituted, and expired |
| Meskerem | Constituted, never activated: the attrition the handoff wants visible |

Plus a mobilisation event whose endorsement was **refused**, because a kebele
that produced no groups is programme learning and it is invisible if only
successes are stored.

Everything goes through `services`, so the rows are the ones the application
would produce; only the dates are seeded. Ids are `uuid5`-derived, so `--refresh`
keeps the same URLs.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.locations.models import Location, LocationLevel
from apps.partners.models import Partner, PartnerType
from apps.users.models import AccountStatus, Role, User
from apps.wlt.models import (
    AttendanceStatus,
    BeneficiaryProfile,
    EnrolmentRoute,
    Group,
    GroupStatus,
    LinkageStatus,
    MeetingCadence,
    MobilisationEvent,
    OfficeRole,
    Phase,
    ServiceChargeBasis,
    VerificationStatus,
)
from apps.wlt.services import formation as formation_service
from apps.wlt.services import ledger as ledger_service
from apps.wlt.services import linkage as linkage_service
from apps.youth.models import PsnpStatus, Sex, Youth

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "wlt.demo.eopp")
FIRST_NAMES = [
    "Aster",
    "Bezawit",
    "Chaltu",
    "Dinknesh",
    "Emebet",
    "Fatuma",
    "Genet",
    "Hirut",
    "Ikram",
    "Jemila",
    "Kidist",
    "Lensa",
    "Meseret",
    "Nigist",
    "Oli",
    "Rahel",
    "Selam",
    "Tigist",
    "Urji",
    "Wubet",
    "Yeshi",
    "Zewditu",
]
LAST_NAMES = ["Abebe", "Bekele", "Chala", "Desta", "Endale", "Girma", "Haile", "Kebede"]

GROUPS = [
    ("Temsalet SHG", "mature"),
    ("Adey SHG", "near_gate"),
    ("Bezawit SHG", "blocked_linkage"),
    ("Selam SHG", "dormant"),
    ("Hiwot SHG", "expired_draft"),
    ("Meskerem SHG", "never_activated"),
]


class Command(BaseCommand):
    help = "Seed demonstration WLT groups. Development only — writes real group and ledger records."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Delete the demo data and rebuild it.")
        parser.add_argument("--reset", action="store_true", help="Delete the demo data and stop.")
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG off.")

    def handle(self, *args, **options):
        # The same guard `seed_demo_referrals` carries. This writes group,
        # membership and ledger rows; a production database must not acquire
        # six invented savings groups because somebody ran the wrong command.
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to run with DEBUG off. Pass --force if this really is a demo environment.")

        if options["refresh"] or options["reset"]:
            self._reset()
            if options["reset"]:
                self.stdout.write(self.style.SUCCESS("WLT demo data removed."))
                return

        with transaction.atomic():
            self._build_all()

    def _build_all(self):
        kebele = self._kebele()
        facilitator = self._facilitator(kebele)
        self._officer(kebele)
        self._region_officer(kebele)
        self._federal_officer()
        provider = self._provider(kebele)

        MobilisationEvent.objects.get_or_create(
            id=uuid.uuid5(NAMESPACE, "mobilisation-refused"),
            defaults={
                "kebele": kebele,
                "held_on": date.today() - timedelta(days=400),
                "facilitator": facilitator,
                "attendees_potential": 34,
                "attendees_husbands": 11,
                "attendees_elders": 6,
                "attendees_leaders": 3,
                "endorsement_obtained": False,
                "endorsement_note": "Elders asked for a second consultation before women commit savings.",
            },
        )

        built = []
        for name, shape in GROUPS:
            built.append(self._build(name, shape, kebele, facilitator, provider))

        self.stdout.write(self.style.SUCCESS(f"WLT demo seeded: {len(built)} group(s) in {kebele.name}."))
        for group in built:
            self.stdout.write(f"  {group.name}: {group.status} {group.current_phase or ''}")
        self.stdout.write("  Refresh the reporting views to see them in the CLA readiness screen:")
        self.stdout.write("    manage.py refresh_wlt_reporting")

    # -- scaffolding ------------------------------------------------------

    def _reset(self):
        """Remove the demo groups, ledger and all.

        The ledger and phase events are append-only *by trigger*, which is
        exactly right for real data and exactly in the way of a command whose
        job is to delete invented data. The triggers come off for the deletes
        and go back on in a `finally`, so an interrupted run cannot leave a
        database whose ledger accepts deletes.

        The two `ALTER`s sit **outside** the deleting transaction on purpose:
        Postgres refuses to alter a table with pending trigger events, and the
        cascading deletes queue them. This is the only place in the module that
        touches the triggers, and it is behind the DEBUG guard in `handle`.
        """
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE wlt_ledgerentry DISABLE TRIGGER USER")
            cursor.execute("ALTER TABLE wlt_phaseevent DISABLE TRIGGER USER")
        try:
            with transaction.atomic():
                self._delete_demo_rows()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE wlt_ledgerentry ENABLE TRIGGER USER")
                cursor.execute("ALTER TABLE wlt_phaseevent ENABLE TRIGGER USER")

    def _delete_demo_rows(self):
        names = [name for name, _shape in GROUPS]
        groups = Group.objects.filter(name__in=names)
        for group in groups:
            group.linkages.all().delete()
            group.ledger_entries.all().delete()
            group.loans.all().delete()
            group.meetings.all().delete()
            group.memberships.all().delete()
            group.office_holders.all().delete()
            group.bylaw_versions.all().delete()
            group.phase_events.all().delete()
            group.validation_overrides.all().delete()
        people = list(Youth.objects.filter(wlt_profile__psnp_client_id__startswith="DEMO-"))
        groups.delete()
        BeneficiaryProfile.objects.filter(person__in=people).delete()
        Youth.objects.filter(pk__in=[person.pk for person in people]).delete()
        MobilisationEvent.objects.filter(id=uuid.uuid5(NAMESPACE, "mobilisation-refused")).delete()

    def _kebele(self):
        kebele = Location.objects.filter(level=LocationLevel.KEBELE, name="Dessie Zuria 01").first()
        if kebele is None:
            raise CommandError("Run seed_locations and seed_wlt_policy first — the pilot kebeles are missing.")
        return kebele

    def _facilitator(self, kebele):
        user, created = User.objects.get_or_create(
            username="wlt1",
            defaults={
                "full_name": "Almaz Fikru",
                "role": Role.WLT_FACILITATOR,
                "account_status": AccountStatus.ACTIVE,
                "wlt_scope_location": kebele,
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _officer(self, kebele):
        user, created = User.objects.get_or_create(
            username="wltworeda1",
            defaults={
                "full_name": "Tadesse Alemu",
                "role": Role.WLT_WOREDA_OFFICER,
                "account_status": AccountStatus.ACTIVE,
                "wlt_scope_location": kebele.parent,
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _region_officer(self, kebele):
        region = kebele
        while region.parent_id and region.level != LocationLevel.REGION:
            region = region.parent
        user, created = User.objects.get_or_create(
            username="wltregion1",
            defaults={
                "full_name": "Mekdes Bekele",
                "role": Role.WLT_REGION_OFFICER,
                "account_status": AccountStatus.ACTIVE,
                "wlt_scope_location": region,
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _federal_officer(self):
        user, created = User.objects.get_or_create(
            username="wltfederal1",
            defaults={
                "full_name": "Hana Girma",
                "role": Role.WLT_FEDERAL_OFFICER,
                "account_status": AccountStatus.ACTIVE,
            },
        )
        if created:
            user.set_password("demo-Test-12345")
            user.save()
        return user

    def _provider(self, kebele):
        provider, _created = Partner.objects.get_or_create(
            partner_name="Amhara Rural Bank",
            partner_type=PartnerType.BANK if hasattr(PartnerType, "BANK") else PartnerType.FINANCE_INSTITUTION,
            defaults={
                "woreda_coverage": [kebele.parent.name],
                "contact_name": "Branch Manager",
                "phone": "+251911000001",
                "email": "branch@example.et",
            },
        )
        return provider

    def _member(self, index, kebele, facilitator):
        name = f"{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[(index // 7) % len(LAST_NAMES)]}"
        person_id = uuid.uuid5(NAMESPACE, f"person-{index}")
        person, created = Youth.objects.get_or_create(
            id=person_id,
            defaults={
                "full_name": name,
                "sex": Sex.FEMALE,
                "date_of_birth": date(1985 + (index % 12), 1 + (index % 12), 1 + (index % 27)),
                "region": kebele.parent.parent.parent.name,
                "zone": kebele.parent.parent.name,
                "woreda": kebele.parent.name,
                "kebele": kebele.name,
                "psnp_status": PsnpStatus.ENROLLED,
                "consent_given": True,
                "consent_date": date.today() - timedelta(days=500),
                "registering_worker": facilitator,
            },
        )
        if created:
            BeneficiaryProfile.objects.create(
                person=person,
                psnp_client_id=f"DEMO-{index:04d}",
                psnp_woreda=kebele.parent,
                psnp_kebele=kebele,
                els_completed_on=date.today() - timedelta(days=480),
                els_grant_received_on=date.today() - timedelta(days=450),
                literacy_level="BASIC" if index % 3 else "NONE",
                digital_literacy="BASIC" if index % 4 else "NONE",
                has_device=index % 5 == 0,
                primary_iga="Poultry" if index % 2 else "Petty trade",
                enrolment_route=EnrolmentRoute.IMPORT if index % 9 else EnrolmentRoute.FACILITATOR,
                verification_status=VerificationStatus.VERIFIED,
                verified_on=date.today() - timedelta(days=440),
            )
        return person

    # -- the six shapes ---------------------------------------------------

    def _build(self, name, shape, kebele, facilitator, provider):
        offset = GROUPS.index((name, shape)) * 100
        members = [self._member(offset + index, kebele, facilitator) for index in range(20)]

        group = Group.objects.filter(name=name).first()
        if group is not None:
            return group

        drafted = date.today() - timedelta(days=400)
        group = formation_service.open_draft(name=name, kebele=kebele, facilitator=facilitator, on_date=drafted)
        Group.objects.filter(pk=group.pk).update(id=group.pk)

        if shape == "expired_draft":
            for person in members[:12]:
                formation_service.add_member(group, person, on_date=drafted)
            formation_service.expire_stale_drafts(as_of=date.today())
            group.refresh_from_db()
            return group

        for person in members:
            formation_service.add_member(group, person, on_date=drafted)

        formation_service.record_bylaws(
            group,
            effective_from=drafted + timedelta(days=7),
            recorded_by=facilitator,
            meeting_cadence=MeetingCadence.WEEKLY,
            meeting_day="Monday",
            contribution_etb=Decimal("20.00"),
            service_charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
            service_charge_rate=Decimal("0.0500"),
            officer_rotation_months=12,
            loan_quorum_pct=60,
            max_concurrent_loans=5,
            reserve_buffer_pct=10,
            clauses_local_language="Two signatories: the chair and the treasurer.",
        )
        for role, person in zip((OfficeRole.CHAIR, OfficeRole.SECRETARY, OfficeRole.TREASURER), members, strict=False):
            formation_service.elect_officer(group, person=person, role=role, from_date=drafted + timedelta(days=7))

        formation_service.constitute(group, on_date=drafted + timedelta(days=10), actor=facilitator)

        if shape == "never_activated":
            return group

        # Weekly meetings up to a date that depends on the shape: a dormant
        # group simply stops, which is what the adherence window catches.
        weeks = {"mature": 52, "near_gate": 30, "blocked_linkage": 14, "dormant": 20}[shape]
        last_week = {"mature": 0, "near_gate": 0, "blocked_linkage": 0, "dormant": 16}[shape]
        start = date.today() - timedelta(weeks=weeks)

        for week in range(weeks - last_week):
            held = start + timedelta(weeks=week)
            meeting = ledger_service.open_meeting(group, held_on=held, recorded_by=facilitator)
            # Not everyone every week: a demo where attendance is always 100%
            # cannot show what the readiness card is for.
            present = members if week % 4 else members[:18]
            ledger_service.record_attendance(
                meeting,
                [
                    (person, AttendanceStatus.PRESENT if person in present else AttendanceStatus.ABSENT)
                    for person in members
                ],
            )
            for person in present:
                ledger_service.record_savings(meeting, person=person, amount_etb=20, actor=facilitator)
            ledger_service.close_meeting(
                meeting,
                counted_cash_etb=ledger_service.expected_cash(meeting),
                actor=facilitator,
                social_time_minutes=20 if week % 3 else 10,
                social_topic="Household nutrition" if week % 2 else "School attendance",
            )
            if week == 0:
                formation_service.activate(group, on_date=held, actor=facilitator)

        group.refresh_from_db()

        if shape == "mature":
            Group.objects.filter(pk=group.pk).update(
                current_phase=Phase.P2, phase_entered_on=date.today() - timedelta(days=120)
            )
            group.refresh_from_db()
            linkage = linkage_service.propose(
                linkage_type="savings_account", subject=group, provider=provider, actor=facilitator
            )
            if linkage.status == LinkageStatus.SCREENED:
                linkage_service.submit_for_approval(linkage, actor=facilitator)
                linkage_service.approve(linkage, actor=User.objects.get(username="wltworeda1"))
                linkage_service.activate(linkage, actor=facilitator)

        if shape == "blocked_linkage":
            # Still at P1, so the savings account blocks and the screen says
            # exactly what the group has to reach.
            linkage_service.propose(linkage_type="savings_account", subject=group, provider=provider, actor=facilitator)

        if shape == "dormant":
            Group.objects.filter(pk=group.pk).update(status=GroupStatus.DORMANT)
            group.refresh_from_db()

        return group
