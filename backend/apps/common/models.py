"""Abstract base models shared across every entity app.

Not a spec entity. Spec §4's type-translation guide maps `System ID` to a UUID
primary key on all fourteen entities, so that lives here once rather than being
repeated fourteen times.
"""

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Primary key per spec §4: UUIDField(primary_key=True, default=uuid4, editable=False)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Row-level create/update stamps.

    Distinct from the domain date fields in spec §4 (`initiated_date`,
    `assessed_date`, and so on): those record when something happened in the
    real world, these record when the row was written. `updated_at` is also what
    the mobile client's `updated_since` delta sync reads (spec §2, Sprint 8).
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """The default base for platform entities."""

    class Meta:
        abstract = True
