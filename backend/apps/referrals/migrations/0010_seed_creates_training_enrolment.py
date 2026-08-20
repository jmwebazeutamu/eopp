"""Turn the flag on for the category the hardcoded tuple used to name.

`apps.training.models.TRAINING_REFERRAL_CATEGORY_CODES` was `("TRAINING",)`, so
this preserves behaviour exactly for every database that already exists. What
changes is that it is now an administrator's decision rather than a constant.
"""

from django.db import migrations

# The tuple this replaces, written out so the intent survives its deletion.
PREVIOUSLY_HARDCODED = ["TRAINING"]


def turn_on(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    ReferralCategory.objects.filter(code__in=PREVIOUSLY_HARDCODED).update(creates_training_enrolment=True)


def turn_off(apps, schema_editor):
    ReferralCategory = apps.get_model("referrals", "ReferralCategory")
    ReferralCategory.objects.filter(code__in=PREVIOUSLY_HARDCODED).update(creates_training_enrolment=False)


class Migration(migrations.Migration):
    dependencies = [("referrals", "0009_category_creates_training_enrolment")]

    operations = [migrations.RunPython(turn_on, turn_off)]
