"""List outcomes whose verification source could not be inferred.

The 0005 backfill mapped only unambiguous phrasings. Everything else is blank,
which every report reads as *not* externally verified — the safe direction, and
the reason these need a person rather than a guess.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.referrals.models import Referral, ReferralStatus


class Command(BaseCommand):
    help = "Report completed referrals with no verification source recorded."

    def handle(self, *args, **options):
        unmapped = Referral.objects.filter(status=ReferralStatus.COMPLETED, verification_source="")

        self.stdout.write("")
        self.stdout.write(f"  completed referrals with no verification source: {unmapped.count()}")
        self.stdout.write("  These count as NOT externally verified until somebody says otherwise.")
        self.stdout.write("")
        for text, n in Counter(unmapped.values_list("outcome_verification_method", flat=True)).most_common():
            self.stdout.write(f"    {n:>4}  {text!r}")
        self.stdout.write("")
        self.stdout.write("  Set the source through the admin, or record it at verification time.")
