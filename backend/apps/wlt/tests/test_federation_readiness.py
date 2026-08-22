"""Federation readiness — the CLA screen one level up.

`cla_readiness` counts groups in a kebele; this counts CLAs in a woreda. The
gate has two conditions, membership and maturity, so both are reported: a
woreda with ten new CLAs is not ready the way one with ten established CLAs is.

Federation is not reachable in the pre-pilot (decision D8). This reports the
arithmetic so it is visible rather than assumed — the gate's own docstring
makes the point that Phase 4 needs more groups in one woreda than the largest
regional allocation holds.
"""

from datetime import date, timedelta

import pytest

from apps.wlt import reporting
from apps.wlt.models import CLA

pytestmark = pytest.mark.django_db

URL = "/api/v1/wlt/reports/federation-readiness/"


def _row(rows, woreda):
    return next(r for r in rows if r["woreda"] == woreda.name)


def _cla(name, kebele, formed_on, status="ACTIVE"):
    return CLA.objects.create(name=name, kebele=kebele, formed_on=formed_on, status=status)


class TestTheReport:
    def test_a_woreda_with_no_clas_is_short_the_whole_threshold(self, db, wlt_locations):
        row = _row(reporting.federation_readiness(), wlt_locations["woreda"])

        assert row["active_clas"] == 0
        assert row["clas_short"] == row["threshold"]

    def test_active_clas_are_counted_and_the_shortfall_falls(self, db, wlt_locations):
        _cla("CLA One", wlt_locations["kebele"], date.today())
        _cla("CLA Two", wlt_locations["other_kebele"], date.today())

        row = _row(reporting.federation_readiness(), wlt_locations["woreda"])

        assert row["active_clas"] == 2
        assert row["clas_short"] == row["threshold"] - 2

    def test_a_dissolved_cla_counts_for_nothing(self, db, wlt_locations):
        _cla("Gone", wlt_locations["kebele"], date.today(), status="DISSOLVED")

        row = _row(reporting.federation_readiness(), wlt_locations["woreda"])
        assert row["active_clas"] == 0

    def test_maturity_is_reported_separately_from_membership(self, db, wlt_locations):
        """The gate has two conditions. Ten CLAs formed last week is not the
        same readiness as ten that have been operating a year."""
        _cla("New", wlt_locations["kebele"], date.today())
        _cla("Established", wlt_locations["other_kebele"], date.today() - timedelta(days=800))

        row = _row(reporting.federation_readiness(), wlt_locations["woreda"])

        assert row["active_clas"] == 2
        assert row["mature_clas"] == 1

    def test_a_cla_in_another_woreda_does_not_count(self, db, wlt_locations):
        from apps.locations.models import Location, LocationLevel

        elsewhere = Location.objects.create(
            code="ET-XX-OTHER", name="Elsewhere", level=LocationLevel.WOREDA, parent=wlt_locations["zone"]
        )
        kebele = Location.objects.create(
            code="ET-XX-OTHER-01", name="Elsewhere 01", level=LocationLevel.KEBELE, parent=elsewhere
        )
        _cla("Theirs", kebele, date.today())

        rows = reporting.federation_readiness()
        assert _row(rows, wlt_locations["woreda"])["active_clas"] == 0
        assert _row(rows, elsewhere)["active_clas"] == 1

    def test_the_closest_woreda_sorts_first(self, db, wlt_locations):
        """Same rule as the CLA screen: the ones within reach lead."""
        _cla("One", wlt_locations["kebele"], date.today())

        rows = reporting.federation_readiness()
        assert rows[0]["clas_short"] <= rows[-1]["clas_short"]


class TestTheEndpoint:
    def test_a_facilitator_reads_the_woreda_holding_her_kebele(self, as_user, facilitator, wlt_locations):
        """Her scope is a kebele; a federation forms in the woreda above it.
        Without that walk her screen would be empty rather than informative."""
        facilitator.wlt_scope_location = wlt_locations["kebele"]
        facilitator.save(update_fields=["wlt_scope_location"])

        response = as_user(facilitator).get(URL)

        assert response.status_code == 200
        assert {row["woreda"] for row in response.data["rows"]} == {wlt_locations["woreda"].name}

    def test_a_woreda_officer_sees_her_own_woreda_only(self, as_user, woreda_officer, wlt_locations):
        from apps.locations.models import Location, LocationLevel

        Location.objects.create(
            code="ET-XX-FAR", name="Far Woreda", level=LocationLevel.WOREDA, parent=wlt_locations["zone"]
        )
        response = as_user(woreda_officer).get(URL)

        assert {row["woreda"] for row in response.data["rows"]} == {wlt_locations["woreda"].name}

    def test_it_is_refused_across_the_module_boundary(self, as_user, case_manager):
        assert as_user(case_manager).get(URL).status_code == 403
