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


# ---------------------------------------------------------------------------
# The registry's open-case pill
# ---------------------------------------------------------------------------


def test_youth_list_says_whether_each_record_has_an_open_case(make_youth, make_case, case_manager, as_user):
    """The registry shows the pill on every card, so the flag ships with the row.

    Annotated rather than resolved per record: a page of forty cards would
    otherwise be forty extra queries.
    """
    with_case = make_youth(name="Has A Case")
    make_case(case_manager, youth=with_case)
    make_youth(name="No Case Yet")

    response = as_user(case_manager).get("/api/v1/youth/")
    flags = {row["full_name"]: row["has_open_case"] for row in response.data["results"]}
    assert flags["Has A Case"] is True


def test_a_closed_case_does_not_count_as_an_open_one(make_youth, make_case, case_manager, as_user):
    from apps.cases.models import CaseStatus

    youth = make_youth(name="Exited Youth")
    case = make_case(case_manager, youth=youth)
    case.case_status = CaseStatus.EXITED
    case.save(update_fields=["case_status"])

    response = as_user(case_manager).get(f"/api/v1/youth/{youth.pk}/")
    assert response.data["has_open_case"] is False


def test_the_registry_row_carries_the_case_it_links_to(make_youth, make_case, case_manager, as_user):
    """The "Open case" pill has to open the case, which needs its id.

    Without this the pill could only report that a case exists, and the screen
    fell back to opening the youth's own edit form — a control that said one
    thing and did another.
    """
    youth = make_youth(name="Has A Case")
    case = make_case(case_manager, youth=youth)

    response = as_user(case_manager).get(f"/api/v1/youth/{youth.pk}/")
    assert str(response.data["open_case_id"]) == str(case.pk)


def test_a_youth_without_a_case_has_no_case_to_link_to(make_youth, outreach_worker, as_user):
    """Asked as the outreach worker: a case manager's scope resolves through the
    case, so a youth with no case is invisible to them by design (§7)."""
    make_youth(name="No Case Yet")
    rows = as_user(outreach_worker).get("/api/v1/youth/").data["results"]
    row = next(item for item in rows if item["full_name"] == "No Case Yet")
    assert row["open_case_id"] is None
    assert row["has_open_case"] is False
