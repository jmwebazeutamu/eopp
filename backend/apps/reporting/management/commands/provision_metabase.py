"""Create the read-only Postgres role Metabase connects as, and its own database.

Spec §8: "Build these in Metabase against a read-only Postgres role." The role
reads the bi schema and nothing in `public`, where the case records live.
`--check` asserts exactly that and exits non-zero if it does not hold (dashboard
handoff README §3 step 5). Idempotent; the password is METABASE_RO_PASSWORD and
is never printed. Names come from settings (`METABASE_RO_ROLE`, `BI_SCHEMA`,
`METABASE_APP_DB`).
"""

import os

import psycopg
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

from apps.reporting import grants, views


class Command(BaseCommand):
    help = "Provision (or --check) the Metabase read-only role and application database."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Assert the role's boundary; change nothing.")

    def handle(self, *args, **options):
        if options["check"]:
            return self.assert_boundary()
        password = os.environ.get("METABASE_RO_PASSWORD")
        if not password:
            raise CommandError("Set METABASE_RO_PASSWORD (infra/.env).")
        role, app_db = settings.METABASE_RO_ROLE, settings.METABASE_APP_DB
        db = connection.settings_dict["NAME"]
        ident = sql.Identifier
        with connection.cursor() as cur:
            raw = cur.connection
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            verb = "ALTER" if cur.fetchone() else "CREATE"
            for stmt in (
                sql.SQL("{} ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.SQL(verb), ident(role), sql.Literal(password)
                ),
                sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(ident(role)),
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(ident(role)),
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(ident(db), ident(role)),
            ):
                cur.execute(stmt.as_string(raw))
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [app_db])
            has_app_db = cur.fetchone() is not None
        grants.reapply()
        if not has_app_db:
            with psycopg.connect(
                dbname=db,
                user=connection.settings_dict["USER"],
                password=connection.settings_dict["PASSWORD"],
                host=connection.settings_dict["HOST"],
                port=connection.settings_dict["PORT"],
                autocommit=True,
            ) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(ident(app_db)))
        self.stdout.write(self.style.SUCCESS(f"{role} provisioned; {app_db} ready."))

    def assert_boundary(self):
        s, role, schema = connection.settings_dict, settings.METABASE_RO_ROLE, settings.BI_SCHEMA
        failures = []
        with psycopg.connect(
            dbname=s["NAME"],
            user=role,
            password=os.environ.get("METABASE_RO_PASSWORD", ""),
            host=s["HOST"],
            port=s["PORT"],
            autocommit=True,
        ) as conn:
            for name in views.view_names():
                conn.execute(f'SELECT 1 FROM "{schema}"."{name}" LIMIT 1')
            # Every table the application owns, not a sample: a new model is
            # covered the day it is added.
            for model in apps.get_models():
                table = model._meta.db_table
                try:
                    conn.execute(f'SELECT 1 FROM public."{table}" LIMIT 1')
                    failures.append(f"CAN read public.{table}")
                except psycopg.errors.InsufficientPrivilege:
                    pass
            try:
                conn.execute(f'CREATE TABLE "{schema}".probe (a int)')
                failures.append(f"CAN create in {schema}")
            except psycopg.errors.InsufficientPrivilege:
                pass
        if failures:
            raise CommandError("; ".join(failures))
        self.stdout.write(self.style.SUCCESS(f"{role} reads {schema}.* and nothing in public."))
