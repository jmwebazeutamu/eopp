"""The one unauthenticated route in the WLT module.

Two properties matter and neither is about the numbers themselves: that an
anonymous caller can read it at all (the landing page has no token), and that
it cannot be persuaded to hand back anything outside the whitelist.
"""

import pytest
from django.core.cache import cache

from apps.wlt.api.public import PUBLIC_KEYS
from apps.wlt.policy import FALLBACKS

URL = "/api/v1/wlt/public-parameters/"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_the_page_cache():
    """The view is `cache_page`d for an hour, so one test's answer would
    otherwise be the next one's. Cleared around each test rather than switching
    the cache off, because the caching is part of what is under test below."""
    cache.clear()
    yield
    cache.clear()


def test_an_anonymous_caller_gets_the_rules(api):
    """The landing page is public and holds no token."""
    response = api.get(URL)
    assert response.status_code == 200
    assert set(response.data["parameters"]) == set(PUBLIC_KEYS)


def test_it_serves_the_seeded_values_not_a_copy_in_the_view(api, wlt_policy):
    """The whole reason this endpoint exists rather than a constant in the
    template: the page has to move when the programme moves the parameter."""
    from datetime import date

    from apps.wlt.models import PolicyParameter

    assert api.get(URL).data["parameters"]["gate.cla.min_groups"] == 8

    PolicyParameter.objects.filter(key="gate.cla.min_groups").delete()
    PolicyParameter.objects.create(key="gate.cla.min_groups", value=6, effective_from=date(2020, 1, 1))
    cache.clear()

    assert api.get(URL).data["parameters"]["gate.cla.min_groups"] == 6


def test_every_published_key_is_a_real_parameter(api):
    """A typo would publish a null forever and read on the page as a blank.

    `FALLBACKS` is the module's whole rule set in one place, so a key absent
    from it is a key nothing resolves.
    """
    unknown = [key for key in PUBLIC_KEYS if key not in FALLBACKS]
    assert unknown == []


def test_it_publishes_nothing_outside_the_whitelist(api):
    """Adding a parameter to the policy table must never silently publish it.

    The credit-facility leverage ratio is the example that matters: it is a
    programme control, it sits in the same table, and it has no business on a
    public page.
    """
    parameters = api.get(URL).data["parameters"]
    assert "gate.credit.max_leverage_ratio" not in parameters
    assert not any(key.startswith("enrolment.") for key in parameters)


def test_it_reports_no_group_or_member_data(api, wlt_group, wlt_members):
    """It is public, so the test is worth having explicitly rather than by
    reading the view. Only the configured rule set leaves this route."""
    body = api.get(URL).data
    assert set(body) == {"parameters"}
    assert all(isinstance(value, (int, float, str, bool)) for value in body["parameters"].values())


def test_the_answer_is_cached_rather_than_queried_per_visitor(api, wlt_policy):
    """It is the front door of the deployment, and the rule set changes by admin
    edit rather than by the minute.

    The consequence is stated rather than hidden: an edit reaches the page
    within `CACHE_SECONDS`, not instantly. That is the right trade for a
    published handbook value and the wrong one for anything operational, which
    is why nothing operational is on this route.
    """
    from datetime import date

    from apps.wlt.models import PolicyParameter

    assert api.get(URL).data["parameters"]["gate.cla.min_groups"] == 8

    PolicyParameter.objects.filter(key="gate.cla.min_groups").delete()
    PolicyParameter.objects.create(key="gate.cla.min_groups", value=6, effective_from=date(2020, 1, 1))

    # No cache clear: the previously computed answer is still being served.
    assert api.get(URL).data["parameters"]["gate.cla.min_groups"] == 8
