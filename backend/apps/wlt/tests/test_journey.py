"""The identity block on the beneficiary profile.

The screen named a woman and then told you nothing about her — no ID, no age,
no phone, no place — so a development agent standing in a kebele could not
confirm that the record she had open was the person in front of her.

What is worth asserting here is not the shape of the payload but the two
decisions inside it: age is counted on the birthday rather than by dividing
days, and every field is one the schema actually holds.
"""

import pytest

from apps.wlt.models import BeneficiaryProfile
from apps.wlt.services import journey

pytestmark = pytest.mark.django_db


@pytest.fixture
def wlt_profile(make_wlt_member):
    person = make_wlt_member("Almaz Tesfaye")
    person.phone_number = "+251911452207"
    person.national_or_kebele_id = "AMH-DSW-01-0247"
    person.save(update_fields=["phone_number", "national_or_kebele_id"])
    return BeneficiaryProfile.objects.get(person=person)


# ---------------------------------------------------------------------------
# Identity — added with the profile redesign of 2026-08-25
# ---------------------------------------------------------------------------


def test_identity_answers_who_she_is(wlt_profile):
    """The screen named her and stopped. Everything here is a real column."""
    identity = journey.build(wlt_profile)["identity"]

    assert identity["full_name"] == wlt_profile.person.full_name
    assert identity["sex_display"]
    assert identity["kebele"]
    assert "phone_number" in identity


def test_age_counts_the_birthday_rather_than_dividing_by_365(wlt_profile):
    """A day-count drifts a year in four, which is the cut a PSNP report uses."""
    from datetime import date

    from apps.wlt.services.journey import _age_on

    # The day before her birthday she is still the younger age.
    assert _age_on(date(1992, 3, 4), date(2026, 3, 3)) == 33
    assert _age_on(date(1992, 3, 4), date(2026, 3, 4)) == 34
    assert _age_on(None, date(2026, 3, 4)) is None


def test_missing_names_the_blank_header_fields(wlt_profile):
    """The chip says "2 details missing"; it has to be able to say which two."""
    wlt_profile.person.phone_number = ""
    wlt_profile.person.national_or_kebele_id = ""
    wlt_profile.person.save(update_fields=["phone_number", "national_or_kebele_id"])

    missing = journey.build(wlt_profile)["identity"]["missing"]

    assert "phone_number" in missing
    assert "national_id" in missing
    assert "kebele" not in missing


def test_place_comes_from_the_scoped_kebele_not_the_typed_one(wlt_profile):
    """When the two disagree, the FK is the one that decides what she is counted in."""
    wlt_profile.person.kebele = "Somewhere Else"
    wlt_profile.person.save(update_fields=["kebele"])

    identity = journey.build(wlt_profile)["identity"]

    assert identity["kebele"] == wlt_profile.psnp_kebele.name


def test_household_reports_only_fields_that_exist(wlt_profile):
    """Household size, dependants and marital status are not columns anywhere."""
    household = journey.build(wlt_profile)["household"]

    assert "household_head" in household
    assert "education_level_display" in household
    # Absent rather than rendered as a zero somebody would go on to report.
    assert "household_size" not in household
    assert "dependants_count" not in household
    assert "marital_status" not in household
