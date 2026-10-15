"""Create or rebuild the nine §8 dashboards in Metabase from `dashboards.py`.

Idempotent: the EOPP collection is emptied and rebuilt, so the code is the only
place a card is defined and a hand edit in the UI does not survive a rebuild.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.reporting.dashboards import dashboards
from apps.reporting.metabase import Metabase

COLLECTION = "EOPP"
SOURCE_NAME = "EOPP reporting (read-only)"
GRID_WIDTH = 24


class Command(BaseCommand):
    help = "Build the spec §8 dashboards in Metabase."

    def handle(self, *args, **options):
        env = os.environ
        missing = [
            k
            for k in ("METABASE_URL", "METABASE_ADMIN_EMAIL", "METABASE_ADMIN_PASSWORD", "METABASE_RO_PASSWORD")
            if not env.get(k)
        ]
        if missing:
            raise CommandError("Set " + ", ".join(missing))
        mb = Metabase(env["METABASE_URL"])
        mb.wait_until_up()
        mb.sign_in(env["METABASE_ADMIN_EMAIL"], env["METABASE_ADMIN_PASSWORD"], "EOPP")

        s = connection.settings_dict
        details = {
            "host": s["HOST"],
            "port": int(s["PORT"]),
            "dbname": s["NAME"],
            "user": settings.METABASE_RO_ROLE,
            "password": env["METABASE_RO_PASSWORD"],
            "ssl": False,
            "schema-filters-type": "inclusion",
            "schema-filters-patterns": settings.BI_SCHEMA,
        }
        existing = next((d for d in mb.call("GET", "/api/database")["data"] if d["name"] == SOURCE_NAME), None)
        if existing:
            mb.call("PUT", f"/api/database/{existing['id']}", {"details": details})
            db_id = existing["id"]
        else:
            db_id = mb.call(
                "POST",
                "/api/database",
                {"engine": "postgres", "name": SOURCE_NAME, "details": details, "is_full_sync": True},
            )["id"]
        mb.call("POST", f"/api/database/{db_id}/sync_schema")

        for coll in mb.call("GET", "/api/collection"):
            if coll.get("name") == COLLECTION and not coll.get("archived"):
                mb.call("PUT", f"/api/collection/{coll['id']}", {"archived": True})
        collection_id = mb.call("POST", "/api/collection", {"name": COLLECTION})["id"]

        for spec in dashboards():
            dash = mb.call(
                "POST",
                "/api/dashboard",
                {"name": spec["name"], "description": spec["description"], "collection_id": collection_id},
            )
            placed, row = [], 0
            per_row = len(spec["cards"])
            for i, card in enumerate(spec["cards"]):
                tags = {k: {"id": k, **v} for k, v in card.get("tags", {}).items()}
                made = mb.call(
                    "POST",
                    "/api/card",
                    {
                        "name": card["name"],
                        "display": card["display"],
                        "collection_id": collection_id,
                        "dataset_query": {
                            "type": "native",
                            "database": db_id,
                            "native": {"query": card["sql"], "template-tags": tags},
                        },
                        "visualization_settings": card.get("viz", {}),
                    },
                )
                result = mb.call("POST", f"/api/card/{made['id']}/query")
                if result.get("error") or result.get("status") == "failed":
                    raise CommandError(f"{spec['name']} / {card['name']}: {result.get('error')}")
                self.stdout.write(f"    {card['name']}: {result['row_count']} row(s)")
                width = GRID_WIDTH // per_row
                placed.append(
                    {
                        "id": -(i + 1),
                        "card_id": made["id"],
                        "row": row,
                        "col": i * width,
                        "size_x": width,
                        "size_y": 8,
                        "parameter_mappings": [
                            {"parameter_id": k, "card_id": made["id"], "target": ["variable", ["template-tag", k]]}
                            for k in tags
                        ],
                    }
                )
            params = {}
            for card in spec["cards"]:
                for k, v in card.get("tags", {}).items():
                    params[k] = {
                        "id": k,
                        "name": v["display-name"],
                        "slug": k,
                        "type": "number/=" if v["type"] == "number" else "string/=",
                        **({"default": float(v["default"])} if "default" in v else {}),
                    }
            mb.call("PUT", f"/api/dashboard/{dash['id']}", {"dashcards": placed, "parameters": list(params.values())})
            self.stdout.write(f"  {spec['name']}: {len(spec['cards'])} card(s)")
        self.stdout.write(self.style.SUCCESS("Dashboards built."))
