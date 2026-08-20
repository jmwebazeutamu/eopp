from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WltConfig(AppConfig):
    name = "apps.wlt"
    label = "wlt"
    verbose_name = _("WLT group module")
