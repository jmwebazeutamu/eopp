"""The handful of programme rules the public landing page states.

**Why this exists at all.** The landing page prints thresholds — a Self Help
Group is 15 to 25 women, eight groups form a CLA, Phase 2 needs twelve weeks of
fund adequacy. CLAUDE.md and the WLT UI handoff both say the same thing about
numbers like these: *thresholds live in `wlt.PolicyParameter`, never in code,
and never typed into a template.* The handoff restates it precisely because it
is the rule somebody breaks by copying a prototype's illustrative markup.

Several of these values are marked NEEDS FSCO and two are disputed in the source
handbook. Hardcoding them into a public page guarantees that the first time the
programme settles one, the front door contradicts the application behind it.

**What it is not.** Not live data. It reports no group, no member, no woreda and
no count — only the configured rule set, resolved at national scope, which is
the same set the printed handbook carries. That is why it can be public.

The whitelist is the control: a key absent from `PUBLIC_KEYS` cannot be read
through this route however the caller asks, so adding a parameter to the policy
table never silently publishes it.
"""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.wlt import policy

#: Exactly the parameters the landing page states, and nothing else.
#:
#: Grouped the way the page reads them so a reviewer can check the page against
#: this list rather than against the whole policy table.
PUBLIC_KEYS = (
    # Structure — the stat strip and the phase rail's Forming step.
    "group.size.hard_min",
    "group.size.hard_max",
    "gate.cla.min_groups",
    "gate.cla.delegates_per_group",
    "gate.federation.min_clas",
    "gate.federation.min_cla_months",
    # Phase 1 exit.
    "gate.p1.meeting_adherence_pct",
    "gate.p1.attendance_pct",
    "gate.p1.savings_compliance_pct",
    "gate.p1.min_savings_meetings",
    "gate.p1.max_par30_pct",
    # Phase 2 exit.
    "gate.p2.fund_adequacy_weeks",
    "gate.p2.completed_loan_cycles",
    "gate.p2.max_par30_pct",
    "gate.p2.min_weeks_since_p1",
)

#: One hour. These change by admin edit, not by the minute, and the page is the
#: most-requested unauthenticated route in the deployment — an uncached read
#: would put a policy query in front of every visitor.
CACHE_SECONDS = 60 * 60


@method_decorator(cache_page(CACHE_SECONDS), name="get")
class PublicParametersView(APIView):
    """The configured rule set, at national scope.

    Deliberately **not** geography-scoped. `policy.resolve` walks most-specific
    place first, and an anonymous caller has no place — serving a kebele
    variation to whoever asked would state one kebele's rules as the
    programme's.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        return Response({"parameters": {key: policy.resolve(key) for key in PUBLIC_KEYS}})
