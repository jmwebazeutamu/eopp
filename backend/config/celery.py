"""Celery application.

Drives the scheduled jobs in spec §4.13 / §6: stall detection, referral
confirmation-overdue alerts, follow-up due, onward and replacement referral
prompts, and 30/60/90-day retention reminders. Beat entries are registered by
each app's tasks module as its sprint lands (Sprint 4 onward).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("yep")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Smoke test that the worker is reachable.

    Deliberately does NOT set ignore_result: the point is to prove the result
    backend round-trips, which a discarded result cannot show. Remove once the
    Sprint 4 alert tasks exist.
    """
    return f"celery ok: {self.request.id}"
