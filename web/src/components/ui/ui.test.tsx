import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseStatusChip, formatMoney, maskPhone, ReferralStatusChip } from "./index";

/**
 * The design handoff's two non-negotiables, tested rather than trusted:
 * phone numbers are masked by default, and no status is signalled by colour
 * alone.
 */

describe("formatMoney", () => {
  it("groups thousands and keeps both decimal places", () => {
    expect(formatMoney("10000.00")).toBe("10,000.00");
    expect(formatMoney("1040.00")).toBe("1,040.00");
    expect(formatMoney("1234567.89")).toBe("1,234,567.89");
  });

  it("leaves a figure below a thousand alone", () => {
    expect(formatMoney("620.00")).toBe("620.00");
    expect(formatMoney("0.00")).toBe("0.00");
  });

  it("never parses to a float", () => {
    // The API sends a decimal string and it stays one. A figure with more
    // places than a double can hold must survive intact.
    expect(formatMoney("9007199254740993.01")).toBe("9,007,199,254,740,993.01");
  });

  it("returns anything that is not a decimal untouched, rather than NaN", () => {
    // A figure the server declined to compute must not render as a word.
    expect(formatMoney("")).toBe("");
    expect(formatMoney("\u2014")).toBe("\u2014");
  });

  it("keeps the sign outside the grouping", () => {
    expect(formatMoney("-1500.50")).toBe("-1,500.50");
  });
});

describe("maskPhone", () => {
  it("keeps the country code and the last four digits, hides the middle", () => {
    // The brief's shape: enough to confirm the right person, not enough for
    // whoever is standing behind you in a shared office.
    expect(maskPhone("+251 911 45 22 07")).toBe("+251 9•• •• 22 07");
  });

  it("masks a number written without spaces the same way", () => {
    expect(maskPhone("+251911452207")).toBe("+251 9•• •• 22 07");
  });

  it("never returns the input unchanged", () => {
    const phone = "+251 912 08 71 33";
    expect(maskPhone(phone)).not.toBe(phone);
    expect(maskPhone(phone)).toContain("•");
  });

  it("refuses to guess at something too short to be a phone number", () => {
    expect(maskPhone("123")).toBe("•• •• •• ••");
  });
});

describe("status chips", () => {
  it("pairs a case status with a mark, not only a colour", () => {
    render(<CaseStatusChip status="STALLED" label="Stalled" />);
    expect(screen.getByText("Stalled")).toBeInTheDocument();
    expect(screen.getByText("▲")).toBeInTheDocument();
  });

  it("gives every referral status its own mark", () => {
    const marks = new Set<string>();
    (["PENDING_CONFIRMATION", "ACTIVE", "COMPLETED", "FAILED", "REPLACED", "CANCELLED"] as const).forEach((status) => {
      const { container, unmount } = render(<ReferralStatusChip status={status} label={status} />);
      const mark = container.querySelector(".chip__mark")!.textContent!;
      // A shared mark would defeat the point on a monochrome screen.
      expect(marks.has(mark)).toBe(false);
      marks.add(mark);
      unmount();
    });
    expect(marks.size).toBe(6);
  });
});
