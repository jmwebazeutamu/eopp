import { describe, expect, it } from "vitest";

import type { Location } from "../../api/types";
import { ancestorAt, indexByCode, kebelesIn, placeOf, regionsIn, woredasIn } from "./locationCascade";

function place(code: string, name: string, level: Location["level"], parent: string | null, active = true): Location {
  return {
    code,
    name,
    level,
    level_display: level,
    parent,
    parent_name: null,
    full_path: name,
    is_active: active,
  };
}

/** Two regions, so "under this region" is a real filter rather than everything. */
const TREE: Location[] = [
  place("AM", "Amhara", "REGION", null),
  place("AM-SOU", "South Wollo", "ZONE", "AM"),
  place("AM-SOU-DES", "Dessie Zuria", "WOREDA", "AM-SOU"),
  place("AM-SOU-DES-01", "Dessie Zuria 01", "KEBELE", "AM-SOU-DES"),
  place("AM-SOU-DES-02", "Dessie Zuria 02", "KEBELE", "AM-SOU-DES"),
  place("AM-SOU-KUT", "Kutaber", "WOREDA", "AM-SOU"),
  place("AM-SOU-KUT-01", "Kutaber 01", "KEBELE", "AM-SOU-KUT"),

  place("OR", "Oromia", "REGION", null),
  place("OR-ES", "East Shewa", "ZONE", "OR"),
  place("OR-ES-ADA", "Adama", "WOREDA", "OR-ES"),
  place("OR-ES-ADA-01", "Adama 01", "KEBELE", "OR-ES-ADA"),

  place("OR-ES-OLD", "Closed Woreda", "WOREDA", "OR-ES", false),
  place("OR-ES-ADA-99", "Closed Kebele", "KEBELE", "OR-ES-ADA", false),
];

describe("ancestorAt", () => {
  it("walks up through the zone to the region", () => {
    const byCode = indexByCode(TREE);
    const kebele = byCode.get("AM-SOU-DES-01");

    expect(ancestorAt(kebele, "REGION", byCode)?.name).toBe("Amhara");
    expect(ancestorAt(kebele, "WOREDA", byCode)?.name).toBe("Dessie Zuria");
    expect(ancestorAt(kebele, "ZONE", byCode)?.name).toBe("South Wollo");
  });

  it("returns the node itself when it is already at that level", () => {
    const byCode = indexByCode(TREE);
    expect(ancestorAt(byCode.get("AM"), "REGION", byCode)?.code).toBe("AM");
  });

  it("returns null rather than looping when the chain is broken", () => {
    // A kebele whose parent is missing from the payload. Reference data is
    // seeded and could be partial; hanging the browser is not an option.
    const orphan = place("X-01", "Orphan", "KEBELE", "NOT-LOADED");
    const byCode = indexByCode([...TREE, orphan]);
    expect(ancestorAt(orphan, "REGION", byCode)).toBeNull();
  });

  it("terminates on a cycle", () => {
    const a = place("A", "A", "WOREDA", "B");
    const b = place("B", "B", "WOREDA", "A");
    const byCode = indexByCode([a, b]);
    expect(ancestorAt(a, "REGION", byCode)).toBeNull();
  });
});

describe("woredasIn", () => {
  it("finds woredas through the zone, which the picker does not show", () => {
    expect(woredasIn(TREE, "AM").map((w) => w.name)).toEqual(["Dessie Zuria", "Kutaber"]);
  });

  it("does not leak woredas from another region", () => {
    expect(woredasIn(TREE, "OR").map((w) => w.name)).toEqual(["Adama"]);
  });

  it("is empty with no region chosen", () => {
    // The control below a cleared one has nothing to offer. Listing every
    // woreda would let one be picked that contradicts the region above it.
    expect(woredasIn(TREE, "")).toEqual([]);
  });

  it("omits inactive woredas", () => {
    expect(woredasIn(TREE, "OR").map((w) => w.name)).not.toContain("Closed Woreda");
  });
});

describe("kebelesIn", () => {
  it("lists only the kebeles of that woreda", () => {
    expect(kebelesIn(TREE, "AM-SOU-DES").map((k) => k.name)).toEqual(["Dessie Zuria 01", "Dessie Zuria 02"]);
  });

  it("is empty with no woreda chosen", () => {
    expect(kebelesIn(TREE, "")).toEqual([]);
  });

  it("omits inactive kebeles", () => {
    expect(kebelesIn(TREE, "OR-ES-ADA").map((k) => k.name)).toEqual(["Adama 01"]);
  });
});

describe("regionsIn", () => {
  it("lists regions alphabetically", () => {
    expect(regionsIn(TREE).map((r) => r.name)).toEqual(["Amhara", "Oromia"]);
  });
});

describe("placeOf", () => {
  it("derives the region and woreda from a kebele", () => {
    // Deriving is the only correct way to prefill: asking a caller for all
    // three invites a set that disagrees with itself.
    expect(placeOf(TREE, "AM-SOU-DES-02")).toEqual({
      region: "AM",
      woreda: "AM-SOU-DES",
      kebele: "AM-SOU-DES-02",
    });
  });

  it("returns null for a code that is not a kebele", () => {
    expect(placeOf(TREE, "AM-SOU-DES")).toBeNull();
    expect(placeOf(TREE, "NOPE")).toBeNull();
  });
});
