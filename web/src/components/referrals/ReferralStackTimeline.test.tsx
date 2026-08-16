import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeReferral } from "../../test/referralFactory";
import ReferralStackTimeline from "./ReferralStackTimeline";

/**
 * Rendering tests, written against the six faults in
 * docs/REFERRAL_TIMELINE_RENDERING_FIX_PROMPT.md: no real axis, tokens instead
 * of duration-sized bars, no open-ended marker, labels exiled to a text block,
 * invisible same-day bars, and unrendered dependency arrows.
 */

const TODAY = new Date(2026, 5, 30);
const WIDTH = 900;

function renderTimeline(referrals: Parameters<typeof ReferralStackTimeline>[0]["referrals"], props = {}) {
  return render(<ReferralStackTimeline referrals={referrals} today={TODAY} width={WIDTH} {...props} />);
}

/** Bars are <rect>s inside the group carrying the test id. */
function rect(container: HTMLElement, id: string): SVGRectElement {
  return container.querySelector(`[data-testid="bar-${id}"] rect`) as SVGRectElement;
}

function widthOf(container: HTMLElement, id: string): number {
  return Number(rect(container, id).getAttribute("width"));
}

function leftOf(container: HTMLElement, id: string): number {
  return Number(rect(container, id).getAttribute("x"));
}

