from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EnterprisesConfig(AppConfig):
    name = "apps.enterprises"
    label = "enterprises"
    verbose_name = _("Enterprises")
