import { App } from "antd";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WltMeetingRegister } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";
import { TestAuth, testUser } from "../../test/authHarness";

/**
 * The meeting register.
 *
 * One rule here is financial rather than cosmetic: the ledger appends and has
 * no update path, so offering the savings button to a woman who has already
 * paid would double her contribution, and the correction is a reversal with a
 * reason. The screen must show what is recorded instead.
 */

const get = vi.fn();
const post = vi.fn();
vi.mock("../../api/client", () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
  },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: MeetingPage } = await import("./MeetingPage");

function register(over: Partial<WltMeetingRegister> = {}): WltMeetingRegister {
  return {
    meeting: {
      id: "m1",
      group: "g1",
      meeting_no: 4,
      scheduled_for: null,
      held_on: "2026-08-21",
      opening_cash_etb: "0",
      closing_cash_etb: null,
      counted_cash_etb: null,
      social_time_minutes: null,
      social_topic: "",
      status: "OPEN",
      closed_at: null,
      device_id: "",
      synced_at: null,
    },
    group_name: "Temsalet SHG",
    contribution_etb: "20.00",
    expected_cash_etb: "40.00",
    cash_balance_etb: "512.00",
    loans: [],
    members: [
      { person: "p1", full_name: "Chaltu Bekele", attendance: "PRESENT", saved_etb: "20.00" },
      { person: "p2", full_name: "Bontu Diriba", attendance: null, saved_etb: null },
    ],
    ...over,
  };
}

function mount(data: WltMeetingRegister = register()) {
  get.mockResolvedValue({ data });
  return render(
    <TestAuth user={testUser("WLT_FACILITATOR", {
      access: {
        case_scope: "NONE",
        case_write: false,
        referral_scope: "NONE",
        referral_write: false,
        group_scope: "OWN_GROUPS",
        group_write: true,
        delivery_write: false,
      },
    })}>
      <LanguageProvider>
        <App>
          <MemoryRouter initialEntries={["/wlt/groups/g1/meetings/m1"]}>
            <Routes>
              <Route path="/wlt/groups/:groupId/meetings/:meetingId" element={<MeetingPage />} />
            </Routes>
          </MemoryRouter>
        </App>
      </LanguageProvider>
    </TestAuth>,
  );
}

function rowFor(name: string): HTMLElement {
  const cell = screen.getAllByText(name)[0];
  const row = cell.closest("tr");
  if (!row) throw new Error(`no row for ${name}`);
  return row as HTMLElement;
}

describe("MeetingPage", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("shows what a woman has already saved rather than offering the button again", async () => {
    // The whole reason the register endpoint exists. A second press appends a
    // second entry; it does not replace the first.
    mount();
    await screen.findAllByText("Chaltu Bekele");

    const saved = screen.getAllByText("Chaltu Bekele").map((node) => node.closest("tr") as HTMLElement);
    const savingsRow = saved[saved.length - 1];
    expect(within(savingsRow).getByText(/20.00 ETB recorded/)).toBeInTheDocument();
    expect(within(savingsRow).queryByRole("button", { name: /Record 20 ETB/i })).toBeNull();
  });

  it("offers the button to a woman with nothing recorded", async () => {
    mount();
    await screen.findAllByText("Bontu Diriba");

    const rows = screen.getAllByText("Bontu Diriba").map((node) => node.closest("tr") as HTMLElement);
    const savingsRow = rows[rows.length - 1];
    expect(within(savingsRow).getByRole("button", { name: /Record 20 ETB/i })).toBeInTheDocument();
  });

  it("counts present and late together, as the attendance formula does", async () => {
    mount(
      register({
        members: [
          { person: "p1", full_name: "A", attendance: "PRESENT", saved_etb: null },
          { person: "p2", full_name: "B", attendance: "LATE", saved_etb: null },
          { person: "p3", full_name: "C", attendance: "ABSENT", saved_etb: null },
        ],
      }),
    );

    expect(await screen.findByText(/2 of 3 present/)).toBeInTheDocument();
  });

  it("shows the expected cash so the box can be counted against it", async () => {
    mount();
    expect(await screen.findByText(/40.00 ETB/)).toBeInTheDocument();
  });

  it("offers no close and no marking once the meeting is closed", async () => {
    // A closed meeting is evidence, not a form. Entries cannot be posted to it
    // server-side either — this only avoids offering what would be refused.
    mount(
      register({
        meeting: { ...register().meeting, status: "CLOSED", counted_cash_etb: "40.00", closed_at: "2026-08-21" },
      }),
    );
    await screen.findAllByText("Chaltu Bekele");

    expect(screen.queryByRole("button", { name: /Close the meeting/i })).toBeNull();
    expect(within(rowFor("Bontu Diriba")).getByRole("button", { name: /^Present$/ })).toBeDisabled();
  });

  it("says plainly when there are no loans, and why lending may not have started", async () => {
    mount();
    expect(await screen.findByText(/No loans outstanding/i)).toBeInTheDocument();
    expect(screen.getByText(/enough savings meetings/i)).toBeInTheDocument();
  });

  it("lists an outstanding loan with what is still owed", async () => {
    // Principal alone: portfolio at risk is a statement about principal, and
    // showing a combined figure here would not match the readiness card.
    mount(
      register({
        loans: [
          {
            id: "l1",
            group: "g1",
            person: "p1",
            borrower_name: "Chaltu Bekele",
            cycle_batch: null,
            principal_etb: "100.00",
            charge_basis: "FLAT_PER_LOAN",
            charge_rate: "5",
            purpose: "IGA",
            purpose_note: "",
            disbursed_on: "2026-06-01",
            due_on: "2026-09-01",
            status: "DISBURSED",
            outstanding_principal_etb: "60.00",
            written_off_on: null,
          },
        ],
      }),
    );

    const row = await screen.findByText(/Outstanding principal 60.00 ETB/i);
    expect(row).toBeInTheDocument();
    expect(screen.getByText(/Income generating activity/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record a repayment/i })).toBeInTheDocument();
  });

  it("shows what the box holds, which is the ceiling on lending", async () => {
    mount();
    expect(await screen.findByText(/512.00 ETB/)).toBeInTheDocument();
  });

  it("offers no write controls to a role the server would refuse", async () => {
    get.mockResolvedValue({ data: register() });
    render(
      <TestAuth user={testUser("WLT_WOREDA_OFFICER", {
        access: {
          case_scope: "NONE",
          case_write: false,
          referral_scope: "NONE",
          referral_write: false,
          group_scope: "OWN_GEOGRAPHY",
          group_write: false,
          delivery_write: false,
        },
      })}>
        <LanguageProvider>
          <App>
            <MemoryRouter initialEntries={["/wlt/groups/g1/meetings/m1"]}>
              <Routes>
                <Route path="/wlt/groups/:groupId/meetings/:meetingId" element={<MeetingPage />} />
              </Routes>
            </MemoryRouter>
          </App>
        </LanguageProvider>
      </TestAuth>,
    );
    await screen.findAllByText("Chaltu Bekele");

    expect(screen.queryByRole("button", { name: /Close the meeting/i })).toBeNull();
    expect(within(rowFor("Bontu Diriba")).getByRole("button", { name: /^Present$/ })).toBeDisabled();
  });
});
