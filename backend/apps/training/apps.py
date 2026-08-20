from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TrainingConfig(AppConfig):
    name = "apps.training"
    label = "training"
    verbose_name = _("Training enrolment")
