"""Youth entity tests — spec §4.1, consent rules from §9."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.youth.models import Sex, Youth

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Consent — spec §9
# ---------------------------------------------------------------------------


def test_youth_cannot_be_registered_without_consent(locations, outreach_worker):
    youth = Youth(
        full_name="No Consent",
        sex=Sex.FEMALE,
        date_of_birth=date(2002, 5, 1),
        region="Oromia",
        zone="East Shewa",
        woreda="Adama",
        kebele="Adama 01",
        consent_given=False,
        registering_worker=outreach_worker,
    )
    with pytest.raises(ValidationError) as exc:
        youth.clean()
    assert "consent_given" in exc.value.message_dict


def test_consent_requires_a_date(locations, outreach_worker):
    youth = Youth(
        full_name="Undated Consent",
        sex=Sex.FEMALE,
        date_of_birth=date(2002, 5, 1),
        region="Oromia",
        zone="East Shewa",
        woreda="Adama",
        kebele="Adama 01",
        consent_given=True,
        consent_date=None,
        registering_worker=outreach_worker,
    )
    with pytest.raises(ValidationError) as exc:
        youth.clean()
    assert "consent_date" in exc.value.message_dict


def test_consent_date_cannot_be_in_the_future(make_youth):
    youth = make_youth()
    youth.consent_date = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError) as exc:
        youth.clean()
    assert "consent_date" in exc.value.message_dict


# ---------------------------------------------------------------------------
# Age band — spec §4.1
# ---------------------------------------------------------------------------


def test_age_is_calculated_from_date_of_birth(make_youth):
    youth = make_youth(age=22)
    assert youth.age == 22


def test_age_accounts_for_a_birthday_not_yet_reached(locations, outreach_worker):
    """Naive year subtraction is off by one before the birthday falls."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    youth = Youth(date_of_birth=date(today.year - 20, tomorrow.month, tomorrow.day))
    # A birthday one day away means they are still 19, not 20.
    assert youth.age_at(today) == 19


def test_age_band_eligibility(make_youth, settings):
    settings.YOUTH_AGE_MIN = 15
    settings.YOUTH_AGE_MAX = 29
    assert make_youth(name="In Band", age=22).is_age_eligible is True
    assert make_youth(name="Too Old", age=41).is_age_eligible is False
    assert make_youth(name="Too Young", age=11).is_age_eligible is False


def test_date_of_birth_cannot_be_in_the_future(make_youth):
    youth = make_youth()
    youth.date_of_birth = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError) as exc:
        youth.clean()
    assert "date_of_birth" in exc.value.message_dict


# ---------------------------------------------------------------------------
# API — location validation and scoping
# ---------------------------------------------------------------------------


def _payload(**overrides):
    body = {
        "full_name": "Chaltu Tadesse",
        "sex": "FEMALE",
        "date_of_birth": "2003-04-12",
        "region": "Oromia",
        "zone": "East Shewa",
        "woreda": "Adama",
        "kebele": "Adama 01",
        "consent_given": True,
        "consent_date": str(date.today()),
    }
    body.update(overrides)
    return body


def test_registration_rejects_an_unknown_woreda(locations, as_user, outreach_worker):
    client = as_user(outreach_worker)
    response = client.post("/api/v1/youth/", _payload(woreda="Nowhere"), format="json")
    assert response.status_code == 400
    assert "woreda" in response.data


def test_registration_rejects_a_woreda_under_the_wrong_zone(locations, as_user, outreach_worker):
    client = as_user(outreach_worker)
    response = client.post("/api/v1/youth/", _payload(zone="Arsi"), format="json")
    assert response.status_code == 400


def test_registration_records_the_logged_in_worker(locations, as_user, outreach_worker):
    """§4.1 makes registering_worker an accountability record, not client input."""
    client = as_user(outreach_worker)
    response = client.post("/api/v1/youth/", _payload(), format="json")
    assert response.status_code == 201, response.data
    assert Youth.objects.get(pk=response.data["id"]).registering_worker == outreach_worker


def test_registration_without_consent_is_rejected_by_the_api(locations, as_user, outreach_worker):
    client = as_user(outreach_worker)
    response = client.post("/api/v1/youth/", _payload(consent_given=False), format="json")
    assert response.status_code == 400
    assert "consent_given" in response.data


def test_out_of_band_age_warns_but_does_not_block(locations, as_user, outreach_worker, settings):
    """Blocking would push staff to falsify a date of birth — see the serializer."""
    settings.YOUTH_AGE_MIN = 15
    settings.YOUTH_AGE_MAX = 29
    client = as_user(outreach_worker)
    response = client.post("/api/v1/youth/", _payload(date_of_birth="1980-01-01"), format="json")
    assert response.status_code == 201
    assert "outside the 15-29 youth band" in response.data["age_band_warning"]


def test_partial_update_does_not_retrigger_the_consent_default(locations, as_user, outreach_worker, make_youth):
    """A PATCH carries only changed fields; consent must not be re-evaluated as unset."""
    youth = make_youth()
    client = as_user(outreach_worker)
    response = client.patch(f"/api/v1/youth/{youth.pk}/", {"phone_number": "+251911000000"}, format="json")
    assert response.status_code == 200, response.data
    youth.refresh_from_db()
    assert youth.phone_number == "+251911000000"


def test_youth_cannot_be_deleted(locations, as_user, outreach_worker, make_youth):
    youth = make_youth()
    client = as_user(outreach_worker)
    assert client.delete(f"/api/v1/youth/{youth.pk}/").status_code == 405
