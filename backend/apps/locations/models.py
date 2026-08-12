"""Location reference data — spec §10 Sprint 1 ("Location and reference data").

Spec §4.1 stores a youth's location as four **text** fields (region, zone,
woreda, kebele), and §4 is the source of truth for the schema, so those stay
text on Youth. This app is the controlled vocabulary behind them: it drives the
dropdowns in the web and mobile clients, validates what gets written, and gives
`User.woreda_assignment` (§4.12) a list to choose from.

Keeping the reference data in its own app rather than adding it to the §2.2 app
list is the "adjust as needed" the spec allows — location is cross-cutting, used
by Youth, Case, Partner (§4.11 `woreda_coverage`) and User alike.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class LocationLevel(models.TextChoices):
    """Ethiopia's administrative hierarchy, as used by the programme."""

    REGION = "REGION", _("Region")
    ZONE = "ZONE", _("Zone")
    WOREDA = "WOREDA", _("Woreda")
    KEBELE = "KEBELE", _("Kebele")


# Which level may sit under which. A region has no parent; everything else does.
PARENT_LEVEL = {
    LocationLevel.REGION: None,
    LocationLevel.ZONE: LocationLevel.REGION,
    LocationLevel.WOREDA: LocationLevel.ZONE,
    LocationLevel.KEBELE: LocationLevel.WOREDA,
}


class LocationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def woredas(self):
        return self.filter(level=LocationLevel.WOREDA)

    def regions(self):
        return self.filter(level=LocationLevel.REGION)


class Location(models.Model):
    """One administrative unit at any level of the hierarchy.

    Deliberately not a `BaseModel`: reference data is administered, not part of
    a case record, and a stable human-readable `code` is more useful here than a
    UUID for imports and cross-system matching. It still carries timestamps.
    """

    code = models.CharField(
        _("code"),
        max_length=32,
        unique=True,
        help_text=_("Stable identifier, e.g. ET-OR-ES-ADAMA. Used by imports and external systems."),
    )
    name = models.CharField(_("name"), max_length=128)
    level = models.CharField(_("level"), max_length=8, choices=LocationLevel.choices, db_index=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name=_("parent"),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivate rather than delete: existing records reference this name."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = LocationQuerySet.as_manager()

    class Meta:
        verbose_name = _("location")
        verbose_name_plural = _("locations")
        ordering = ["level", "name"]
        constraints = [
            # Two woredas may share a name across zones, but not within one.
            models.UniqueConstraint(fields=["parent", "name", "level"], name="unique_location_within_parent"),
        ]
        indexes = [models.Index(fields=["level", "is_active"])]

    def __str__(self):
        return self.name

    def clean(self):
        expected_parent_level = PARENT_LEVEL[self.level]

        if expected_parent_level is None:
            if self.parent_id:
                raise ValidationError({"parent": _("A region has no parent.")})
            return

        if not self.parent_id:
            raise ValidationError({"parent": _("A %(level)s needs a parent.") % {"level": self.get_level_display()}})

        if self.parent.level != expected_parent_level:
            raise ValidationError(
                {
                    "parent": _("A %(level)s must sit under a %(expected)s, not a %(actual)s.")
                    % {
                        "level": self.get_level_display(),
                        "expected": expected_parent_level.label,
                        "actual": self.parent.get_level_display(),
                    }
                }
            )

    def save(self, *args, **kwargs):
        # Reference data is edited by administrators through the admin and by
        # seed scripts. Validating here means neither path can build a hierarchy
        # that the dropdowns cannot render.
        self.full_clean(exclude=None, validate_unique=False)
        return super().save(*args, **kwargs)

    @property
    def ancestors(self):
        """Walk up to the region, nearest parent first."""
        node, chain = self.parent, []
        while node is not None:
            chain.append(node)
            node = node.parent
        return chain

    @property
    def full_path(self):
        """'Oromia / East Shewa / Adama' — for display and disambiguation.

        `ancestors` runs nearest-parent-first, so it is reversed on its own
        before the node's own name is appended.
        """
        return " / ".join([node.name for node in reversed(self.ancestors)] + [self.name])
