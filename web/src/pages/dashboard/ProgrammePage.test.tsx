import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FunnelStage, MeanDays, ProgrammeTier, Rate } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";

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
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: ProgrammePage } = await import("./ProgrammePage");

/** A figure whose denominator clears the reporting floor. */
function reported(n: number, d: number, percent: number): Rate {
  return { percent, n, d, band: "report", note: "" };
}

function stage(
  key: string,
  label: string,
  count: number,
  share: Rate,
  median: number | null,
  lostFrom: FunnelStage["lost"],
): FunnelStage {
  return {
    key,
    label,
    sublabel: `${label} reached`,
    count,
    share,
    median_days_in_prev_stage: median,
    lost: lostFrom,
    unit: "youth",
    gating: true,
    available: true,
    reason: "",
  };
}

function lost(count: number, of: number, toLabel = "Referred", medianDays: number | null = 23): FunnelStage["lost"] {
  return {
    count,
    share: reported(count, of, Math.round((count * 100) / of)),
    to_stage: toLabel.toLowerCase().replace(/ /g, "_"),
    to_label: toLabel,
    // The duration belongs to the transition this loss describes, not to
    // whichever row happens to come next in the list.
    median_days: medianDays,
  };
}

function mean(days: number, n: number): MeanDays {
  return { days, n, band: "report", note: "" };
}

function payload(overrides: Partial<ProgrammeTier> = {}): ProgrammeTier {
  return {
    period: { label: "Q3 2026", start: "2026-07-01", end: "2026-10-01" },
    scope_label: "Adama, Bishoftu",
    metrics: {
      placements_this_quarter: {
        available: true,
        value: 12,
        target: 40,
        percent: 30,
        quarter_elapsed_percent: 52,
      },
      retained_six_months: { available: false, reason: "Not measurable yet: nothing records whether a youth stays in their placement." },
      gender_split: {
        available: true,
        placed_total: 128,
        female: reported(59, 128, 46),
        male: reported(69, 128, 54),
        registration_female: reported(245, 480, 51),
      },
    },
    funnel: [
      stage("registered", "Registered", 480, reported(480, 480, 100), null, lost(18, 480)),
      stage("case_opened", "Case opened", 394, reported(394, 480, 82), 13, lost(24, 394)),
      stage("referred", "Referred", 310, reported(310, 480, 65), 20, lost(41, 310)),
      stage("partner_confirmed", "Partner confirmed", 245, reported(245, 480, 51), 12, lost(69, 245)),
      stage("closed_successfully", "First referral closed successfully", 128, reported(128, 480, 27), 60, null),
      {
        key: "retained",
        label: "Retained 3 months after exit",
        sublabel: "Still in the same placement",
        count: null,
        share: null,
        median_days_in_prev_stage: null,
        lost: null,
        unit: "youth",
        gating: true,
        available: false,
        reason: "Not measurable yet: nothing records whether a youth stays in their placement.",
      },
    ],
    confirmation_lag: {
      standard_days: 14,
      partners: [
        { partner: "Adama Polytechnic College", lag: mean(19, 112) },
        { partner: "Adama Health Centre 03", lag: mean(2, 48) },
      ],
    },
    woredas: [
      { woreda: "Adama", registered: 300, placed: 87, rate: reported(87, 300, 29) },
      { woreda: "Bishoftu", registered: 180, placed: 41, rate: reported(41, 180, 23) },
    ],
    alerts: { open_total: 5, by_type: [{ type: "STALL", count: 5 }], stalled_cases: 5 },
    as_of: new Date().toISOString(),
    outcome_matrix: {
      categories: [],
      outcomes: [],
      cells: [],
      not_recorded: 0,
      permitted: [],
      crossovers_possible: false,
      other: reported(31, 190, 16),
    },
    partner_performance: { overall_rate: reported(72, 136, 53), partners: [] },
    parallel_load: { cases_with_parallel: 16, breaches_cap: 0, cases_total: 170 },
    data_completeness: [],
    cohort_retention: { available: false, reason: "Not measurable yet: placements are not recorded." },
    disposition_90_day: { available: false, reason: "Not measurable yet: placements are not recorded." },
    ...overrides,
  };
}

