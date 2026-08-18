"""Reconcile `case_status = PLACED` against recorded placement outcomes.

Two populations that should have been the same set and were not:

* cases holding a placement outcome but not marked Placed — the derivation now
  in `Referral.transition_to` prevents new ones, and this fixes the backlog;
* cases marked Placed with no placement outcome behind them.

**Only the first is reconciled.** The second is reported and left alone: §4.2
lets a case manager set `PLACED` by hand, and a case can be genuinely placed
through a route this platform never recorded — a youth who found work themselves,
or a placement made before the pilot started using the system. Overwriting that
would destroy a human judgement to make a dashboard tidy, so it is surfaced for
someone to decide, one case at a time.

    python manage.py reconcile_case_placement            # report only
    python manage.py reconcile_case_placement --apply     # promote the backlog

Report first, apply second, never both in one run.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cases.models import Case, CaseStatus
from apps.referrals.models import Referral


class Command(BaseCommand):
    help = "Report, and optionally fix, cases whose status disagrees with their placement outcomes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Promote cases that hold a placement outcome but are not marked Placed.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        placed_case_ids = Referral.objects.placed_case_ids()

        # Holds a placement outcome, not marked Placed. Safe to fix: the
        # outcome is the source of truth and carries a date and a verifier.
        to_promote = Case.objects.filter(id__in=placed_case_ids).exclude(case_status=CaseStatus.PLACED)
        # Marked Placed with nothing behind it. Not safe to fix automatically.
        unexplained = Case.objects.filter(case_status=CaseStatus.PLACED).exclude(id__in=placed_case_ids)

        self.stdout.write("")
        self.stdout.write(f"  placement outcomes recorded      {Referral.objects.placements().count()}")
        self.stdout.write(f"  distinct cases with one          {len(placed_case_ids)}")
        self.stdout.write(f"  cases marked PLACED              {Case.objects.filter(case_status=CaseStatus.PLACED).count()}")
        self.stdout.write("")
        self.stdout.write(f"  to promote (outcome, not PLACED) {to_promote.count()}")
        for case in to_promote.select_related("youth")[:10]:
            self.stdout.write(f"      {case.youth.full_name:<28} {case.case_status} -> PLACED")
        if to_promote.count() > 10:
            self.stdout.write(f"      … and {to_promote.count() - 10} more")

        self.stdout.write("")
        self.stdout.write(f"  cannot reconcile (PLACED, no outcome) {unexplained.count()}")
        self.stdout.write(
            "      Left alone. §4.2 allows a case manager to set this by hand, and a youth may have\n"
            "      been placed through a route the platform never recorded. Each needs a person to\n"
            "      decide: record the outcome, or move the case back."
        )
        for case in unexplained.select_related("youth")[:10]:
            self.stdout.write(f"      {case.youth.full_name:<28} PLACED, no placement outcome")
        if unexplained.count() > 10:
            self.stdout.write(f"      … and {unexplained.count() - 10} more")

        self.stdout.write("")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Report only. Re-run with --apply to promote the first group."))
            return

        promoted = to_promote.update(case_status=CaseStatus.PLACED)
        self.stdout.write(self.style.SUCCESS(f"Promoted {promoted} case(s) to PLACED."))
        self.stdout.write(f"{unexplained.count()} case(s) still need a human decision.")
