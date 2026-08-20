from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FollowUpsConfig(AppConfig):
    name = "apps.followups"
    label = "followups"
    verbose_name = _("Follow-up and contact log")
