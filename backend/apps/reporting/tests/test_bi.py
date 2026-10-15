import pytest
from django.conf import settings
from django.db import connection

from apps.reporting import views
from apps.youth.models import Youth

# Columns a young person's record carries that no bi view may repeat. Derived
# from the model, so a field added to Youth is covered without editing this file;
# the shared plumbing columns are the only allowance.
SHARED = {"id", "created_at", "updated_at", "woreda"}


def _columns():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = %s",
            [settings.BI_SCHEMA],
        )
        return cur.fetchall()


@pytest.mark.django_db
def test_every_declared_view_exists_and_only_those():
    assert {t for t, _ in _columns()} == set(views.view_names())


@pytest.mark.django_db
def test_no_view_exposes_a_youth_field():
    personal = {f.column for f in Youth._meta.concrete_fields} - SHARED
    assert not [(t, col) for t, col in _columns() if col in personal]


@pytest.mark.django_db
def test_partner_rate_is_withheld_below_the_provisional_floor():
    from apps.dashboard.rules import PROVISIONAL_MIN_DENOMINATOR

    with connection.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {settings.BI_SCHEMA}.partner_closure "
            f"WHERE closed < {PROVISIONAL_MIN_DENOMINATOR} AND failed_percent IS NOT NULL"
        )
        assert cur.fetchone()[0] == 0
