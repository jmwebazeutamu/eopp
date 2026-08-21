"""Seed the WLT policy layer — the handoff's `sql/003`, as admin-editable rows.

Idempotent. Values marked NEEDS FSCO are placeholders taken from the handbook
where it is self-consistent and from the more conservative reading where it is
not. **A default is not an agreement**: every one of these is a row an
administrator can supersede without a deployment, which is the whole point of
decision D6.

Also seeds the pre-pilot geography and allocation. The five regions already
exist in `seed_locations`; the zones, woredas and kebeles under them do not, and
a group cannot be registered without a kebele. Those are **illustrative** — one
woreda and two kebeles per region, named for the region — and the actual pilot
sites are a programme decision, exactly as the youth-side seeded woredas are.
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.locations.models import Location, LocationLevel
from apps.wlt.models import EnrolmentAllocation, PolicyParameter

EFFECTIVE_FROM = date(2026, 1, 1)

# (region code, members, groups) — handbook §3.1, a hard ceiling of 5,000.
ALLOCATIONS = [
    ("ET-SO", 1600, 80),
    ("ET-AM", 1200, 60),
    ("ET-AF", 1000, 50),
    ("ET-CE", 908, 45),
    ("ET-DD", 292, 15),
]

# Illustrative pilot geography, one woreda and two kebeles per region.
PILOT_SITES = [
    ("ET-SO", "Jarar", "Degehabur"),
    ("ET-AM", "South Wollo", "Dessie Zuria"),
    ("ET-AF", "Awsi Rasu", "Chifra"),
    ("ET-CE", "Gurage", "Meskan"),
    ("ET-DD", "Dire Dawa Rural", "Biyo Awale"),
]

PARAMETERS = [
    # Group composition. The handbook says 15-20 (S2), 15-25 (S3.4) and 20 (the
    # target table). The outer range is the hard block, the inner the warning.
    ("group.size.hard_min", 15, "NEEDS FSCO: the handbook states three ranges"),
    ("group.size.hard_max", 25, "NEEDS FSCO: the handbook states three ranges"),
    ("group.size.warn_min", 18, "Soft warning only"),
    ("group.size.warn_max", 22, "Soft warning only"),
    # Formation lifecycle
    ("formation.draft_expiry_days", 60, ""),
    ("formation.constituted_expiry_days", 30, "Constituted but never held a savings meeting"),
    ("formation.event_expiry_days", 90, "CLA and federation formation events"),
    # Phase 1 exit gate
    ("gate.p1.meeting_adherence_pct", 90, "Against the group's own bylaw cadence"),
    ("gate.p1.attendance_pct", 80, "Handbook §4, phase 1"),
    ("gate.p1.savings_compliance_pct", 80, "NEEDS FSCO: undefined in the handbook"),
    ("gate.p1.min_savings_meetings", 10, "Handbook §3.5 lending gate"),
    ("gate.p1.max_par30_pct", 0, ""),
    # Phase 2 exit gate
    (
        "gate.p2.fund_adequacy_weeks",
        12,
        "Replaces the handbook's '2-3 months of contributions', which sits below the natural "
        "accumulation floor and screens nothing",
    ),
    ("gate.p2.completed_loan_cycles", 1, ""),
    ("gate.p2.max_par30_pct", 0, ""),
    ("gate.p2.social_fund_required", True, "NEEDS FSCO: the social fund is never defined (Q9)"),
    ("gate.p2.min_weeks_since_p1", 52, ""),
    # CLA. The handbook says 8 in the text and "around 6" in the indicator;
    # the Kindernothilfe source says 8 to 10. Seeded at the conservative 8.
    ("gate.cla.min_groups", 8, "NEEDS FSCO: the handbook says 8 and 6 (Q6)"),
    ("gate.cla.delegates_per_group", 2, ""),
    # Federation. "5 to 10 CLAs" in the text, "at least 10" in the indicator.
    ("gate.federation.min_clas", 10, "NEEDS FSCO: the handbook says 5-10 and 10+ (Q7)"),
    ("gate.federation.min_cla_months", 12, ""),
    # Credit facility — deliberately restrictive. Early linkage of savings
    # groups to microfinance is the clearest negative finding in the Ethiopian
    # evidence base, so this pathway carries the longest chain in the module.
    ("gate.credit.min_phase", "P4", ""),
    ("gate.credit.allow_group_subject", False, "Group-level credit is blocked in the pilot"),
    ("gate.credit.savings_account_months", 12, ""),
    ("gate.credit.min_completed_cycles", 2, ""),
    ("gate.credit.max_leverage_ratio", 1.0, "Facility no larger than the subject's own funds"),
    ("gate.credit.par30_clean_months", 6, ""),
    ("linkage.lapse_days", 90, "Approved but never activated"),
    ("linkage.distress_cure_days", 60, "Distressed to defaulted"),
    # Savings and market linkage open at P2. A locked cash box in a pastoralist
    # kebele is a worse custodian than a bank account.
    ("gate.savings_account.min_phase", "P2", ""),
    ("gate.market_offtake.min_phase", "P2", ""),
    ("gate.cooperative_membership.min_phase", "P3", ""),
    # Risk and dormancy
    ("risk.dormant_cadence_multiple", 3, ""),
    ("risk.dormant_floor_days", 60, ""),
    ("risk.attendance_floor_pct", 60, ""),
    ("risk.par30_ceiling_pct", 20, ""),
    # Loan discipline
    ("loan.default_days_past_due", 30, "NEEDS FSCO: standard microfinance convention (Q5)"),
    ("loan.delinquent_days_past_due", 1, ""),
    ("loan.min_meetings_before_lending", 10, "Handbook §3.5"),
    # Indicator windows
    ("indicator.rolling_meetings", 12, ""),
    ("indicator.member_compliance_pct", 90, "A member is compliant at or above this share"),
    # Enrolment controls
    ("enrolment.allocation_warn_pct", 90, ""),
    (
        "enrolment.exception_route_alert_pct",
        10,
        "Above this share in a woreda, the extract is the problem and should be fixed",
    ),
    # Meeting content. Handbook §3.6 asks for 15 to 30 minutes.
    ("meeting.social_minutes_min", 15, ""),
]


class Command(BaseCommand):
    help = "Seed WLT policy parameters, pilot geography and the pre-pilot allocation. Idempotent."

    @transaction.atomic
    def handle(self, *args, **options):
        sites = self._seed_geography()
        parameters = self._seed_parameters()
        allocations = self._seed_allocations()

        self.stdout.write(
            self.style.SUCCESS(
                f"WLT policy seeded: {parameters} parameter(s), {allocations} allocation(s), {sites} pilot site(s)."
            )
        )
        self.stdout.write(
            "  Values marked NEEDS FSCO are the conservative reading of the handbook, not an agreed position."
        )

    def _seed_geography(self):
        created = 0
        for region_code, zone_name, woreda_name in PILOT_SITES:
            region = Location.objects.filter(code=region_code).first()
            if region is None:
                self.stderr.write(f"  region {region_code} is missing — run seed_locations first")
                continue

            # Matched on the place, not on the code. Two seeds naming the same
            # woreda have to converge on one row: `unique_location_within_parent`
            # is on (parent, name, level), so matching on a code this command
            # invented would collide with a row somebody else created under a
            # different code.
            zone, made = Location.objects.get_or_create(
                name=zone_name,
                level=LocationLevel.ZONE,
                parent=region,
                defaults={"code": f"{region_code}-{zone_name[:3].upper()}"},
            )
            created += int(made)
            woreda, made = Location.objects.get_or_create(
                name=woreda_name,
                level=LocationLevel.WOREDA,
                parent=zone,
                defaults={"code": f"{zone.code}-{woreda_name[:5].upper()}"},
            )
            created += int(made)
            for index in (1, 2):
                _kebele, made = Location.objects.get_or_create(
                    name=f"{woreda_name} {index:02d}",
                    level=LocationLevel.KEBELE,
                    parent=woreda,
                    defaults={"code": f"{woreda.code}-{index:02d}"},
                )
                created += int(made)
        return created

    def _seed_parameters(self):
        written = 0
        for key, value, note in PARAMETERS:
            _row, made = PolicyParameter.objects.get_or_create(
                key=key,
                scope_location=None,
                effective_from=EFFECTIVE_FROM,
                defaults={"value": value, "note": note},
            )
            written += int(made)
        return written

    def _seed_allocations(self):
        written = 0
        for region_code, members, groups in ALLOCATIONS:
            region = Location.objects.filter(code=region_code).first()
            if region is None:
                continue
            _row, made = EnrolmentAllocation.objects.get_or_create(
                location=region,
                phase_label="pre_pilot",
                effective_from=EFFECTIVE_FROM,
                defaults={"target_members": members, "target_groups": groups},
            )
            written += int(made)
        return written
