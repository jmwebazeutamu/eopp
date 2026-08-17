import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProgrammeDashboard } from "../api/types";
import { LanguageProvider } from "../i18n/LanguageContext";

/**
 * The dashboard's job is to be honest, so that is what is tested.
 *
 * A figure with no source entity must read as absent, never as a zero — this is
 * the screen a donor sees, and "0% retained" and "retention is not built yet"
 * are opposite claims. The scope line matters for the same reason: a
 * supervisor's totals are their woredas, and reading them as the programme's is
 * the worst available misreading.
 */

const get = vi.fn();
vi.mock("../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: DashboardPage } = await import("./DashboardPage");

function payload(overrides: Partial<ProgrammeDashboard> = {}): ProgrammeDashboard {
  return {
    period: { label: "Q3 2026", start: "2026-07-01", end: "2026-10-01" },
    scope_label: "Adama, Bishoftu",
    metrics: {
      placements_this_quarter: { available: true, value: 12, target: 40, percent: 30 },
      retained_six_months: { available: false, reason: "Retention needs the Placement record (spec §4.7, Sprint 5)." },
      gender_split: {
        available: true,
        placed_total: 12,
        female: 46,
        male: 54,
        registration_female_percent: 51,
      },
    },
    funnel: [
      { key: "registered", label: "Registered", count: 480, percent: 100, available: true, reason: "" },
      { key: "case_opened", label: "Case opened", count: 394, percent: 82, available: true, reason: "" },
      { key: "referred", label: "Referred", count: 310, percent: 65, available: true, reason: "" },
      { key: "partner_confirmed", label: "Partner confirmed", count: 245, percent: 51, available: true, reason: "" },
      { key: "completed", label: "Placed or completed", count: 128, percent: 27, available: true, reason: "" },
      {
        key: "retained",
        label: "Retained at 6 months",
        count: null,
        percent: null,
        available: false,
        reason: "Retention needs the Placement record (spec §4.7, Sprint 5).",
      },
    ],
    confirmation_lag: {
      standard_days: 14,
      partners: [
        { partner: "Adama Health Centre 03", days: 2, referrals: 8 },
        { partner: "Adama Polytechnic College", days: 19, referrals: 12 },
      ],
    },
    woredas: [
      { woreda: "Adama", registered: 300, placed: 87, rate: 29 },
      { woreda: "Bishoftu", registered: 180, placed: 41, rate: 23 },
    ],
    alerts: { open_total: 5, by_type: [{ type: "STALL", count: 5 }], stalled_cases: 5 },
    ...overrides,
  };
}

function renderDashboard(data = payload()) {
  get.mockResolvedValue({ data });
  return render(
    <LanguageProvider>
      <App>
        <DashboardPage />
      </App>
    </LanguageProvider>,
  );
}

beforeEach(() => get.mockReset());

describe("DashboardPage", () => {
  it("fetches the whole screen in one request", async () => {
    renderDashboard();
    await screen.findByText("Programme dashboard");
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/dashboard/");
  });

  it("says what the numbers cover, so a woreda total is not read as the programme's", async () => {
    renderDashboard();
    expect(await screen.findByText("Q3 2026 · Adama, Bishoftu")).toBeInTheDocument();
  });

  it("reports an unbuilt figure as absent rather than as a zero", async () => {
    renderDashboard();
    // The label appears twice: the metric card and the funnel row it belongs to.
    expect((await screen.findAllByText("Retained at 6 months")).length).toBe(2);

    expect(screen.getAllByText("Not measurable yet").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Sprint 5/).length).toBeGreaterThan(0);
    // The failure this pins: a 0 or 0% anywhere near the retention card would
    // read as a programme that retained nobody.
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("draws every funnel stage, including the one it cannot fill", async () => {
    renderDashboard();
    for (const label of ["Registered", "Case opened", "Referred", "Partner confirmed", "Placed or completed"]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("480")).toBeInTheDocument();
  });

  it("pairs every bar with its own number in text", async () => {
    renderDashboard();
    // The bar is the comparison; the number is the fact that survives a
    // monochrome screen at half brightness.
    expect(await screen.findByText("2 days")).toBeInTheDocument();
    expect(screen.getByText("19 days")).toBeInTheDocument();
    expect(screen.getByText("29%")).toBeInTheDocument();
    expect(screen.getByText("300 registered · 87 placed")).toBeInTheDocument();
  });

  it("shows the count alone when no quarterly target has been agreed", async () => {
    const data = payload();
    data.metrics.placements_this_quarter = { available: true, value: 12, target: null, percent: null };
    renderDashboard(data);

    expect(await screen.findByText("No quarterly target set")).toBeInTheDocument();
    expect(screen.queryByText(/of .* target/)).not.toBeInTheDocument();
  });

  it("states the registration baseline beside the placement split", async () => {
    renderDashboard();
    // A placement split of 46/54 only means something against what was registered.
    expect(await screen.findByText("Registration is 51% women.")).toBeInTheDocument();
  });

  it("says so plainly when there is nothing to plot yet", async () => {
    const data = payload({
      funnel: payload().funnel.map((stage) =>
        stage.available ? { ...stage, count: 0, percent: 0 } : stage,
      ),
      woredas: [],
      confirmation_lag: { standard_days: 14, partners: [] },
      alerts: { open_total: 0, by_type: [], stalled_cases: 0 },
    });
    renderDashboard(data);

    expect(await screen.findByText(/No youth registered yet/)).toBeInTheDocument();
    expect(screen.getByText("No partner has responded to a referral yet.")).toBeInTheDocument();
    expect(screen.getByText("No open alerts.")).toBeInTheDocument();
  });
});
