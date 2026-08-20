"""Turn the two remaining flags on for the categories the tuples used to name.

`apps.placements.models.PLACEMENT_REFERRAL_CATEGORY_CODES` and
`apps.enterprises.models.ENTERPRISE_REFERRAL_CATEGORY_CODES`, written out so the
intent survives their deletion. Behaviour is preserved exactly for every
database that already exists; what changes is who may change it.
"""

from django.db import migrations

PREVIOUSLY_HARDCODED = {
    "creates_placement": ["EMPLOYMENT", "APPRENTICESHIP"],
    "creates_enterprise": ["ENTERPRISE", "FINANCE_ACCESS"],
}


def turn_on(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    for field, codes in PREVIOUSLY_HARDCODED.items():
        ReferralCategory.objects.filter(code__in=codes).update(**{field: True})


def turn_off(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    for field, codes in PREVIOUSLY_HARDCODED.items():
        ReferralCategory.objects.filter(code__in=codes).update(**{field: False})


class Migration(migrations.Migration):
    dependencies = [("referrals", "0011_category_creates_placement_and_enterprise")]

    operations = [migrations.RunPython(turn_on, turn_off)]
