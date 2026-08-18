import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WoredaDashboard } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";

/**
 * Tier 2, against `PUNCH_LIST_v1.md` v2 section 4.
 *
 * W-1 is the one that mattered: the build spent two of its four segments on
 * terminal states and none on the one live state a supervisor can act on —
 * which was also the segment that would have surfaced the stranded-referral
 * cohort in P1-3.
 */

const get = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: WoredaPage } = await import("./WoredaPage");

function payload(overrides: Partial<WoredaDashboard> = {}): WoredaDashboard {
  return {
    scope_label: "Adama",
    as_of: new Date().toISOString(),
    confirmation_threshold: 7,
    awaiting_partner_alerts: 113,
    tiles: {
      open_cases: 194,
      registered_without_case: 74,
      overdue_actions: 418,
      median_days_to_confirm: 9,
      outcomes_verified: 14,
      over_ceiling: 4,
      caseload_ceiling: 120,
    },
    team_caseload: [
      {
        case_manager: "u1",
        name: "Case Manager One",
        total: 141,
        segments: { on_track: 100, awaiting_partner: 30, stalled: 8, closed: 3 },
        overdue: 119,
        over_ceiling: true,
      },
      {
        case_manager: "u2",
        name: "Case Manager Two",
        total: 90,
        segments: { on_track: 80, awaiting_partner: 6, stalled: 3, closed: 1 },
        overdue: 12,
        over_ceiling: false,
      },
    ],
    segments: [
      { key: "on_track", label: "On track" },
      { key: "awaiting_partner", label: "Awaiting partner" },
      { key: "stalled", label: "Stalled" },
      { key: "closed", label: "Placed or exited" },
    ],
    unassigned_youth: { available: false, reason: "Not measurable yet: every case must have a case manager." },
    registered_without_case: 74,
    partner_response: [
      { partner: "Slow Institute", median_days: 10, n: 92, staff_recorded: 4, band: "report" },
      { partner: "Quick College", median_days: 8, n: 109, staff_recorded: 0, band: "report" },
      { partner: "Thin Evidence", median_days: null, n: 4, staff_recorded: 31, band: "suppressed" },
    ],
    data_completeness: [
      { field: "Phone number", missing: 12, of: 614, has_records: true, cost: "Follow-up calls cannot be made." },
      { field: "Failure reason", missing: 0, of: 0, has_records: false, cost: "Breaks the replacement prompt." },
    ],
    ...overrides,
  };
}

function renderPage(data = payload()) {
  get.mockResolvedValue({ data });
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <App>
          <WoredaPage />
        </App>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => get.mockReset());

describe("WoredaPage", () => {
  it("gives a segment to the one live state a supervisor can act on", async () => {
    // W-1: "Awaiting partner" had been folded into "in progress", and two of
    // the four segments were spent on terminal states.
    renderPage();
    expect(await screen.findAllByText("Awaiting partner")).not.toHaveLength(0);
    expect(screen.queryByText("In progress")).not.toBeInTheDocument();
  });

  it("puts a count outside any segment too narrow to hold one", async () => {
    // W-3: gold and grey both fall below 3:1 against the surface and cannot
    // carry meaning by fill alone, so a dropped label loses the segment.
    renderPage();
    // closed = 3 of 141 is ~2% — far too narrow for an inside label.
    expect(await screen.findByText(/Placed or exited 3/)).toBeInTheDocument();
  });

  it("flags a case manager over the caseload ceiling", async () => {
    // The ceiling parameter was configured and nothing read it.
    renderPage();
    expect(await screen.findByText("over ceiling")).toBeInTheDocument();
  });

  it("sorts partners slowest first, with withheld medians last", async () => {
    // W-9: the table was unsorted, so the partner to chase was not findable.
    renderPage();
    await screen.findByText("Slow Institute");
    const names = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    const slow = names.findIndex((t) => t.includes("Slow Institute"));
    const quick = names.findIndex((t) => t.includes("Quick College"));
    const thin = names.findIndex((t) => t.includes("Thin Evidence"));
    expect(slow).toBeLessThan(quick);
    expect(quick).toBeLessThan(thin);
  });

  it("keeps staff-recorded confirmations out of the responsiveness median", async () => {
    // A case manager may confirm on a partner's behalf (decided 2026-08-18).
    // Averaged together, a partner who never replies would score like one who
    // replies the same day.
    renderPage();
    expect(await screen.findByText("31 recorded by staff")).toBeInTheDocument();
    expect(screen.getByText(/Medians cover confirmations the partner entered themselves/)).toBeInTheDocument();
  });

  it("distinguishes no records from complete", async () => {
    // W-10: "Complete" over a zero denominator is absence of records dressed
    // up as a clean bill of health.
    renderPage();
    expect(await screen.findByText("No records to check")).toBeInTheDocument();
    expect(screen.queryByText("Complete")).not.toBeInTheDocument();
  });

  it("carries the five stat tiles and an as-of stamp", async () => {
    // W-5 and W-11.
    renderPage();
    expect(await screen.findByText("Open cases")).toBeInTheDocument();
    expect(screen.getByText("Overdue actions")).toBeInTheDocument();
    expect(screen.getByText("Median days to confirm")).toBeInTheDocument();
    expect(screen.getByText(/As of /)).toBeInTheDocument();
  });

  it("shows an em dash rather than a zero for a withheld median", async () => {
    const data = payload();
    data.tiles.median_days_to_confirm = null;
    renderPage(data);
    await screen.findByText("Median days to confirm");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
