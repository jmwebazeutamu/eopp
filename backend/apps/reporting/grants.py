"""Privileges for the Metabase role. One definition, used by the provisioning
command and by the rebuild that follows every migrate (dropping the schema
drops its grants)."""

from django.conf import settings
from django.db import connections


def reapply(using="default"):
    role, schema = settings.METABASE_RO_ROLE, settings.BI_SCHEMA
    with connections[using].cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        if cur.fetchone() is None:
            return False
        cur.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
        cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
    return True
