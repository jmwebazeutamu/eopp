"""WLT fixtures, borrowed.

The grievance channel is shared by both modules, so its tests need a savings
group and a facilitator — and those fixtures live in the WLT app's own
conftest, which pytest does not make visible to a sibling app.

Re-exported rather than rewritten. A second `wlt_group` fixture built by hand
here would drift from the real one within a sprint, and the boundary tests below
are only worth anything if the group they scope against is the group the module
actually produces.
"""

import pytest

from apps.grievances import services
from apps.grievances.models import ComplaintType, RaisedBy
from apps.wlt.tests.conftest import (  # noqa: F401
    facilitator,
    make_wlt_member,
    wlt_draft,
    wlt_group,
    wlt_locations,
    wlt_members,
    wlt_policy,
    woreda_officer,
)


@pytest.fixture
def raise_grievance(db, supervisor):
    """Shared by both grievance test modules, so the safeguarding file can use
    an ordinary complaint as its control."""

    def _raise(**fields):
        fields.setdefault("complaint_type", ComplaintType.SERVICE_QUALITY)
        fields.setdefault("raised_by", RaisedBy.YOUTH)
        fields.setdefault("summary", "The training centre had no materials for three weeks.")
        fields.setdefault("assigned_staff", supervisor)
        fields.setdefault("woreda", "Adama")
        return services.raise_grievance(**fields)

    return _raise
