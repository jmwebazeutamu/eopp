"""Backfill `verification_source` from the free-text verification method.

`outcome_verification_method` is free text and holds values like "Provider
register", "Employer confirmation", "Self-reported", "interview" and "Follow-up
visit". Reports were pattern-matching it, which is why self-reported outcomes
were being counted as verified.

Only unambiguous phrasings are mapped. Anything that does not clearly name who
verified the outcome is **left blank and reported**, because a blank is read as
not-verified everywhere and guessing here would inflate the headline the donor
reads. `manage.py report_unmapped_verification` lists what is left.

Reversible: the reverse pass clears only the rows this migration set, so
re-running it cannot lose a value somebody entered by hand afterwards.
"""

from django.db import migrations

# Phrasings that name the verifier without ambiguity.
UNAMBIGUOUS = {
    "self-reported": "SELF_REPORTED",
    "employer confirmation": "EMPLOYER_CONFIRMED",
    "employer confirmation call": "EMPLOYER_CONFIRMED",
    "provider register": "PROVIDER_CONFIRMED",
    "partner-recorded completion": "PROVIDER_CONFIRMED",
}

# Deliberately unmapped: a follow-up visit or an interview does not say who
# stood behind the outcome. "Follow-up visit" could be the case worker seeing
# the youth, which is not external verification at all.


def backfill(apps, schema_editor):
    Referral = apps.get_model("referrals", "Referral")
    mapped = 0
    for referral in Referral.objects.filter(verification_source="").exclude(outcome_verification_method=""):
        source = UNAMBIGUOUS.get(referral.outcome_verification_method.strip().lower())
        if source:
            referral.verification_source = source
            referral.save(update_fields=["verification_source"])
            mapped += 1
    print(f"\n  verification_source backfilled on {mapped} referral(s); the rest left blank for review.")


def clear(apps, schema_editor):
    """Only the rows whose free text still matches what we mapped from."""
    Referral = apps.get_model("referrals", "Referral")
    for referral in Referral.objects.exclude(verification_source="").exclude(outcome_verification_method=""):
        if UNAMBIGUOUS.get(referral.outcome_verification_method.strip().lower()) == referral.verification_source:
            referral.verification_source = ""
            referral.save(update_fields=["verification_source"])


class Migration(migrations.Migration):
    dependencies = [("referrals", "0004_historicalreferral_service_start_date_and_more")]
    operations = [migrations.RunPython(backfill, clear)]
