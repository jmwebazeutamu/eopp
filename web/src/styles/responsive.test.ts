import { describe, expect, it } from "vitest";

/**
 * A guard for one specific bug that shipped: the referrals, cases and registry
 * screens each rendered their table *and* their phone cards at the same time on
 * a laptop, so every row appeared twice.
 *
 * The cause was that `.only-phone` carried its stacking as an inline
 * `style={{ display: "flex" }}`, and an inline declaration outranks the
 * `display: none` the media query applies. Those two classes now own their
 * `display` outright in base.css, and this asserts nobody sets one inline again.
 *
 * Source is scanned rather than rendered: vitest stubs CSS imports, so neither
 * a render test nor an assertion on the stylesheet's text can see this — the
 * media query itself is not covered here, only the thing that overrode it.
 */

const SOURCES = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

describe("responsive visibility helpers", () => {
  it("are never given an inline display, which would beat the media query", () => {
    const offenders: string[] = [];

    Object.entries(SOURCES).forEach(([path, source]) => {
      source.split("\n").forEach((line, index) => {
        if (!/className="only-(phone|laptop)"/.test(line)) return;
        if (/style=\{\{[^}]*display:/.test(line)) offenders.push(`${path}:${index + 1}`);
      });
    });

    expect(offenders).toEqual([]);
  });

  it("checks something — the glob must actually be finding the screens", () => {
    // Otherwise the assertion above passes vacuously if the paths ever move.
    const users = Object.keys(SOURCES).filter((path) => /only-phone/.test(SOURCES[path]));
    expect(users.length).toBeGreaterThanOrEqual(3);
  });
});
