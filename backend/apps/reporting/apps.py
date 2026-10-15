from django.apps import AppConfig
from django.db.models.signals import post_migrate, pre_migrate


def _drop(sender, using="default", **kwargs):
    # A view pins the columns it reads, so a migration that alters one would fail
    # while the schema stands. Dropping first and rebuilding after is what lets
    # any later migration touch any table.
    from django.db import connections

    from apps.reporting import views

    with connections[using].cursor() as cur:
        cur.execute(views.drop_sql())


def _build(sender, using="default", **kwargs):
    from django.db import connections

    from apps.reporting import grants, views

    with connections[using].cursor() as cur:
        cur.execute(views.create_sql())
    grants.reapply(using)


class ReportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    label = "reporting"

    def ready(self):
        pre_migrate.connect(_drop, sender=self, dispatch_uid="reporting.drop_bi")
        post_migrate.connect(_build, sender=self, dispatch_uid="reporting.build_bi")
