import { maskPhone } from "../../components/ui";
import type { BeneficiaryIdentity } from "../../api/types";
import type { StringKey } from "../../i18n/strings";

/**
 * The identity header, as data.
 *
 * Same rule as `groupTabs.ts` and `timelineLayout.ts`: which facts exist, what
 * they are called and which of them are missing is the part worth testing, and
 * a test asserting on a rendered `<dd>` would be asserting on the browser.
 *
 * The header exists because the page named a woman and then told you nothing
 * about her — no ID, no age, no phone, no place. A development agent standing
 * in a kebele could not confirm the record in front of her was the person in
 * front of her.
 */

export interface Fact {
  code: string;
  labelKey: StringKey;
  /** Rendered value, already masked and formatted, or null when nothing is recorded. */
  value: string | null;
  /** A second line under the value — the birth year, the sex code. Never load-bearing. */
  note?: string;
}

/**
 * Initials for the avatar tile.
 *
 * Split on code points rather than on `charAt`: an Amharic name's first
 * syllable is one code point but not one byte, and slicing bytes renders a
 * replacement glyph in a 76px tile that the whole card is built around.
 *
 * At most two, because three initials in a 26px face overflow the tile at the
 * phone width where it is already smaller.
 */
export function initialsFor(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((word) => Array.from(word)[0] ?? "")
    .join("")
    .toUpperCase();
}

/**
 * The five facts, in the order the design fixes them.
 *
 * **Household size is deliberately absent.** The design asks for it as the
 * fifth column; no such field exists on `Youth` or on the profile, and
 * `household_id` is the PSNP household *identifier*, not a count. Sex takes the
 * slot instead — the design's own review asks for sex to move out of the
 * compliance checklist and into identity, and unlike household size it is a
 * column that exists.
 *
 * **The phone is masked**, like every other phone in this application. The
 * registry has no reveal at all and the case screen's is per-view and never
 * persisted; a profile page is not the place to introduce a third policy.
 */
export function factsFor(identity: BeneficiaryIdentity): Fact[] {
  return [
    {
      code: "age",
      labelKey: "wlt.factAge",
      value: identity.age === null ? null : String(identity.age),
      note: identity.date_of_birth ? identity.date_of_birth.slice(0, 4) : undefined,
    },
    { code: "sex", labelKey: "wlt.factSex", value: identity.sex_display || null },
    {
      code: "phone_number",
      labelKey: "wlt.factPhone",
      value: identity.phone_number ? maskPhone(identity.phone_number) : null,
    },
    { code: "woreda", labelKey: "wlt.factWoreda", value: identity.woreda || null },
    { code: "kebele", labelKey: "wlt.factKebele", value: identity.kebele || null },
  ];
}

/** The identifier line: internal ID, PSNP client number, registration date. */
export type IdentifierCode = "national_id" | "psnp_client_id" | "registered_on";

export function identifiersFor(
  identity: BeneficiaryIdentity,
): Array<{ code: IdentifierCode; value: string | null }> {
  return [
    { code: "national_id", value: identity.national_id || null },
    { code: "psnp_client_id", value: identity.psnp_client_id || null },
    { code: "registered_on", value: identity.registered_on },
  ];
}

/**
 * How many header fields are blank.
 *
 * The count comes from the server, which owns the list — a client-side count
 * over whichever fields this screen happens to render would drift the moment
 * the header changed, and the chip would then disagree with the record.
 *
 * Zero is not a chip. "0 details missing" is a sentence nobody needs, and in
 * gold it reads as a warning about a complete record.
 */
export function missingCount(identity: BeneficiaryIdentity): number {
  return identity.missing.length;
}
