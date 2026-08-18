import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TestAuth } from "../../test/authHarness";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MyWork } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";

/**
 * Tier 1, against `PUNCH_LIST_v1.md`.
 *
 * The items here are the ones the review caught by reading the screen rather
 * than the code: a tile whose subtitle contradicted its own number, a missing
 * tile, plain text where a threshold badge belongs, and lists with no way to
 * reach the rest of the rows.
 */

const get = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: MyWorkPage } = await import("./MyWorkPage");

function payload(overrides: Partial<MyWork> = {}): MyWork {
  return {
    needs_action: [
      { id: "a1", case: "c1", youth_name: "Chaltu Bekele", reason: "Case stalled", days_overdue: 19 },
    ],
    needs_action_count: 101,
    awaiting_partner: [
      { id: "r1", case: "c1", youth_name: "Firaol Tadesse", partner: "Bishoftu TVET", days_waiting: 16 },
      { id: "r2", case: "c2", youth_name: "Ebisa Fikadu", partner: "Adama Polytechnic", days_waiting: 2 },
    ],
    awaiting_partner_count: 7,
    awaiting_over_threshold: 5,
    open_alerts_in_scope: 101,
    confirmation_threshold: 7,
    active: { referrals: 79, youth: 62 },
    at_risk: [{ case: "c3", youth_name: "Tolosa Nagawo", reason: "No activity for 45 days", badge: "45d" }],
    at_risk_count: 14,
    uninstrumented_risk: ["3 consecutive training absences — training attendance is not recorded yet"],
    caseload_by_status: [
      { status: "ACTIVE", label: "Active", n: 71, oldest_days: 0, slug: "active" },
      { status: "STALLED", label: "Stalled", n: 14, oldest_days: 62, slug: "stalled" },
    ],
    week: { opened: 6, closed: 3 },
    outcomes_verified: { verified: 14, recorded: 21 },
    woredas: ["Adama", "Bishoftu"],
    generated_at: new Date().toISOString(),
    ...overrides,
  };
}

function renderPage(data = payload()) {
  get.mockResolvedValue({ data });
  return render(
    <MemoryRouter>
      <TestAuth>
      <LanguageProvider>
        <App>
          <MyWorkPage />
        </App>
      </LanguageProvider>
    </TestAuth>
    </MemoryRouter>,
  );
}

beforeEach(() => get.mockReset());

describe("MyWorkPage", () => {
  it("does not print an empty-state caption above a non-zero count", async () => {
    // P2-1: the tile read "No referral is waiting on a partner" above 117.
    renderPage();
    expect(await screen.findByText("5 older than 7 days")).toBeInTheDocument();
    expect(screen.queryByText("No referral is waiting on a partner")).not.toBeInTheDocument();
  });

  it("reads the threshold from the server rather than hardcoding seven", async () => {
    renderPage(payload({ confirmation_threshold: 14, awaiting_over_threshold: 2 }));
    expect(await screen.findByText("2 older than 14 days")).toBeInTheDocument();
    expect(screen.getByText(/overdue after 14 days/)).toBeInTheDocument();
  });

  it("carries the active-referrals tile the spec asks for", async () => {
    // P2-2: the built row had four tiles where the spec has five.
    renderPage();
    expect(await screen.findByText("Active referrals")).toBeInTheDocument();
    expect(screen.getByText("79")).toBeInTheDocument();
    expect(screen.getByText("across 62 youth")).toBeInTheDocument();
  });

  it("badges each wait against the threshold rather than printing plain days", async () => {
    // P2-3: colour paired with the day count and a mark, never colour alone.
    renderPage();
    expect(await screen.findByText("16d")).toBeInTheDocument();
    expect(screen.getByText("2d")).toBeInTheDocument();
    expect(screen.getAllByText("▲").length).toBeGreaterThan(0);
  });

  it("states the threshold as a footnote", async () => {
    // P2-4.
    renderPage();
    expect(await screen.findByText(/Threshold: partner confirmation overdue after 7 days/)).toBeInTheDocument();
  });

  it("links onward from every list that has more rows than it shows", async () => {
    // P2-6: the counts are separate from the rows, so the page does not grow
    // with the caseload.
    renderPage();
    expect(await screen.findByText("View all 101 →")).toBeInTheDocument();
    expect(screen.getByText("View all 7 →")).toBeInTheDocument();
    expect(screen.getByText("View all 14 →")).toBeInTheDocument();
  });

  it("states its own age and the woredas it covers", async () => {
    // P2-7 and P2-8: the header read "Woreda: —" and had no freshness stamp.
    renderPage();
    expect(await screen.findByText(/Adama, Bishoftu/)).toBeInTheDocument();
    expect(screen.getByText(/Live · refreshed/)).toBeInTheDocument();
  });

  it("says nothing is assigned to you, rather than nothing is overdue", async () => {
    // What the review actually saw: a supervisor with 540 cases in view and an
    // empty work queue, told "Nothing is overdue". That is a claim about the
    // programme; the true one is narrower.
    renderPage(payload({ needs_action: [], needs_action_count: 0, open_alerts_in_scope: 418 }));
    expect(await screen.findByText(/No alerts are assigned to you. 418 are open/)).toBeInTheDocument();
    expect(screen.queryByText("Nothing is overdue.")).not.toBeInTheDocument();
  });

  it("says nothing is overdue only when nothing actually is", async () => {
    renderPage(payload({ needs_action: [], needs_action_count: 0, open_alerts_in_scope: 0 }));
    expect(await screen.findByText("Nothing is overdue.")).toBeInTheDocument();
  });

  it("does not present recorded outcomes as verified ones", async () => {
    // 3.2. The tile counted every recorded outcome under a "verified" label —
    // 50 where only 34 had anyone but the youth behind them.
    renderPage();
    // The subtext is what makes the tile honest: 14 is a subset of 21, and the
    // tile used to show the 21 under a "verified" label.
    const subtext = await screen.findByText("of 21 recorded, this month");
    expect(subtext).toBeInTheDocument();
    expect(subtext.closest("div")?.parentElement?.textContent).toContain("14");
  });

  it("keeps the caseload table in workflow order", async () => {
    // P2-9 was a positive finding; this stops it being "fixed" into size order.
    renderPage();
    await screen.findByText("Active");
    const rows = screen.getAllByRole("row").map((row) => row.textContent ?? "");
    const active = rows.findIndex((text) => text.includes("Active"));
    const stalled = rows.findIndex((text) => text.includes("Stalled"));
    expect(active).toBeLessThan(stalled);
  });

  it("still names the risk conditions it cannot check", async () => {
    // The review called this out as the pattern to keep.
    renderPage();
    expect(await screen.findByText(/training attendance is not recorded yet/)).toBeInTheDocument();
  });
});
