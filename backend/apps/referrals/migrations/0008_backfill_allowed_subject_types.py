"""Every existing referral category names a case, and nothing else.

The handoff's runbook backfills every referral type to `person` before widening
any of them, "which preserves current behaviour exactly". The same move here,
with `CASE` as the subject every existing referral has: a category that permitted
nothing would refuse the next referral raised in it, and one left empty would
have to be read as unrestricted — which is precisely the reading that would open
the safeguarding rule.

Widening a category to accept a group is a deliberate admin edit afterwards, not
a consequence of this migration.
"""

from django.db import migrations


def set_case_only(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    updated = ReferralCategory.objects.filter(allowed_subject_types=[]).update(allowed_subject_types=["CASE"])
    print(f"\n  {updated} referral categor(ies) restricted to CASE subjects.")


def clear(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    ReferralCategory.objects.filter(allowed_subject_types=["CASE"]).update(allowed_subject_types=[])


class Migration(migrations.Migration):

    dependencies = [
        ("referrals", "0007_historicalreferral_subject_cla_and_more"),
    ]

    operations = [migrations.RunPython(set_case_only, clear)]
