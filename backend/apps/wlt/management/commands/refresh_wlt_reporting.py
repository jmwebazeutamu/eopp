from django.core.management.base import BaseCommand

from apps.wlt import reporting


class Command(BaseCommand):
    help = "Rebuild the WLT materialized views."

    def handle(self, *args, **options):
        reporting.refresh()
        self.stdout.write(self.style.SUCCESS("WLT reporting views refreshed."))
