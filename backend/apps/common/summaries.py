"""Counter summaries for the screens' mini dashboards.

Every list screen carries a row of counters that double as filters. Two things
make them worth computing on the server rather than in the client:

1. **They must count the whole scoped set, not the loaded page.** A case manager
   sees 25 rows at a time; "6 stalled" is a fact about their caseload, not about
   the page they happen to be on.
2. **Bandwidth.** The brief's users are on 3G or worse. One summary request beats
   five list requests issued only to read their `count`.

The shape is deliberately uniform — `{total, counters: [{param, value, label,
count}]}` — so one component renders all of them and each counter carries the
query parameter it toggles.
"""

from django.db.models import Count


def counters_for(queryset, *, param, field, choices, include_zero=True):
    """Count `queryset` by `field`, in the order `choices` declares.

    `choices` is a TextChoices class or any (value, label) iterable, which keeps
    the counter order stable and the labels identical to the ones the serializers
    already return — a counter reading "Referral Pending" must match the chip on
    the row it filters to.
    """
    pairs = choices.choices if hasattr(choices, "choices") else list(choices)

    # Counted through a fresh queryset over the same rows rather than by
    # grouping the caller's.
    #
    # A viewset queryset often carries annotations — UserViewSet joins
    # managed_cases for `caseload_count`, and a join multiplies rows — and any
    # existing annotation is added to the GROUP BY, so `.values(field)` groups by
    # more than the field asked for. Both faults are silent: the first inflates
    # counts to the size of the join, the second splits one status across
    # several rows so all but the last are dropped. A subquery on the primary
    # keys discards annotations, joins and ordering together.
    rows = queryset.model.objects.filter(pk__in=queryset.values("pk"))
    counts = {row[field]: row["n"] for row in rows.values(field).annotate(n=Count("id"))}

    return [
        {"param": param, "value": value, "label": str(label), "count": counts.get(value, 0)}
        for value, label in pairs
        if include_zero or counts.get(value, 0)
    ]


def summary_response(queryset, counters):
    """The payload every `summary` action returns.

    `total` is counted the same distinct way as the counters, so a joined
    annotation cannot make the total disagree with the parts.
    """
    total = queryset.model.objects.filter(pk__in=queryset.values("pk")).count()
    return {"total": total, "counters": counters}
