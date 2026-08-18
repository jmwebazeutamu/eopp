"""Self-service profile: what a user may change about their own account.

The boundary under test is escalation. `/users/me/` is reachable by every
authenticated role, so anything writable there is writable by everyone —
including a case manager who would like a wider §7 scope.
"""

import pytest

from apps.users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db

PASSWORD = "pw-Test-12345"


@pytest.fixture
def person(db):
    return User.objects.create_user(
        "p1", PASSWORD, full_name="Case Manager One", role=Role.CASE_MANAGER, woreda_assignment=["Adama"]
    )


# ---------------------------------------------------------------------------
# Editing your own details
# ---------------------------------------------------------------------------


def test_a_user_can_change_their_own_name_and_contacts(person, as_user):
    response = as_user(person).patch(
        "/api/v1/users/me/",
        {
            "full_name": "Almaz Tesfaye",
            "work_email": "Almaz@Example.COM",
            "personal_email": "almaz.home@example.com",
            "work_phone": "+251911000111",
            "personal_phone": "+251911000222",
        },
        format="json",
    )
    assert response.status_code == 200
    person.refresh_from_db()
    assert person.full_name == "Almaz Tesfaye"
    # Normalised: the domain is lowercased, so two spellings cannot both be held.
    assert person.work_email == "Almaz@example.com"
    assert person.personal_email == "almaz.home@example.com"
    assert person.work_phone == "+251911000111"
    assert person.personal_phone == "+251911000222"
    # The response is the full /me/ shape, so one round trip refreshes the client.
    assert response.data["full_name"] == "Almaz Tesfaye"
    assert "access" in response.data


def test_the_response_carries_the_access_row_so_the_shell_can_rebuild(person, as_user):
    body = as_user(person).patch("/api/v1/users/me/", {"full_name": "X Y"}, format="json").data
    assert set(body["access"]) == {"case_scope", "case_write", "referral_scope", "referral_write"}


def test_a_blank_name_is_refused(person, as_user):
    response = as_user(person).patch("/api/v1/users/me/", {"full_name": "   "}, format="json")
    assert response.status_code == 400
    assert "full_name" in response.data


@pytest.mark.parametrize("held_as", ["work_email", "personal_email"])
@pytest.mark.parametrize("claimed_as", ["work_email", "personal_email"])
def test_an_email_another_account_holds_is_refused(person, as_user, held_as, claimed_as):
    """An address is one address, whichever slot either side keeps it in."""
    User.objects.create_user(
        "other", PASSWORD, full_name="Other", role=Role.CASE_MANAGER, **{held_as: "taken@example.com"}
    )
    response = as_user(person).patch("/api/v1/users/me/", {claimed_as: "TAKEN@example.com"}, format="json")
    assert response.status_code == 400
    assert claimed_as in response.data


def test_the_two_addresses_on_one_account_must_differ(person, as_user):
    response = as_user(person).patch(
        "/api/v1/users/me/",
        {"work_email": "same@example.com", "personal_email": "same@example.com"},
        format="json",
    )
    assert response.status_code == 400
    assert "personal_email" in response.data


def test_a_personal_number_is_optional(person, as_user):
    """Field staff are not required to hand over a personal number to use the
    system; every contact point is blank by default and may stay blank."""
    assert as_user(person).patch("/api/v1/users/me/", {"work_phone": "+251911000111"}, format="json").status_code == 200
    person.refresh_from_db()
    assert person.personal_phone == ""


def test_keeping_your_own_email_is_not_a_clash_with_yourself(person, as_user):
    person.work_email = "mine@example.com"
    person.save(update_fields=["work_email"])
    assert (
        as_user(person).patch("/api/v1/users/me/", {"work_email": "mine@example.com"}, format="json").status_code == 200
    )


# ---------------------------------------------------------------------------
# Escalation — the reason this is a separate serializer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"role": Role.SYSTEM_ADMIN}, "role"),
        ({"woreda_assignment": ["Adama", "Bishoftu", "Lume"]}, "woreda_assignment"),
        ({"account_status": AccountStatus.ACTIVE}, "account_status"),
        ({"is_staff": True}, "is_staff"),
        ({"is_superuser": True}, "is_superuser"),
        ({"username": "someone-else"}, "username"),
    ],
)
def test_self_service_cannot_widen_its_own_access(person, as_user, payload, field):
    """Every one of these is an escalation if it is writable here.

    They are not merely ignored by a permission check — they are absent from
    `ProfileSerializer`, so there is no field to write.
    """
    before = getattr(person, field)
    response = as_user(person).patch("/api/v1/users/me/", payload, format="json")
    assert response.status_code == 200
    person.refresh_from_db()
    assert getattr(person, field) == before


def test_a_self_edit_is_recorded_in_the_audit_trail(person, as_user):
    """§9 wants date and actor on a change. HistoricalRecords covers it."""
    as_user(person).patch("/api/v1/users/me/", {"full_name": "Renamed"}, format="json")
    assert person.history.filter(full_name="Renamed").exists()


# ---------------------------------------------------------------------------
# Changing your own password
# ---------------------------------------------------------------------------


def test_a_user_can_change_their_own_password(person, as_user):
    response = as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": PASSWORD, "new_password": "new-Passw0rd-9876"},
        format="json",
    )
    assert response.status_code == 204
    person.refresh_from_db()
    assert person.check_password("new-Passw0rd-9876")


def test_the_current_password_is_required_and_checked(person, as_user):
    """An access token lasts an hour and these are shared machines: an unlocked
    screen must not be enough to take the account over."""
    response = as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": "not-my-password", "new_password": "new-Passw0rd-9876"},
        format="json",
    )
    assert response.status_code == 400
    assert "current_password" in response.data
    person.refresh_from_db()
    assert person.check_password(PASSWORD)


def test_django_password_validators_run(person, as_user):
    response = as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": PASSWORD, "new_password": "password"},
        format="json",
    )
    assert response.status_code == 400
    assert "new_password" in response.data


def test_the_new_password_must_differ_from_the_old(person, as_user):
    response = as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": PASSWORD, "new_password": PASSWORD},
        format="json",
    )
    assert response.status_code == 400


def test_signing_in_with_the_old_password_stops_working(person, as_user, api):
    as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": PASSWORD, "new_password": "new-Passw0rd-9876"},
        format="json",
    )
    old = api.post("/api/v1/users/token/", {"username": "p1", "password": PASSWORD}, format="json")
    new = api.post("/api/v1/users/token/", {"username": "p1", "password": "new-Passw0rd-9876"}, format="json")
    assert old.status_code == 401
    assert new.status_code == 200


def test_an_anonymous_caller_reaches_neither_route(api):
    assert api.patch("/api/v1/users/me/", {"full_name": "x"}, format="json").status_code in (401, 403)
    assert api.post("/api/v1/users/me/password/", {}, format="json").status_code in (401, 403)
