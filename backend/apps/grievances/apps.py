from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GrievancesConfig(AppConfig):
    name = "apps.grievances"
    label = "grievances"
    verbose_name = _("Grievances")
