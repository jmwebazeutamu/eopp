from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PlacementsConfig(AppConfig):
    name = "apps.placements"
    label = "placements"
    verbose_name = _("Placements")
