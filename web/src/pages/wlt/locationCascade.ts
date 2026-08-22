import type { Location } from "../../api/types";

/**
 * Region → woreda → kebele, from the flat location list.
 *
 * The hierarchy is four levels — region, zone, woreda, kebele — and the picker
 * shows three. The zone is skipped on screen rather than dropped: a woreda is
 * matched to its region by walking up through it, and the server derives region,
 * zone and woreda from the kebele anyway. So the cascade is a way of finding a
 * kebele, never a second place where the place is recorded.
 *
 * Built from `/locations/` in one fetch. `parent` is the parent's **code**, not
 * its primary key — the serializer says so explicitly, because a client
 * cascading a hierarchy once compared `child.parent` against `parent.code` and
 * got a silent, permanent mismatch. Everything here compares codes.
 *
 * Kept apart from the modal for the reason `timelineLayout.ts` gives: this is
 * the part with rules in it, and a test that mounted a form to check a woreda
 * belongs to a region would be testing antd.
 */

/** Walk up to the ancestor at `level`, or null if the chain does not reach it. */
export function ancestorAt(
  location: Location | undefined,
  level: Location["level"],
  byCode: Map<string, Location>,
): Location | null {
  let node = location;
  // Bounded by the four levels, and by `seen` in case reference data ever
  // contains a cycle — an infinite loop here would hang the browser rather
  // than showing a bad list.
  const seen = new Set<string>();
  while (node && !seen.has(node.code)) {
    if (node.level === level) return node;
    seen.add(node.code);
    node = node.parent ? byCode.get(node.parent) : undefined;
  }
  return null;
}

export function indexByCode(locations: Location[]): Map<string, Location> {
  return new Map(locations.map((location) => [location.code, location]));
}

/** Active regions, alphabetical. */
export function regionsIn(locations: Location[]): Location[] {
  return locations
    .filter((location) => location.level === "REGION" && location.is_active)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Woredas under a region, found by walking up through the zone.
 *
 * Empty when no region is chosen — the control below a cleared one has nothing
 * to offer, and offering every woreda in the country would let a woreda be
 * picked that contradicts the region above it.
 */
export function woredasIn(locations: Location[], regionCode: string): Location[] {
  if (!regionCode) return [];
  const byCode = indexByCode(locations);
  return locations
    .filter(
      (location) =>
        location.level === "WOREDA" &&
        location.is_active &&
        ancestorAt(location, "REGION", byCode)?.code === regionCode,
    )
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Kebeles directly under a woreda. */
export function kebelesIn(locations: Location[], woredaCode: string): Location[] {
  if (!woredaCode) return [];
  return locations
    .filter((location) => location.level === "KEBELE" && location.is_active && location.parent === woredaCode)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * The region and woreda a kebele sits in.
 *
 * Used to open the cascade already filled in when a kebele is passed to the
 * form — from the group screen, say. Deriving them is the only correct way:
 * asking the caller for all three invites a set that disagrees with itself.
 */
export function placeOf(
  locations: Location[],
  kebeleCode: string,
): { region: string; woreda: string; kebele: string } | null {
  const byCode = indexByCode(locations);
  const kebele = byCode.get(kebeleCode);
  if (!kebele || kebele.level !== "KEBELE") return null;

  const woreda = ancestorAt(kebele, "WOREDA", byCode);
  const region = ancestorAt(kebele, "REGION", byCode);
  if (!woreda || !region) return null;

  return { region: region.code, woreda: woreda.code, kebele: kebele.code };
}
