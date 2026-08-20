import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Journey, JourneyStage, JourneyStageState } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";
import { TestAuth, testUser } from "../../test/authHarness";

/**
 * The journey screen.
 *
 * What is worth asserting here is not the layout but the two distinctions the
 * screen exists to draw: an unmet condition names its own threshold rather than
 * simply failing, and `waiting` is not `blocked`.
 */

const get = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: JourneyPage } = await import("./JourneyPage");

function stage(
  code: JourneyStage["code"],
  state: JourneyStageState,
  conditions: JourneyStage["conditions"] = [],
  detail: Record<string, unknown> = {},
): JourneyStage {
  return { code, label: code, state, conditions, detail };
}

function condition(code: string, label: string, met: boolean, actual: string, threshold: string) {
  return { code, label, met, actual, threshold, unit: "", unmeasurable: false };
}

function mount(overrides: Partial<Journey> = {}) {
  const journey: Journey = {
    person: "p1",
    profile: "b1",
    full_name: "Almaz Tesfaye",
    stages: [
      stage("REGISTERED", "done"),
      stage("VERIFIED", "done"),
      stage("GROUPED", "done"),
      stage("LINKED", "blocked"),
    ],
    stages_done: 3,
    stages_total: 4,
    next_action: null,
    ...overrides,
  };
  get.mockResolvedValue({ data: journey });
  return render(
    <TestAuth user={testUser("WLT_FACILITATOR")}>
      <LanguageProvider>
        <App>
          <MemoryRouter initialEntries={["/wlt/beneficiaries/b1"]}>
            <Routes>
              <Route path="/wlt/beneficiaries/:profileId" element={<JourneyPage />} />
            </Routes>
          </MemoryRouter>
        </App>
      </LanguageProvider>
    </TestAuth>,
  );
}

describe("JourneyPage", () => {
  beforeEach(() => get.mockReset());

  it("puts each unmet condition's actual value next to its threshold", async () => {
    // The rule it shares with the readiness card. "ELS grant received: No (need
    // Yes)" tells a facilitator what to collect; a red dot does not.
    mount({
      stages: [
        stage("REGISTERED", "done"),
        stage("VERIFIED", "done"),
        stage(
          "GROUPED",
          "blocked",
          [
            condition("els_completed", "ELS package completed", true, "Yes", "Yes"),
            condition("els_grant", "ELS grant received", false, "No", "Yes"),
          ],
          {},
        ),
        stage("LINKED", "blocked"),
      ],
    });

    expect(await screen.findByText("ELS grant received")).toBeInTheDocument();
    // The unmet row names what it needs; the met one just states its value.
    // "Yes (need Yes)" says nothing and wraps the rows that do need reading.
    expect(screen.getAllByText("(need Yes)", { exact: false })).toHaveLength(1);
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("says a pending woman is waiting on a decision, not blocked", async () => {
    // Verification is a woreda officer's judgement. A facilitator reading
    // "blocked" would go looking for something to fix that is not hers.
    mount({
      stages: [stage("REGISTERED", "done"), stage("VERIFIED", "waiting"), stage("GROUPED", "blocked")],
      next_action: stage("VERIFIED", "waiting"),
    });

    expect(await screen.findByText(/Waiting on a decision/)).toBeInTheDocument();
    expect(screen.getByText(/A woreda officer verifies her/)).toBeInTheDocument();
  });

  it("leads with the first stage that is not done", async () => {
    mount({ next_action: stage("GROUPED", "ready") });

    expect(await screen.findByText(/Next: GROUPED/)).toBeInTheDocument();
  });

  it("says so plainly when all four stages are done", async () => {
    mount({ stages_done: 4, next_action: null });

    expect(await screen.findByText(/registered, verified, in a group and linked/)).toBeInTheDocument();
  });

  it("names the phase a linkage type still needs rather than omitting it", async () => {
    // "All the gates included": a facilitator asking why the bank option is
    // absent gets the reason, not an empty list.
    mount({
      stages: [
        stage("REGISTERED", "done"),
        stage("VERIFIED", "done"),
        stage("GROUPED", "done"),
        stage("LINKED", "blocked", [], {
          group: "g1",
          group_name: "Temsalet SHG",
          available_types: [],
          blocked_types: [
            {
              code: "bank",
              label: "Savings account",
              min_phase: "P2",
              min_phase_display: "Phase 2",
              group_phase_display: "Phase 1",
            },
          ],
          service_linkages: [],
        }),
      ],
    });

    expect(await screen.findByText(/Savings account/)).toBeInTheDocument();
    expect(screen.getByText(/needs Phase 2, group is at Phase 1/)).toBeInTheDocument();
  });
});
