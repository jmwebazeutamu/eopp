"""Self-service profile: what a user may change about their own account.

The boundary under test is escalation. `/users/me/` is reachable by every
authenticated role, so anything writable there is writable by everyone —
including a case manager who would like a wider §7 scope.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

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
    # Addresses are rows now; the wire shape is unchanged.
    assert {e.kind: e.address for e in person.emails.all()} == {
        "WORK": "Almaz@example.com",
        "PERSONAL": "almaz.home@example.com",
    }
    assert response.data["work_email"] == "Almaz@example.com"
    assert person.work_phone == "+251911000111"
    assert person.personal_phone == "+251911000222"
    # The response is the full /me/ shape, so one round trip refreshes the client.
    assert response.data["full_name"] == "Almaz Tesfaye"
    assert "access" in response.data


def test_the_response_carries_the_access_row_so_the_shell_can_rebuild(person, as_user):
    body = as_user(person).patch("/api/v1/users/me/", {"full_name": "X Y"}, format="json").data
    assert set(body["access"]) == {
        "case_scope",
        "case_write",
        "referral_scope",
        "referral_write",
        "group_scope",
        "group_write",
        "delivery_write",
    }


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
    person.emails.create(kind="WORK", address="mine@example.com")
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
    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}
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


# ---------------------------------------------------------------------------
# "An email is registered once" — enforced by the database, not by a serializer
# ---------------------------------------------------------------------------


def test_the_database_refuses_a_duplicate_address(person):
    """The constraint is the authority, so it is tested without the API.

    Two flat columns could not express this. `unique=True` on each would still
    permit one account's work address to equal another's personal.
    """
    from django.db import IntegrityError, transaction

    from apps.users.models import UserEmail

    other = User.objects.create_user("other", PASSWORD, full_name="Other", role=Role.CASE_MANAGER)
    person.emails.create(kind="WORK", address="one@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        UserEmail.objects.create(user=other, kind="PERSONAL", address="one@example.com")


def test_the_index_is_case_insensitive(person):
    """`A@x.com` and `a@x.com` are one inbox. A constraint that let both
    through would enforce nothing."""
    from django.db import IntegrityError, transaction

    other = User.objects.create_user("other2", PASSWORD, full_name="Other", role=Role.CASE_MANAGER)
    person.emails.create(kind="WORK", address="Mixed@Example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        other.emails.create(kind="WORK", address="mixed@example.com")


def test_one_address_of_each_kind_per_account(person):
    from django.db import IntegrityError, transaction

    person.emails.create(kind="WORK", address="a@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        person.emails.create(kind="WORK", address="b@example.com")


def test_deleting_an_account_releases_its_addresses(person):
    """The address means nothing without the account, and holding it would
    block whoever needs it next."""
    from apps.users.models import UserEmail

    person.emails.create(kind="WORK", address="released@example.com")
    person.delete()
    assert not UserEmail.objects.filter(address="released@example.com").exists()


def test_the_api_reports_a_duplicate_against_the_right_field(person, as_user):
    User.objects.create_user(
        "holder", PASSWORD, full_name="Holder", role=Role.CASE_MANAGER, work_email="held@example.com"
    )
    response = as_user(person).patch("/api/v1/users/me/", {"personal_email": "HELD@example.com"}, format="json")
    assert response.status_code == 400
    assert "personal_email" in response.data


def test_clearing_an_address_frees_it_for_another_account(person, as_user):
    other = User.objects.create_user("next", PASSWORD, full_name="Next", role=Role.CASE_MANAGER)
    as_user(person).patch("/api/v1/users/me/", {"work_email": "shared@example.com"}, format="json")
    as_user(person).patch("/api/v1/users/me/", {"work_email": ""}, format="json")

    response = as_user(other).patch("/api/v1/users/me/", {"work_email": "shared@example.com"}, format="json")
    assert response.status_code == 200
    assert response.data["work_email"] == "shared@example.com"


# ---------------------------------------------------------------------------
# The same questions asked of every role
# ---------------------------------------------------------------------------


def _make(role, partner):
    kwargs = {}
    if role == Role.PARTNER_STAFF:
        kwargs["partner"] = partner
    if role in (Role.OUTREACH_WORKER, Role.CASE_MANAGER, Role.SUPERVISOR):
        kwargs["woreda_assignment"] = ["Adama"]
    return User.objects.create_user(f"perm-{role.lower()}", PASSWORD, full_name=f"P {role}", role=role, **kwargs)


@pytest.mark.parametrize("role", Role.values)
def test_every_role_can_read_and_edit_its_own_profile(role, partner, as_user):
    """The profile is the one screen nobody is scoped out of.

    A trainer and a partner staff account see no case content at all under §7,
    and still have a name and a password of their own.
    """
    user = _make(role, partner)
    client = as_user(user)

    assert client.get("/api/v1/users/me/").status_code == 200
    assert client.patch("/api/v1/users/me/", {"full_name": "Renamed"}, format="json").status_code == 200
    assert (
        client.post(
            "/api/v1/users/me/password/",
            {"current_password": PASSWORD, "new_password": "brand-New-Pass-42"},
            format="json",
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", Role.values)
def test_no_role_can_make_itself_an_administrator(role, partner, as_user):
    """The escalation every role would try, asked of every role.

    A single missing `read_only` on a self-service route hands §7 to whoever
    notices, so this is asserted for all ten rather than for a representative.
    """
    user = _make(role, partner)
    as_user(user).patch(
        "/api/v1/users/me/",
        {"role": Role.SYSTEM_ADMIN, "woreda_assignment": ["Adama", "Bishoftu", "Lume"], "is_superuser": True},
        format="json",
    )
    user.refresh_from_db()
    assert user.role == role
    assert user.is_superuser is False


@pytest.mark.parametrize("role", Role.values)
def test_user_administration_stays_with_the_administrator(role, partner, as_user):
    """§7 grants the account list to the system administrator alone, and the
    profile routes did not widen it."""
    user = _make(role, partner)
    expected = 200 if role == Role.SYSTEM_ADMIN else 403
    assert as_user(user).get("/api/v1/users/").status_code == expected


# ---------------------------------------------------------------------------
# Changing a password ends every other session
# ---------------------------------------------------------------------------


def _tokens_for(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def test_a_token_issued_before_the_change_stops_working(person, api):
    """The point of changing a password when you think you are compromised.

    Before this, a stolen token outlived the change by up to its full window —
    an hour for an access token, fourteen days for a refresh.
    """
    stolen, _ = _tokens_for(person)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {stolen}")
    assert api.get("/api/v1/users/me/").status_code == 200

    # A minute later, not the same second: `iat` is whole seconds and the
    # check allows one second of slack so a freshly issued token is not
    # refused on its first use.
    with freeze_time(timezone.now() + timedelta(minutes=1)):
        person.set_password("brand-New-Pass-42")
        person.save()

    assert api.get("/api/v1/users/me/").status_code == 401


def test_a_token_issued_after_the_change_works(person, api):
    person.set_password("brand-New-Pass-42")
    person.save()
    fresh, _ = _tokens_for(person)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {fresh}")
    assert api.get("/api/v1/users/me/").status_code == 200


def test_an_administrator_reset_also_cuts_off_stolen_sessions(person, api):
    """The case that matters most is the one where the account holder is not
    the one asking. The stamp is in `set_password`, so every route that resets
    a password — the admin, the management command — ends other sessions too."""
    stolen, _ = _tokens_for(person)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {stolen}")
    assert api.get("/api/v1/users/me/").status_code == 200

    from django.core.management import call_command

    with freeze_time(timezone.now() + timedelta(minutes=1)):
        call_command("set_password", person.username, "--generate", verbosity=0)

    assert api.get("/api/v1/users/me/").status_code == 401


def test_the_device_that_changed_the_password_stays_signed_in(person, as_user):
    """Signing someone out of the screen they just used correctly would teach
    them not to use it."""
    response = as_user(person).post(
        "/api/v1/users/me/password/",
        {"current_password": PASSWORD, "new_password": "brand-New-Pass-42"},
        format="json",
    )
    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}

    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    assert client.get("/api/v1/users/me/").status_code == 200


def test_accounts_that_have_never_changed_a_password_are_left_alone(person, api):
    """A deployment must not sign the whole programme out.

    Accounts predating the column have no stamp, so there is nothing to compare
    against and their sessions stand.
    """
    User.objects.filter(pk=person.pk).update(password_changed_at=None)
    token, _ = _tokens_for(person)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get("/api/v1/users/me/").status_code == 200
