"""Emails become rows, so "registered once" can be a database constraint.

Order matters here and the generated migration had it wrong: it dropped the
two columns and created the table, with nothing in between, which is a schema
change that discards every address on file. The table is created first, the
addresses are copied into it, and only then are the columns removed.

The copy is reversible. Going backwards puts each address back in the column
it came from, so the migration can be rolled back without loss — except where
two accounts already share an address, which the new constraint forbids and
the old columns allowed. That case is reported rather than resolved by
guessing whose address it is.
"""

from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.text
import uuid
import simple_history.models
from django.conf import settings


def copy_addresses_into_rows(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserEmail = apps.get_model("users", "UserEmail")
    seen = {}
    for user in User.objects.exclude(work_email="", personal_email=""):
        for kind, address in (("WORK", user.work_email), ("PERSONAL", user.personal_email)):
            address = (address or "").strip()
            if not address:
                continue
            key = address.lower()
            if key in seen:
                # The old columns permitted this; the new index does not. Left
                # for a person to resolve rather than assigned by guesswork.
                raise RuntimeError(
                    f"{address!r} is held by more than one account "
                    f"({seen[key]} and {user.username}). Resolve the duplicate, then migrate."
                )
            seen[key] = user.username
            UserEmail.objects.create(user=user, kind=kind, address=address)


def copy_rows_back_into_columns(apps, schema_editor):
    UserEmail = apps.get_model("users", "UserEmail")
    User = apps.get_model("users", "User")
    for row in UserEmail.objects.all():
        field = "work_email" if row.kind == "WORK" else "personal_email"
        User.objects.filter(pk=row.user_id).update(**{field: row.address})


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_contact_points"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalUserEmail",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(blank=True, db_index=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, db_index=True, editable=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[("WORK", "Work"), ("PERSONAL", "Personal")], max_length=16, verbose_name="kind"
                    ),
                ),
                ("address", models.EmailField(max_length=254, verbose_name="address")),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="Deleting the account removes its addresses; they mean nothing without it.",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical user email",
                "verbose_name_plural": "historical user emails",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="UserEmail",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[("WORK", "Work"), ("PERSONAL", "Personal")], max_length=16, verbose_name="kind"
                    ),
                ),
                ("address", models.EmailField(max_length=254, verbose_name="address")),
                (
                    "user",
                    models.ForeignKey(
                        help_text="Deleting the account removes its addresses; they mean nothing without it.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="emails",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "user email",
                "verbose_name_plural": "user emails",
                "ordering": ["kind"],
                "constraints": [
                    models.UniqueConstraint(
                        django.db.models.functions.text.Lower("address"),
                        name="user_email_unique_address",
                        violation_error_message="Another account already uses this email address.",
                    ),
                    models.UniqueConstraint(
                        fields=("user", "kind"),
                        name="user_email_one_per_kind",
                        violation_error_message="That account already has an address of this kind.",
                    ),
                ],
            },
        ),
        migrations.RunPython(copy_addresses_into_rows, copy_rows_back_into_columns),
        migrations.RemoveField(
            model_name="historicaluser",
            name="personal_email",
        ),
        migrations.RemoveField(
            model_name="historicaluser",
            name="work_email",
        ),
        migrations.RemoveField(
            model_name="user",
            name="personal_email",
        ),
        migrations.RemoveField(
            model_name="user",
            name="work_email",
        ),
    ]
