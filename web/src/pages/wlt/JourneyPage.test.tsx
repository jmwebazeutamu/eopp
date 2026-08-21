import { App } from "antd";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args), post: (...args: unknown[]) => post(...args) },
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

function mount(overrides: Partial<Journey> = {}, role: "WLT_FACILITATOR" | "WLT_WOREDA_OFFICER" | "SYSTEM_ADMIN" = "WLT_FACILITATOR") {
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
    <TestAuth user={testUser(role)}>
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
  beforeEach(() => { get.mockReset(); post.mockReset(); post.mockResolvedValue({ data: {} }); });

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

    expect((await screen.findAllByText(/Waiting on a decision/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/A woreda officer verifies her/)).toBeInTheDocument();
  });

  it("leads with the first stage that is not done", async () => {
    mount({ next_action: stage("GROUPED", "ready") });

    expect(await screen.findByText(/Next: GROUPED/)).toBeInTheDocument();
  });

  it("shows the entire ordered sequence with completed stages ticked", async () => {
    mount({ next_action: stage("GROUPED", "ready") });

    const sequence = await screen.findByRole("list", { name: "Complete programme sequence" });
    expect(sequence).toHaveTextContent("REGISTERED");
    expect(sequence).toHaveTextContent("VERIFIED");
    expect(sequence).toHaveTextContent("GROUPED");
    expect(sequence).toHaveTextContent("LINKED");
    expect(sequence).toHaveTextContent("✓");
  });

  it("lets an authorised officer verify a pending registration", async () => {
    mount({
      stages: [stage("REGISTERED", "done"), stage("VERIFIED", "waiting"), stage("GROUPED", "blocked")],
      next_action: stage("VERIFIED", "waiting"),
    }, "WLT_WOREDA_OFFICER");

    fireEvent.click(await screen.findByRole("button", { name: "Verify registration" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm verification" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/wlt/profiles/b1/verify/", { approved: true, reason: "" }));
  });

  it("says so plainly when all four stages are done", async () => {
    mount({ stages_done: 4, next_action: null });

    expect(await screen.findByText(/registered, verified, in a group and linked/)).toBeInTheDocument();
  });

  it("names her group and how it is doing, not just its name", async () => {
    // The register lands here. A bare group name sent a facilitator to a second
    // screen to find out whether that group was even operating.
    mount({
      stages: [
        stage("REGISTERED", "done"),
        stage("VERIFIED", "done"),
        stage("GROUPED", "done", [], {
          group: "g1",
          group_name: "Temsalet SHG",
          group_status: "ACTIVE",
          group_status_display: "Active",
          group_phase_display: "Phase 2",
          kebele_name: "Dessie Zuria 01",
          facilitator_name: "Almaz Fikru",
          members_current: 20,
          joined_on: "2025-12-20",
        }),
      ],
    });

    expect(await screen.findByText("Temsalet SHG")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Dessie Zuria 01")).toBeInTheDocument();
    expect(screen.getByText("Phase 2")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("says plainly when she is in no group rather than rendering an empty card", async () => {
    mount({ stages: [stage("REGISTERED", "done"), stage("GROUPED", "ready", [], {})] });

    expect(await screen.findByText(/not in a savings group yet/i)).toBeInTheDocument();
  });

  it("shows a blocked linkage with its status rather than hiding it", async () => {
    // The reported gap: only ACTIVE and APPROVED reached the profile, so a
    // group whose bank linkage sat blocked looked like a group with none.
    mount({
      stages: [
        stage("GROUPED", "done", [], { group: "g1", group_name: "Temsalet SHG", group_status: "ACTIVE" }),
        stage("LINKED", "blocked", [], {
          group: "g1",
          service_linkages: [
            {
              id: "l1",
              type_label: "Savings account",
              status: "BLOCKED",
              status_display: "Blocked",
              provider_name: "Amhara Rural Bank",
              opened_on: "2026-03-01",
              activated_on: null,
              is_live: false,
              is_settled: false,
            },
          ],
        }),
      ],
    });

    // Scoped to the row: "Blocked" is also the stage's own state chip, and an
    // unscoped query cannot tell the two apart — which is the same collision
    // that made the journey screen read as a contradiction in the first place.
    const label = await screen.findByText("Savings account");
    const row = label.closest("li");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Blocked")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText(/Amhara Rural Bank/)).toBeInTheDocument();
  });

  it("leads with the live linkage and puts settled history last", async () => {
    // Ordered by what needs doing, not by date — sorting by date would bury a
    // blocked linkage under a closed one.
    mount({
      stages: [
        stage("GROUPED", "done", [], { group: "g1", group_name: "Temsalet SHG", group_status: "ACTIVE" }),
        stage("LINKED", "done", [], {
          group: "g1",
          service_linkages: [
            {
              id: "closed",
              type_label: "Old account",
              status: "CLOSED",
              status_display: "Closed",
              provider_name: null,
              opened_on: "2025-01-01",
              activated_on: null,
              is_live: false,
              is_settled: true,
            },
            {
              id: "live",
              type_label: "Savings account",
              status: "ACTIVE",
              status_display: "Active",
              provider_name: null,
              opened_on: "2026-01-01",
              activated_on: "2026-02-01",
              is_live: true,
              is_settled: false,
            },
          ],
        }),
      ],
    });

    const items = await screen.findAllByRole("listitem");
    const labels = items.map((item) => item.textContent ?? "");
    const live = labels.findIndex((text) => text.includes("Savings account"));
    const closed = labels.findIndex((text) => text.includes("Old account"));
    expect(live).toBeLessThan(closed);
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