function renderDashboard(data = payload()) {
  get.mockResolvedValue({ data });
  return render(
    <LanguageProvider>
      <App>
        <ProgrammePage />
      </App>
    </LanguageProvider>,
  );
}

beforeEach(() => get.mockReset());

describe("ProgrammePage", () => {
  it("fetches the whole screen in one request", async () => {
    renderDashboard();
    await screen.findByText("Programme performance");
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/dashboard/programme/");
  });

  it("says what the numbers cover, so a woreda total is not read as the programme's", async () => {
    renderDashboard();
    // The subtitle now carries the as-of stamp alongside period and scope (G-8).
    expect(await screen.findByText(/Q3 2026 · Adama, Bishoftu/)).toBeInTheDocument();
  });

  it("reports an unbuilt figure as absent rather than as a zero", async () => {
    renderDashboard();
    // The label appears twice: the metric card and the funnel row it belongs to.
    // OQ-9 settled: the reportable anchor is 3 months from programme exit,
    // matching the parent operation's indicator. The "6 months" label came from
    // a mockup with no framework behind it.
    expect((await screen.findAllByText("Retained 3 months after exit")).length).toBe(2)

    expect(screen.getAllByText("Not measurable yet").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Not measurable yet/).length).toBeGreaterThan(0);
    // The failure this pins: a 0 or 0% anywhere near the retention card would
    // read as a programme that retained nobody.
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("draws every funnel stage, including the one it cannot fill", async () => {
    renderDashboard();
    for (const label of ["Registered", "Case opened", "Referred", "Partner confirmed"]) {
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
    data.metrics.placements_this_quarter = {
      available: true,
      value: 12,
      target: null,
      percent: null,
      quarter_elapsed_percent: 52,
    };
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
      funnel: payload().funnel.map((row) =>
        row.available
          ? {
              ...row,
              count: 0,
              lost: null,
              share: { percent: null, n: 0, d: 0, band: "suppressed" as const, note: "Too few to assess." },
            }
          : row,
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

  it("withholds a rate its denominator cannot support, and does not show it as zero", async () => {
    const data = payload();
    data.woredas = [
      {
        woreda: "Lume",
        registered: 6,
        placed: 0,
        rate: { percent: null, n: 0, d: 6, band: "suppressed", note: "Too few to assess." },
      },
    ];
    renderDashboard(data);

    // Six registered youth cannot carry a placement rate. "0%" here would read
    // as a woreda that placed nobody, which is a different claim entirely.
    expect(await screen.findByText("too few to assess")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    // The counts still show — they are facts; only the rate is unstable.
    expect(screen.getByText("6 registered · 0 placed")).toBeInTheDocument();
  });

  it("marks a rate below the reporting floor as provisional", async () => {
    const data = payload();
    data.woredas = [
      {
        woreda: "Lume",
        registered: 20,
        placed: 5,
        rate: {
          percent: 25,
          n: 5,
          d: 20,
          band: "provisional",
          note: "Provisional — fewer than 30 cases. Not for comparison or ranking.",
        },
      },
    ];
    renderDashboard(data);

    expect(await screen.findByText("25%")).toBeInTheDocument();
    expect(screen.getByText("*")).toBeInTheDocument();
    expect(screen.getByText(/Not for comparison or ranking/)).toBeInTheDocument();
  });

  it("does not draw a gender split off too few placements", async () => {
    const data = payload();
    data.metrics.gender_split = {
      available: true,
      placed_total: 3,
      female: { percent: null, n: 2, d: 3, band: "suppressed", note: "Too few to assess." },
      male: { percent: null, n: 1, d: 3, band: "suppressed", note: "Too few to assess." },
      registration_female: reported(245, 480, 51),
    };
    renderDashboard(data);

    // A 67/33 bar off three placements is more persuasive than any caveat
    // printed beside it, so the bar is not drawn at all.
    expect(await screen.findByText(/Only 3 placements so far/)).toBeInTheDocument();
    expect(screen.queryByText("67% women")).not.toBeInTheDocument();
  });

  it("shows how far through the quarter the target is being read against", async () => {
    renderDashboard();
    // 30% of target on day 52 of the quarter is behind; the same figure on day
    // three is not. The card cannot be read honestly without this.
    expect(await screen.findByText("52% of the quarter elapsed")).toBeInTheDocument();
  });

  it("annotates the loss at every transition, not just who survived", async () => {
    renderDashboard();
    // The prototype's whole argument against a funnel chart: the question is
    // where youth are lost, and a funnel draws the survivors.
    expect(await screen.findByText("24 lost (6%)")).toBeInTheDocument();
    expect(screen.getByText("69 lost (28%)")).toBeInTheDocument();
  });

  it("pairs each loss with the duration of its own transition", async () => {
    // 4.6. "76 lost between Case opened and Referred" was printed beside the
    // 0-day median for Case opened to Profiled, and the 22-day median the loss
    // actually spans never reached the screen.
    const data = payload();
    data.funnel[1].lost = lost(24, 394, "Referred", 22);
    renderDashboard(data);

    const row = await screen.findByText(/24 lost/);
    const text = row.parentElement?.textContent ?? "";
    expect(text).toContain("reaching Referred");
    expect(text).toContain("median 22 days in stage");
  });

  it("orders partners by how much evidence there is, not by speed", async () => {
    renderDashboard();
    await screen.findByText("19 days");
    const names = screen.getAllByText(/Adama (Polytechnic College|Health Centre 03)/).map((n) => n.textContent);
    // The slower partner leads, because 112 referrals beat 48.
    expect(names[0]).toBe("Adama Polytechnic College");
    expect(screen.getByText("from 112 confirmed referrals")).toBeInTheDocument();
  });
});

describe("ProgrammePage, against PUNCH_LIST v3 Tier 3", () => {
  it("says when a diagonal matrix is the taxonomy rather than a finding", async () => {
    // G-1. PM-3 exists to expose the onward-referral gap. If §5.3 admits one
    // outcome per category, the off-diagonal is forbidden rather than empty,
    // and the card is restating a lookup table.
    renderDashboard(payload());
    // The copy used to say every off-diagonal cell was forbidden, which
    // overstated it: "Other" applies to every category, so that column could
    // always hold one.
    expect(await screen.findByText(/only cells that can fall off the diagonal are in the Other column/)).toBeInTheDocument();
  });

  it("flags an Other share that makes the breakdown unreportable", async () => {
    // G-3. §5.3 requires a note with Other; past a share it stops being an
    // outcome and becomes a reporting failure.
    const data = payload();
    data.outcome_matrix.other = { percent: 56, n: 109, d: 195, band: "report", note: "" };
    renderDashboard(data);
    expect(await screen.findByText(/56% of completed referrals are recorded as Other/)).toBeInTheDocument();
  });

  it("does not nag when Other is a normal share", async () => {
    const data = payload();
    data.outcome_matrix.other = { percent: 8, n: 15, d: 190, band: "report", note: "" };
    renderDashboard(data);
    await screen.findByText("Programme performance");
    expect(screen.queryByText(/recorded as Other/)).not.toBeInTheDocument();
  });

  it("labels what the pipeline counts, against the partner cards", async () => {
    // G-6. PM-1 counts youth, the partner cards count referrals. Both right;
    // unlabelled they read as a contradiction.
    renderDashboard();
    expect(await screen.findByText(/Counts youth/)).toBeInTheDocument();
    expect(screen.getByText(/Counts referrals, not youth/)).toBeInTheDocument();
  });

  it("states when the figures were computed", async () => {
    // G-8.
    renderDashboard();
    expect(await screen.findByText(/As of /)).toBeInTheDocument();
  });

  it("names the pipeline's last stage for what it measures", async () => {
    // G-2. Three different numbers were labelled "placed" on one screen.
    renderDashboard();
    await screen.findByText("Programme performance");
    expect(screen.queryByText("Placed or completed")).not.toBeInTheDocument();
  });
});
