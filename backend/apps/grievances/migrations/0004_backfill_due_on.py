"""Give the complaints already on file a deadline.

Without this every existing row reads `unscheduled` — no deadline, so never
late, so absent from the queue's late list. A grievance mechanism that quietly
exempts its own backlog from the clock it just acquired is measuring the wrong
thing from its first day.

Computed with the same `clock.due_on` the model uses, so a backfilled row and a
new one are judged by one rule. Rows already concluded are backfilled too: the
figure the mechanism is reported on is "resolved within the deadline", and a
resolved case with no deadline cannot be counted either way.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    from apps.grievances import clock

    Grievance = apps.get_model("grievances", "Grievance")
    for grievance in Grievance.objects.filter(due_on__isnull=True).iterator():
        if not grievance.date_raised:
            continue
        grievance.due_on = clock.due_on(raised_on=grievance.date_raised, severity=grievance.severity)
        grievance.save(update_fields=["due_on"])


def unbackfill(apps, schema_editor):
    """Reversible, and it really does clear them.

    A no-op reverse would leave a column the previous migration state says does
    not exist, which is the kind of half-reversal that makes a rollback worse
    than the fault it was rolling back.
    """
    Grievance = apps.get_model("grievances", "Grievance")
    Grievance.objects.update(due_on=None)


class Migration(migrations.Migration):
    dependencies = [("grievances", "0003_grievance_acknowledged_at_grievance_acknowledged_by_and_more")]

    operations = [migrations.RunPython(backfill, unbackfill)]
