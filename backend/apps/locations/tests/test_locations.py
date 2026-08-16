"""Location reference-data tests.

The serialisation of `parent` has a regression test because getting it wrong is
invisible from the backend: the API returns 200 with well-formed JSON, and only
a client trying to cascade the hierarchy discovers the identifiers do not match.
"""

import pytest

from apps.locations.models import Location, LocationLevel

pytestmark = pytest.mark.django_db


def test_parent_is_serialised_as_the_parent_code(locations, case_manager, as_user):
    """`parent` must be the parent's `code`, not its primary key.

    `code` is unique but not the primary key, so DRF's default related field
    emitted an integer id while `lookup_field` and every client identify a
    location by code. A cascading picker compared `child.parent` to
    `parent.code`, matched nothing, and left every dependent dropdown empty.
    """
    response = as_user(case_manager).get("/api/v1/locations/")
    assert response.status_code == 200

    rows = {row["code"]: row for row in response.data}
    assert rows["ET-OR"]["parent"] is None
    assert rows["ET-OR-ES"]["parent"] == "ET-OR"
    assert rows["ET-OR-ES-ADAMA"]["parent"] == "ET-OR-ES"


def test_every_child_parent_resolves_to_a_returned_code(locations, case_manager, as_user):
    """A cascade can only work if every non-root parent is itself in the payload."""
    response = as_user(case_manager).get("/api/v1/locations/")
    codes = {row["code"] for row in response.data}
    for row in response.data:
        if row["parent"] is not None:
            assert row["parent"] in codes, f"{row['code']} points at a parent not in the response"


def test_full_path_reads_root_first(locations):
    """'Oromia / East Shewa / Adama', not the reverse."""
    adama = Location.objects.get(code="ET-OR-ES-ADAMA")
    assert adama.full_path == "Oromia / East Shewa / Adama"


def test_hierarchy_rejects_a_wrongly_levelled_parent(locations):
    from django.core.exceptions import ValidationError

    bad = Location(code="X", name="Bad", level=LocationLevel.WOREDA, parent=locations["region"])
    with pytest.raises(ValidationError):
        bad.clean()
