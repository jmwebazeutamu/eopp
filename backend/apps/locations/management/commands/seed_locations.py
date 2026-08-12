"""Seed the Ethiopian administrative hierarchy.

Regions are the full national list. Zones and woredas below them cover the
areas the pilot is expected to touch, plus enough of the surrounding hierarchy
to be realistic for demos and testing.

TODO(open-question): the actual pilot woredas are a programme decision (spec §10
targets 2-3 woredas). Confirm them and extend the WOREDAS table below — nothing
here should be treated as the agreed pilot geography.

    python manage.py seed_locations
    python manage.py seed_locations --prune   # deactivate rows not in this file
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.locations.models import Location, LocationLevel

REGIONS = [
    ("ET-AA", "Addis Ababa"),
    ("ET-AF", "Afar"),
    ("ET-AM", "Amhara"),
    ("ET-BG", "Benishangul-Gumuz"),
    ("ET-CE", "Central Ethiopia"),
    ("ET-DD", "Dire Dawa"),
    ("ET-GA", "Gambela"),
    ("ET-HA", "Harari"),
    ("ET-OR", "Oromia"),
    ("ET-SI", "Sidama"),
    ("ET-SO", "Somali"),
    ("ET-SE", "South Ethiopia"),
    ("ET-SW", "South West Ethiopia"),
    ("ET-TI", "Tigray"),
]

# (zone_code, zone_name, parent_region_code)
ZONES = [
    ("ET-OR-ES", "East Shewa", "ET-OR"),
    ("ET-OR-WS", "West Shewa", "ET-OR"),
    ("ET-OR-AR", "Arsi", "ET-OR"),
    ("ET-AM-NS", "North Shewa", "ET-AM"),
    ("ET-AM-SG", "South Gondar", "ET-AM"),
    ("ET-SI-SD", "Sidama", "ET-SI"),
    ("ET-TI-SE", "South Eastern Tigray", "ET-TI"),
    ("ET-AA-Z1", "Addis Ababa", "ET-AA"),
]

# (woreda_code, woreda_name, parent_zone_code)
WOREDAS = [
    ("ET-OR-ES-ADAMA", "Adama", "ET-OR-ES"),
    ("ET-OR-ES-BISHOFTU", "Bishoftu", "ET-OR-ES"),
    ("ET-OR-ES-LUME", "Lume", "ET-OR-ES"),
    ("ET-OR-ES-ADEA", "Ada'a", "ET-OR-ES"),
    ("ET-OR-WS-AMBO", "Ambo", "ET-OR-WS"),
    ("ET-OR-AR-ASELLA", "Asella", "ET-OR-AR"),
    ("ET-AM-NS-DEBREBERHAN", "Debre Berhan", "ET-AM-NS"),
    ("ET-AM-SG-DEBRETABOR", "Debre Tabor", "ET-AM-SG"),
    ("ET-SI-SD-HAWASSA", "Hawassa", "ET-SI-SD"),
    ("ET-TI-SE-MEKELLE", "Mekelle", "ET-TI-SE"),
    ("ET-AA-Z1-BOLE", "Bole", "ET-AA-Z1"),
    ("ET-AA-Z1-KIRKOS", "Kirkos", "ET-AA-Z1"),
]

# (kebele_code, kebele_name, parent_woreda_code) — illustrative, for the two
# woredas most likely to be used in demos.
KEBELES = [
    ("ET-OR-ES-ADAMA-01", "Adama 01", "ET-OR-ES-ADAMA"),
    ("ET-OR-ES-ADAMA-02", "Adama 02", "ET-OR-ES-ADAMA"),
    ("ET-OR-ES-ADAMA-03", "Adama 03", "ET-OR-ES-ADAMA"),
    ("ET-OR-ES-BISHOFTU-01", "Bishoftu 01", "ET-OR-ES-BISHOFTU"),
    ("ET-OR-ES-BISHOFTU-02", "Bishoftu 02", "ET-OR-ES-BISHOFTU"),
]


class Command(BaseCommand):
    help = "Seed or refresh the Ethiopian location hierarchy. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Deactivate locations that are not in this file (never deletes — records reference them).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created_total = 0
        seen_codes = set()

        for level, rows in (
            (LocationLevel.REGION, [(c, n, None) for c, n in REGIONS]),
            (LocationLevel.ZONE, ZONES),
            (LocationLevel.WOREDA, WOREDAS),
            (LocationLevel.KEBELE, KEBELES),
        ):
            for code, name, parent_code in rows:
                parent = Location.objects.get(code=parent_code) if parent_code else None
                _, created = Location.objects.update_or_create(
                    code=code,
                    defaults={"name": name, "level": level, "parent": parent, "is_active": True},
                )
                seen_codes.add(code)
                created_total += int(created)
            self.stdout.write(f"  {level.label}: {len(rows)} rows")

        if options["prune"]:
            pruned = Location.objects.exclude(code__in=seen_codes).update(is_active=False)
            self.stdout.write(self.style.WARNING(f"Deactivated {pruned} location(s) not in the seed file."))

        total = Location.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Locations seeded: {created_total} new, {total} total."))