describe("ReferralStackTimeline", () => {
  it("renders nothing for a case with no referrals — the panel owns that empty state", () => {
    const { container } = renderTimeline([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("draws a day-by-day axis on a week-long case", () => {
    // The reported symptom: a lone "AUG" column, so nothing could be read
    // relative to anything else.
    render(
      <ReferralStackTimeline
        referrals={[
          makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-06-10", outcome_date: "2026-06-16" }),
        ]}
        today={new Date(2026, 5, 16)}
        width={WIDTH}
      />,
    );
    ["10 Jun", "12 Jun", "14 Jun", "16 Jun"].forEach((label) =>
      expect(screen.getByText(label)).toBeInTheDocument(),
    );
  });

  it("widens the tick interval rather than crowding the axis on a longer case", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-05-05" }),
    ]);
    // Four months: monthly ticks, dated on the first so the axis is never undated.
    expect(screen.getByText("Jan 2026")).toBeInTheDocument();
    expect(screen.getByText("Apr")).toBeInTheDocument();
    expect(screen.queryByText("6 Jan")).not.toBeInTheDocument();
  });

  it("sizes each bar by its own duration", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "short", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-01-07" }),
      makeReferral({ id: "long", status: "COMPLETED", initiated_date: "2026-02-01", outcome_date: "2026-05-01" }),
    ]);
    expect(widthOf(container, "long")).toBeGreaterThan(widthOf(container, "short") * 5);
  });

  it("positions a later referral further right than an earlier one", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "first", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-01-20" }),
      makeReferral({ id: "second", status: "COMPLETED", initiated_date: "2026-04-05", outcome_date: "2026-04-20" }),
    ]);
    expect(leftOf(container, "second")).toBeGreaterThan(leftOf(container, "first"));
  });

  it("keeps a same-day referral visible and clickable", () => {
    // A real zero-width interval; without a pixel floor it would vanish.
    const onReferralClick = vi.fn();
    const { container } = renderTimeline(
      [makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-06-16", outcome_date: "2026-06-16" })],
      { onReferralClick },
    );
    expect(widthOf(container, "r1")).toBeGreaterThanOrEqual(10);
  });

  it("marks an open referral with an arrow instead of closing it off at today", () => {
    const { container } = renderTimeline([makeReferral({ id: "open", status: "ACTIVE", initiated_date: "2026-06-01" })]);
    const group = container.querySelector('[data-testid="bar-open"]')!;
    // The arrow is the only path in the bar group.
    expect(group.querySelector("path")).toBeInTheDocument();

    const { container: closed } = render(
      <ReferralStackTimeline
        referrals={[
          makeReferral({ id: "done", status: "COMPLETED", initiated_date: "2026-06-01", outcome_date: "2026-06-20" }),
        ]}
        today={TODAY}
        width={WIDTH}
      />,
    );
    expect(closed.querySelector('[data-testid="bar-done"] path')).toBeNull();
  });

  it("puts the label on the timeline, not in a separate text block", () => {
    const { container } = renderTimeline([
      makeReferral({
        id: "r1",
        status: "COMPLETED",
        referral_category_label: "Training",
        partner_name: "Adama Polytechnic",
        initiated_date: "2026-01-05",
        outcome_date: "2026-05-05",
      }),
    ]);
    // The text sits inside the bar's own group, so it moves with the bar.
    const group = container.querySelector('[data-testid="bar-r1"]')!;
    expect(within(group as HTMLElement).getByText(/Training · Adama Polytechnic/)).toBeInTheDocument();
  });

  it("shows the label beside a bar too narrow to hold it", () => {
    const { container } = renderTimeline([
      makeReferral({
        id: "r1",
        status: "COMPLETED",
        referral_category_label: "Training",
        partner_name: "Adama Polytechnic College",
        initiated_date: "2026-06-16",
        outcome_date: "2026-06-16",
      }),
    ]);
    const group = container.querySelector('[data-testid="bar-r1"]')!;
    const text = group.querySelector("text")!;
    // Outside the bar: its x starts past the bar's right edge.
    expect(Number(text.getAttribute("x"))).toBeGreaterThan(leftOf(container, "r1") + widthOf(container, "r1"));
  });

  it("never lets a label run across the bar beside it", () => {
    // The reported fault: a wide bar whose label did not fit inside was pushed
    // outside, where it drew straight over the next bar on the same row and
    // over that bar's own label.
    const { container } = renderTimeline([
      makeReferral({
        id: "wide",
        status: "COMPLETED",
        referral_category_label: "Employment / Placement",
        partner_name: "Bishoftu Automotive Plc",
        initiated_date: "2026-06-01",
        outcome_date: "2026-06-20",
      }),
      makeReferral({
        id: "next",
        status: "CANCELLED",
        referral_category_label: "Enterprise",
        partner_name: "Adama Skills Hub",
        initiated_date: "2026-06-21",
        updated_at: "2026-06-21T09:00:00+03:00",
      }),
    ]);

    const bars = ["wide", "next"].map((id) => {
      const group = container.querySelector(`[data-testid="bar-${id}"]`)!;
      const box = group.querySelector("rect")!;
      const text = group.querySelector("text");
      const left = Number(box.getAttribute("x"));
      return {
        left,
        right: left + Number(box.getAttribute("width")),
        labelStart: text ? Number(text.getAttribute("x")) : null,
        labelEnd: text ? Number(text.getAttribute("x")) + (text.textContent?.length ?? 0) * 5.9 : null,
      };
    });

    // Whatever the first bar's label does, it stops before the second bar.
    expect(bars[0].labelEnd).not.toBeNull();
    expect(bars[0].labelEnd!).toBeLessThanOrEqual(bars[1].left);
  });

  it("truncates a label to fit rather than overflowing the bar", () => {
    // A bar wide enough for some of the label but not all of it: the case that
    // used to push the whole string outside and over its neighbour.
    const { container } = renderTimeline([
      makeReferral({
        id: "r1",
        status: "COMPLETED",
        referral_category_label: "Employment / Placement",
        partner_name: "Bishoftu Automotive Plc",
        initiated_date: "2026-06-01",
        outcome_date: "2026-06-20",
      }),
      makeReferral({
        id: "later",
        status: "COMPLETED",
        initiated_date: "2026-08-01",
        outcome_date: "2026-08-10",
      }),
    ]);
    const text = container.querySelector('[data-testid="bar-r1"] text')!;
    expect(text.textContent).toMatch(/…$/);
    // The status mark leads the label, so truncation can never drop it.
    expect(text.textContent).toMatch(/^✓/);
  });

  it("thins axis labels rather than overprinting them on a narrow chart", () => {
    // Three weeks of day ticks in 560px: gridlines on every day, labels on some.
    render(
      <ReferralStackTimeline
        referrals={[
          makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-06-01", outcome_date: "2026-06-20" }),
        ]}
        today={new Date(2026, 5, 20)}
        width={300}
      />,
    );
    const labels = screen.getAllByText(/\d+ Jun/);
    expect(labels.length).toBeGreaterThan(1);
    expect(labels.length).toBeLessThan(13);
  });

  it("draws a labelled connector from a failed referral to its replacement", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "REPLACED", initiated_date: "2026-01-05", failure_date: "2026-02-01" }),
      makeReferral({
        id: "r2",
        status: "ACTIVE",
        initiated_date: "2026-02-05",
        parent_referral: "r1",
        referral_trigger: "REPLACEMENT",
      }),
    ]);
    expect(screen.getByText("replacement")).toBeInTheDocument();
  });

  it("draws a connector per hop of an onward chain", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-01" }),
      makeReferral({
        id: "r2",
        status: "COMPLETED",
        initiated_date: "2026-02-05",
        outcome_date: "2026-03-01",
        parent_referral: "r1",
        referral_trigger: "ONWARD",
      }),
      makeReferral({
        id: "r3",
        status: "ACTIVE",
        initiated_date: "2026-03-05",
        parent_referral: "r2",
        referral_trigger: "ONWARD",
      }),
    ]);
    expect(screen.getAllByText("onward")).toHaveLength(2);
  });

  it("shows the three tracks, so an unused slot reads as spare capacity", () => {
    renderTimeline([makeReferral({ id: "r1" })]);
    expect(screen.getByText("SLOT 1")).toBeInTheDocument();
    expect(screen.getByText("SLOT 2")).toBeInTheDocument();
    expect(screen.getByText("EXEMPT")).toBeInTheDocument();
    expect(screen.getAllByText("Never used")).toHaveLength(2);
  });

  it("puts an exempt referral in the Exempt track, below the slots", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "training", status: "ACTIVE", initiated_date: "2026-01-05" }),
      makeReferral({
        id: "health",
        status: "ACTIVE",
        initiated_date: "2026-01-06",
        counts_toward_parallel_cap: false,
      }),
    ]);
    const y = (id: string) => Number(rect(container, id).getAttribute("y"));
    expect(y("health")).toBeGreaterThan(y("training"));
  });

  it("stacks overlapping bars in a track instead of hiding one behind the other", () => {
    const { container } = renderTimeline([
      makeReferral({ id: "a", status: "ACTIVE", initiated_date: "2026-01-05", counts_toward_parallel_cap: false }),
      makeReferral({ id: "b", status: "ACTIVE", initiated_date: "2026-02-05", counts_toward_parallel_cap: false }),
    ]);
    expect(Number(rect(container, "a").getAttribute("y"))).not.toBe(Number(rect(container, "b").getAttribute("y")));
  });

  it("pairs every state with a mark, so colour is never doing the work alone", () => {
    renderTimeline([
      makeReferral({ id: "r1", status: "FAILED", initiated_date: "2026-01-05", failure_date: "2026-02-01" }),
    ]);
    expect(screen.getAllByText(/✕/).length).toBeGreaterThanOrEqual(2);
  });

  it("reports the referral id on click without opening anything itself", async () => {
    const onReferralClick = vi.fn();
    const { container } = renderTimeline([makeReferral({ id: "r1" })], { onReferralClick });
    await userEvent.click(container.querySelector('[data-testid="bar-r1"]')!);
    expect(onReferralClick).toHaveBeenCalledExactlyOnceWith("r1");
  });

  it("describes each bar and its dates for a screen reader", () => {
    renderTimeline([
      makeReferral({
        id: "r1",
        status: "ACTIVE",
        referral_category_label: "Training",
        partner_name: "Adama Poly",
        initiated_date: "2026-06-01",
      }),
    ]);
    expect(screen.getByLabelText(/Training · Adama Poly, active, 1 Jun 2026 – ongoing/i)).toBeInTheDocument();
  });

  it("legends all six states", () => {
    const { container } = renderTimeline([makeReferral({ id: "r1" })]);
    const legend = container.lastElementChild as HTMLElement;
    ["Pending confirmation", "Active", "Completed", "Failed", "Replaced", "Cancelled"].forEach((label) => {
      expect(within(legend).getByText(new RegExp(label))).toBeInTheDocument();
    });
  });

  it("marks the selected referral so a selection made elsewhere is findable", () => {
    const { container } = renderTimeline([makeReferral({ id: "r1" })], { selectedReferralId: "r1" });
    expect(rect(container, "r1").getAttribute("stroke")).toBe("var(--ink-900)");
  });
});
