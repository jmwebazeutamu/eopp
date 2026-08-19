"""Seed the partners and staff accounts the other seeders assume exist.

`seed_pilot_scale` refuses without three active partners and `seed_demo_referrals`
looks for a user per role, but nothing created either. They existed only in
whichever database someone had made them in by hand, so a fresh environment
could not be brought to a state anybody could test — which is exactly what
happened bringing up the review server.

    python manage.py seed_demo_org                       # partners + one account per role
    python manage.py seed_demo_org --password 'chosen'   # instead of a generated one
    python manage.py seed_demo_org --reset               # delete the seeded accounts and partners

Idempotent: partners match on name and accounts on username, so re-running
updates rather than duplicates. It never touches an account it did not create,
so a real administrator added by hand is left alone.

Development and review data only. It writes partner records and login
credentials, so it refuses unless DEBUG is on or
--i-know-this-is-not-production is passed.
"""

import secrets
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.partners.models import MouStatus, Partner, PartnerType
from apps.users.models import AccountStatus, Role, User

# Covering the three woredas seed_pilot_scale registers into, with a spread of
# types so the referral taxonomy has somewhere to send each category.
PARTNERS = [
    ("Adama Polytechnic College", PartnerType.TVET_INSTITUTION, ["Adama", "Lume"], MouStatus.SIGNED, "Tigist Bekele"),
    ("Adama Skills Hub", PartnerType.TVET_INSTITUTION, ["Adama"], MouStatus.NONE, "Meseret Alemu"),
    ("Adama Health Centre", PartnerType.HEALTH_SERVICE, ["Adama"], MouStatus.NONE, "Dr Hailu"),
    ("Bishoftu Automotive Plc", PartnerType.EMPLOYER, ["Bishoftu"], MouStatus.SIGNED, "Solomon Girma"),
    (
        "Oromia Credit and Savings",
        PartnerType.FINANCE_INSTITUTION,
        ["Adama", "Bishoftu"],
        MouStatus.DRAFT,
        "Almaz Tesfaye",
    ),
    (
        "Rift Valley Enterprise Agency",
        PartnerType.ENTERPRISE_DEVELOPMENT_AGENCY,
        ["Adama", "Bishoftu", "Lume"],
        MouStatus.SIGNED,
        "Bekele Wolde",
    ),
]

WOREDAS = ["Adama", "Bishoftu", "Lume"]

# One account per role a reviewer needs to see the system through. The §7
# matrix is only legible from inside the roles it describes: signed in as an
# administrator every screen looks the same.
ACCOUNTS = [
    ("cm1", "Case Manager One", Role.CASE_MANAGER, ["Adama", "Bishoftu"]),
    ("cm2", "Case Manager Two", Role.CASE_MANAGER, WOREDAS),
    ("cm3", "Case Manager Three", Role.CASE_MANAGER, WOREDAS),
    ("cm4", "Case Manager Four", Role.CASE_MANAGER, WOREDAS),
    ("sup1", "Supervisor One", Role.SUPERVISOR, ["Adama"]),
    ("outreach1", "Outreach Worker One", Role.OUTREACH_WORKER, ["Adama", "Bishoftu"]),
    ("pm1", "Programme Manager One", Role.PROGRAMME_MANAGER, []),
    ("me1", "M and E Officer One", Role.MNE_STAFF, []),
]

# One partner-staff login per institution.
#
# Not decoration: a confirmation entered by the partner leaves
# `confirmation_recorded_by` null, and that is the only thing the
# partner-response median counts. With staff recording every answer, the whole
# "confirmation lag by partner" panel reads "too few to assess" forever —
# correct, and impossible to review.
PARTNER_STAFF = [
    ("partner1", "Tigist Bekele", "Adama Polytechnic College"),
    ("partner2", "Meseret Alemu", "Adama Skills Hub"),
    ("partner3", "Dr Hailu", "Adama Health Centre"),
    ("partner4", "Solomon Girma", "Bishoftu Automotive Plc"),
    ("partner5", "Almaz Tesfaye", "Oromia Credit and Savings"),
    ("partner6", "Bekele Wolde", "Rift Valley Enterprise Agency"),
]

CHANGE_REASON = "Seeded by manage.py seed_demo_org"


class Command(BaseCommand):
    help = "Seed demo partners and one staff account per role. Never for an environment holding real records."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Password for every seeded account. Generated if omitted.")
        parser.add_argument("--reset", action="store_true", help="Delete the seeded accounts and partners, then stop.")
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
                "This writes partner records and login credentials. Re-run with "
                "--i-know-this-is-not-production if this environment holds no real data."
            )

        if options["reset"]:
            usernames = [a[0] for a in ACCOUNTS] + [p[0] for p in PARTNER_STAFF]
            users, _ = User.objects.filter(username__in=usernames).delete()
            partners, _ = Partner.objects.filter(partner_name__in=[p[0] for p in PARTNERS]).delete()
            self.stdout.write(f"  removed {users} account row(s) and {partners} partner row(s)")
            return

        for name, kind, coverage, mou, contact in PARTNERS:
            Partner.objects.update_or_create(
                partner_name=name,
                defaults={
                    "partner_type": kind,
                    "woreda_coverage": coverage,
                    "mou_status": mou,
                    "contact_name": contact,
                    "phone": "+251911000000",
                    "active_status": True,
                    # The model requires a date on a signed MOU; without one a
                    # later full_clean on the record refuses to save it.
                    "mou_date": date.today() - timedelta(days=120) if mou == MouStatus.SIGNED else None,
                },
            )
        self.stdout.write(f"  partners: {len(PARTNERS)}")

        password = options["password"] or secrets.token_urlsafe(12)

        def upsert(username, full_name, role, woredas, partner=None):
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "full_name": full_name,
                    "role": role,
                    "woreda_assignment": woredas,
                    "account_status": AccountStatus.ACTIVE,
                    # §4.12: a partner staff account is meaningless without the
                    # institution it is scoped to.
                    "partner": partner,
                },
            )
            user.set_password(password)
            user._change_reason = CHANGE_REASON
            user.save()

        for username, full_name, role, woredas in ACCOUNTS:
            upsert(username, full_name, role, woredas)

        for username, full_name, partner_name in PARTNER_STAFF:
            upsert(username, full_name, Role.PARTNER_STAFF, [], Partner.objects.get(partner_name=partner_name))

        self.stdout.write(f"  accounts: {len(ACCOUNTS) + len(PARTNER_STAFF)}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  every seeded account signs in with:  {password}"))
        self.stdout.write(
            "  Shown once — only the hash is stored. These are review credentials for "
            "fabricated data; never reuse them where real records live."
        )
