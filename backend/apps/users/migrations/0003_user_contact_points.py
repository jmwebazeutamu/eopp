"""Four contact points on a user: work and personal, email and phone.

`email` becomes `work_email` by **rename**, not by drop-and-add.

`makemigrations` generated a RemoveField plus an AddField, which is the same
schema and a different outcome: every address on file would be discarded, and
so would the column on 95 historical rows. Django cannot tell a rename from a
coincidence, so it has to be written by hand. This database happens to hold no
addresses today; a deployed one is not required to be so lucky.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("users", "0002_historicaluser_partner_user_partner")]

    operations = [
        migrations.RenameField(model_name="user", old_name="email", new_name="work_email"),
        migrations.RenameField(model_name="historicaluser", old_name="email", new_name="work_email"),
        migrations.AlterField(
            model_name="user",
            name="work_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="work email"),
        ),
        migrations.AlterField(
            model_name="historicaluser",
            name="work_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="work email"),
        ),
        migrations.AddField(
            model_name="user",
            name="personal_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="personal email"),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="personal_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="personal email"),
        ),
        migrations.AddField(
            model_name="user",
            name="work_phone",
            field=models.CharField(blank=True, max_length=32, verbose_name="work phone"),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="work_phone",
            field=models.CharField(blank=True, max_length=32, verbose_name="work phone"),
        ),
        migrations.AddField(
            model_name="user",
            name="personal_phone",
            field=models.CharField(blank=True, max_length=32, verbose_name="personal phone"),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="personal_phone",
            field=models.CharField(blank=True, max_length=32, verbose_name="personal phone"),
        ),
    ]
