"""`scopable_woredas` on /me/ — what the shell's woreda scope selector offers.

`woreda_assignment` could not serve the purpose on its own: an ALL-scope
account carries an empty one, which is why the header rendered "Woreda: —" for
exactly the users who can see every woreda.

This is presentation, not permission. `ScopedQuerySetMixin` still decides what
an account may read; this only says which narrowings are worth offering.
"""

import pytest

from apps.locations.models import Location, LocationLevel
from apps.users.models import Role, User
from apps.users.serializers import CurrentUserSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def woredas():
    """A minimal slice of the hierarchy. Locations validate their parent, so a
    woreda cannot be created without the zone and region above it."""
    region = Location.objects.create(name="Oromia", code="OR", level=LocationLevel.REGION, is_active=True)
    zone = Location.objects.create(
        name="East Shewa", code="OR-ES", level=LocationLevel.ZONE, parent=region, is_active=True
    )
    for name, code, active in [
        ("Bishoftu", "OR-ES-BI", True),
        ("Adama", "OR-ES-AD", True),
        ("Retired", "OR-ES-RT", False),
    ]:
        Location.objects.create(name=name, code=code, level=LocationLevel.WOREDA, parent=zone, is_active=active)


def offered(user):
    return CurrentUserSerializer(user).data["scopable_woredas"]


def test_all_scope_gets_every_active_woreda_in_name_order(woredas):
    admin = User.objects.create_user(username="a1", password="x", role=Role.SYSTEM_ADMIN)
    assert offered(admin) == ["Adama", "Bishoftu"]


def test_all_scope_excludes_other_levels_and_inactive_rows(woredas):
    # A region is not a woreda, and a retired woreda would offer a filter that
    # narrows to nothing.
    pm = User.objects.create_user(username="pm1", password="x", role=Role.PROGRAMME_MANAGER)
    assert "Oromia" not in offered(pm)
    assert "Retired" not in offered(pm)


def test_narrower_scope_gets_only_its_own_assignment(woredas):
    # Offering more would offer a filter that returns nothing: the scoped
    # queryset will not produce rows outside the assignment anyway.
    cm = User.objects.create_user(username="c1", password="x", role=Role.CASE_MANAGER, woreda_assignment=["Adama"])
    assert offered(cm) == ["Adama"]


def test_unassigned_narrow_scope_gets_an_empty_list_not_every_woreda(woredas):
    # The failure this guards against is a scope selector that hands a case
    # manager the whole programme's woredas because their assignment is blank.
    cm = User.objects.create_user(username="c2", password="x", role=Role.CASE_MANAGER, woreda_assignment=[])
    assert offered(cm) == []
