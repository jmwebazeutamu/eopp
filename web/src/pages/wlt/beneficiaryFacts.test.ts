import { describe, expect, it } from "vitest";

import type { BeneficiaryIdentity } from "../../api/types";
import { factsFor, identifiersFor, initialsFor, missingCount } from "./beneficiaryFacts";

function identity(over: Partial<BeneficiaryIdentity> = {}): BeneficiaryIdentity {
  return {
    full_name: "Aster Abebe",
    sex: "FEMALE",
    sex_display: "Female",
    age: 34,
    date_of_birth: "1992-03-04",
    national_id: "AMH-DSW-01-0247",
    psnp_client_id: "03-11-0928-4",
    phone_number: "+251911452207",
    region: "Amhara",
    zone: "South Wollo",
    woreda: "Dessie Zuria",
    kebele: "Dessie White 01",
    settlement_type: "",
    settlement_type_display: "",
    registered_on: "2025-07-16",
    psnp_status: "ENROLLED",
    psnp_status_display: "Enrolled",
    enrolment_route_display: "Added by a facilitator",
    verification_status: "VERIFIED",
    verification_status_display: "Verified",
    missing: [],
    ...over,
  };
}

describe("initialsFor", () => {
  it("takes the first letter of the first two words", () => {
    expect(initialsFor("Aster Abebe")).toBe("AA");
    expect(initialsFor("Meseret Alemu Tadesse")).toBe("MA");
  });

  it("falls back to one letter for a one-word name", () => {
    expect(initialsFor("Aster")).toBe("A");
  });

  it("splits an Amharic name on code points, not on bytes", () => {
    // The tile is 76px and the glyph is 26px; a sliced byte renders as U+FFFD.
    const initials = initialsFor("አስቴር አበበ");
    expect(initials).toBe("አአ");
    expect(initials).not.toContain("�");
  });

  it("never returns an empty tile", () => {
    expect(initialsFor("   ")).toBe("?");
    expect(initialsFor("")).toBe("?");
  });
});

describe("factsFor", () => {
  it("masks the phone number", () => {
    // The registry has no reveal at all. A profile page must not be the one
    // screen in the application that prints a woman's number in full.
    const phone = factsFor(identity()).find((fact) => fact.code === "phone_number");
    expect(phone?.value).not.toBe("+251911452207");
    expect(phone?.value).toContain("•");
  });

  it("carries sex, and does not carry household size", () => {
    const codes = factsFor(identity()).map((fact) => fact.code);
    expect(codes).toEqual(["age", "sex", "phone_number", "woreda", "kebele"]);
    // Household size is in the design and in no table. It must not appear as a
    // zero, which is what an absent count renders as.
    expect(codes).not.toContain("household_size");
  });

  it("reports a missing value as null rather than as an empty string", () => {
    const facts = factsFor(identity({ phone_number: "", woreda: "", age: null, date_of_birth: null }));
    const byCode = Object.fromEntries(facts.map((fact) => [fact.code, fact.value]));
    expect(byCode.phone_number).toBeNull();
    expect(byCode.woreda).toBeNull();
    expect(byCode.age).toBeNull();
  });

  it("shows the birth year beside the age, and nothing when there is no date", () => {
    expect(factsFor(identity()).find((fact) => fact.code === "age")?.note).toBe("1992");
    expect(factsFor(identity({ date_of_birth: null })).find((fact) => fact.code === "age")?.note).toBeUndefined();
  });
});

describe("identifiersFor", () => {
  it("keeps the slot when an identifier is missing, so the line does not reorder", () => {
    const rows = identifiersFor(identity({ national_id: "" }));
    expect(rows.map((row) => row.code)).toEqual(["national_id", "psnp_client_id", "registered_on"]);
    expect(rows[0].value).toBeNull();
  });
});

describe("missingCount", () => {
  it("counts what the server says is missing, not what this screen renders", () => {
    expect(missingCount(identity({ missing: ["phone_number", "national_id"] }))).toBe(2);
  });

  it("is zero on a complete record", () => {
    expect(missingCount(identity())).toBe(0);
  });
});
