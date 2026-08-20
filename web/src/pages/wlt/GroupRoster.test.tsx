import { App } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WltGroup, WltGroupMembership } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";
import { TestAuth, testUser } from "../../test/authHarness";

/**
 * The roster panel.
 *
 * Two things here are behaviour rather than layout, and both would be silent
 * failures: a woman who has left must stay on the screen with her reason, and
 * the write controls must not be offered to a role the server will refuse.
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

const { default: GroupRoster } = await import("./GroupRoster");

const GROUP = {
  id: "g1",
  name: "Temsalet SHG",
  kebele: "k1",
  kebele_name: "Dembela",
  facilitator: "f1",
  facilitator_name: "Facilitator",
  status: "ACTIVE",
  status_display: "Active",
  current_phase: "P1",
  phase_display: "Phase 1",
  drafted_on: "2025-12-15",
  constituted_on: "2026-01-02",
  activated_on: "2026-01-05",
  phase_entered_on: "2026-01-05",
  members_current: 2,
} as WltGroup;

function membership(overrides: Partial<WltGroupMembership> = {}): WltGroupMembership {
  return {
    id: "m1",
    group: "g1",
    person: "p1",
    full_name: "Chaltu Bekele",
    joined_on: "2025-12-20",
    exited_on: null,
    exit_reason: "",
    exit_reason_display: "",
    exit_note: "",
    ...overrides,
  };
}

function mount(roster: WltGroupMembership[], { canWrite = true }: { canWrite?: boolean } = {}) {
  get.mockResolvedValue({ data: roster });
  const user = testUser("WLT_FACILITATOR", {
    access: {
      case_scope: "NONE",
      case_write: false,
      referral_scope: "NONE",
      referral_write: false,
      group_scope: "OWN_GROUPS",
      group_write: canWrite,
      delivery_write: false,
    },
  });
  return render(
    <TestAuth user={user}>
      <LanguageProvider>
        <App>
          <GroupRoster group={GROUP} onChanged={() => {}} />
        </App>
      </LanguageProvider>
    </TestAuth>,
  );
}

describe("GroupRoster", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("names every current member, which the member count never did", async () => {
    mount([membership(), membership({ id: "m2", person: "p2", full_name: "Bontu Diriba" })]);

    expect(await screen.findByText("Chaltu Bekele")).toBeInTheDocument();
    expect(screen.getByText("Bontu Diriba")).toBeInTheDocument();
    expect(screen.getByText(/2 on the roster today/)).toBeInTheDocument();
  });

  it("keeps a woman who has left, with the date and the reason", async () => {
    // A membership is a dated range. Dropping her would change February's
    // attendance when she leaves in April, because the denominator is the
    // roster as it stood at each meeting.
    mount([
      membership(),
      membership({
        id: "m2",
        person: "p2",
        full_name: "Bontu Diriba",
        exited_on: "2026-04-01",
        exit_reason: "MOVED",
        exit_reason_display: "Moved away",
      }),
    ]);

    expect(await screen.findByText(/Former members/i)).toBeInTheDocument();
    expect(screen.getByText(/Bontu Diriba/)).toBeInTheDocument();
    expect(screen.getByText(/Moved away/)).toBeInTheDocument();
    // She is not counted among the women who are here now.
    expect(screen.getByText(/1 on the roster today/)).toBeInTheDocument();
  });

  it("offers no write control to a role the server would refuse", async () => {
    // The button gate is not the security boundary — `CanAccessGroups` refuses
    // the write regardless. It is here so a region officer is not shown a
    // control that 403s.
    mount([membership()], { canWrite: false });

    expect(await screen.findByText("Chaltu Bekele")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add a member/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Record that she left/i })).not.toBeInTheDocument();
  });

  it("offers both write controls to a facilitator", async () => {
    mount([membership()]);

    expect(await screen.findByRole("button", { name: /Add a member/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record that she left/i })).toBeInTheDocument();
  });

  it("refuses to record an exit with no reason", async () => {
    // The check constraint can only say "not blank". "Moved away" and
    // "expelled" are opposite programme outcomes, so the form asks.
    mount([membership()]);
    const person = userEvent.setup();

    await person.click(await screen.findByRole("button", { name: /Record that she left/i }));
    await person.click(await screen.findByRole("button", { name: /Record the exit/i }));

    await waitFor(() => expect(screen.getByText(/Choose why she is leaving/)).toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });

  it("says the exit keeps her history rather than deleting her", async () => {
    mount([membership()]);
    const person = userEvent.setup();

    await person.click(await screen.findByRole("button", { name: /Record that she left/i }));

    expect(await screen.findByText(/stays on the record with the date she left/i)).toBeInTheDocument();
  });
});
