import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeReferral } from "../../test/referralFactory";
import ReferralStackTimeline from "./ReferralStackTimeline";

/**
 * Rendering tests. The arithmetic is covered in timelineLayout.test.ts; what is
 * checked here is that the component draws what the layout describes — one bar
 * per lane, a bracket instead of a colour for concurrency, labelled arrows, and
 * a legend that does not reintroduce the mockup's status/structure conflation.
 */

const TODAY = new Date(2026, 5, 30);

function renderTimeline(referrals: Parameters<typeof ReferralStackTimeline>[0]["referrals"], props = {}) {
  return render(<ReferralStackTimeline referrals={referrals} today={TODAY} width={960} {...props} />);
}

describe("ReferralStackTimeline", () => {
  it("shows an empty state rather than a blank chart", () => {
    renderTimeline([]);
    expect(screen.getByText("No referrals yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("draws one bar per referral, described by category, partner and status", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "ACTIVE", referral_category_label: "Training", partner_name: "Adama Poly" }),
      makeReferral({ id: "r2", status: "COMPLETED", referral_category_label: "Coaching", partner_name: "Bishoftu OSS" }),
    ]);

    const bars = screen.getAllByRole("button");
    expect(bars).toHaveLength(2);
    expect(bars[0]).toHaveAttribute("aria-label", expect.stringContaining("Training referral to Adama Poly"));
    expect(bars[1]).toHaveAttribute("aria-label", expect.stringContaining("Coaching referral to Bishoftu OSS"));
  });

  it("reports the referral id on click without opening anything itself", async () => {
    const onReferralClick = vi.fn();
    renderTimeline([makeReferral({ id: "r1" })], { onReferralClick });

    await userEvent.click(screen.getByRole("button"));
    expect(onReferralClick).toHaveBeenCalledExactlyOnceWith("r1");
  });

  it("is reachable by keyboard", async () => {
    const onReferralClick = vi.fn();
    renderTimeline([makeReferral({ id: "r1" })], { onReferralClick });

    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    expect(onReferralClick).toHaveBeenCalledWith("r1");
  });

  it("brackets a parallel group and gives its bars ordinary status colours", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "p1", status: "ACTIVE", parallel_group_id: "g1", initiated_date: "2026-01-05" }),
      makeReferral({
        id: "p2",
        status: "FAILED",
        parallel_group_id: "g1",
        initiated_date: "2026-01-06",
        failure_date: "2026-02-01",
      }),
    ]);

    expect(screen.getByTestId("bracket-g1")).toBeInTheDocument();
    // The failed member is red like any other failure — concurrency is not a colour.
    const active = container.querySelector('[data-testid="bar-p1"]');
    const failed = container.querySelector('[data-testid="bar-p2"]');
    expect(active).toHaveAttribute("fill", "#fa8c16");
    expect(failed).toHaveAttribute("fill", "#ff4d4f");
  });

  it("labels dependency arrows with the trigger that produced the child", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-01" }),
      makeReferral({
        id: "r2",
        status: "FAILED",
        initiated_date: "2026-02-05",
        failure_date: "2026-03-01",
        parent_referral: "r1",
        referral_trigger: "ONWARD",
      }),
      makeReferral({
        id: "r3",
        status: "ACTIVE",
        initiated_date: "2026-03-05",
        parent_referral: "r2",
        referral_trigger: "REPLACEMENT",
      }),
    ]);

    expect(screen.getByText("onward")).toBeInTheDocument();
    expect(screen.getByText("replacement")).toBeInTheDocument();
  });

  it("marks a pending referral with a dashed edge rather than a sixth colour", () => {
    const { container } = renderTimeline([makeReferral({ id: "r1", status: "PENDING_CONFIRMATION" })]);
    expect(container.querySelector('[data-testid="bar-r1"]')).toHaveAttribute("stroke-dasharray", "4 3");
  });

  it("draws Replaced in the Failed colour plus a mark, not a colour of its own", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "r1", status: "REPLACED", failure_date: "2026-02-01" }),
    ]);
    const bar = container.querySelector('[data-testid="bar-r1"]');
    expect(bar).toHaveAttribute("fill", "#ff4d4f");
    expect(screen.getAllByText("⟳").length).toBeGreaterThan(0);
  });

  it("legends five status colours plus the parallel bracket, not seven colours", () => {
    renderTimeline([makeReferral({ id: "r1" })]);

    ["Completed", "Active", "Failed", "Pending confirmation", "Cancelled", "Replaced"].forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
    expect(screen.getByText("Parallel (ran concurrently)")).toBeInTheDocument();
  });

  it("scales the axis to the data, with no hardcoded month bands", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-01-12" }),
    ]);

    // A one-week case gets day ticks in January, not "Month 1..6".
    expect(screen.getByText("6 Jan")).toBeInTheDocument();
    expect(screen.queryByText("Month 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Jun")).not.toBeInTheDocument();
  });

  it("highlights the selected referral so a selection made elsewhere is findable", () => {
    const { container } = renderTimeline([makeReferral({ id: "r1", status: "ACTIVE" })], {
      selectedReferralId: "r1",
    });
    expect(container.querySelector('[data-testid="bar-r1"]')).toHaveAttribute("stroke", "#1668dc");
  });
});
