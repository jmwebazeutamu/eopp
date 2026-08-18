# Generated manually for case action history.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def backfill_case_actions(apps, schema_editor):
    Case = apps.get_model("cases", "Case")
    CaseAction = apps.get_model("cases", "CaseAction")
    for case in Case.objects.exclude(next_action="").iterator():
        CaseAction.objects.create(
            case=case,
            action_type="NEXT_ACTION",
            body=case.next_action,
            assigned_to_id=case.next_action_owner_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0002_historicalprofilingrecord_pathwayassignment_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseAction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("NEXT_ACTION", "Next action"),
                            ("FEEDBACK", "Feedback"),
                            ("FOLLOW_UP", "Follow-up"),
                            ("STATUS_NOTE", "Status note"),
                        ],
                        default="NEXT_ACTION",
                        max_length=20,
                        verbose_name="action type",
                    ),
                ),
                ("body", models.TextField(verbose_name="body")),
                (
                    "status",
                    models.CharField(
                        choices=[("OPEN", "Open"), ("DONE", "Done"), ("SUPERSEDED", "Superseded")],
                        default="OPEN",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="due date")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="resolved at")),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_case_actions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned to",
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="actions",
                        to="cases.case",
                        verbose_name="case",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_case_actions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="created by",
                    ),
                ),
            ],
            options={
                "verbose_name": "case action",
                "verbose_name_plural": "case actions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="caseaction",
            index=models.Index(fields=["case", "action_type", "status"], name="cases_casea_case_id_13098e_idx"),
        ),
        migrations.AddIndex(
            model_name="caseaction",
            index=models.Index(fields=["created_at"], name="cases_casea_created_610b45_idx"),
        ),
        migrations.RunPython(backfill_case_actions, migrations.RunPython.noop),
    ]
