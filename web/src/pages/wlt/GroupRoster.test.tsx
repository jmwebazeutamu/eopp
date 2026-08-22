import { App } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
  formErrors: () => [],
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
    profile: "b1",
    full_name: "Chaltu Bekele",
    joined_on: "2025-12-20",
    exited_on: null,
    exit_reason: "",
    exit_reason_display: "",
    exit_note: "",
    ...overrides,
  };
}

function mount(
  roster: WltGroupMembership[],
  {
    canWrite = true,
    pool,
    officers = [],
  }: {
    canWrite?: boolean;
    pool?: { results: unknown[]; waiting_elsewhere: number; registered_here?: number; already_grouped_here?: number };
    officers?: unknown[];
  } = {},
) {
  // Two endpoints behind one mock: the roster and the candidate pool. Routing
  // by URL rather than by call order, because the modal fetches on open and the
  // order depends on what the test clicks.
  get.mockImplementation((url: string) => {
    const path = String(url);
    if (path.includes("candidates")) {
      return Promise.resolve({
        data: { kebele: { code: "k1", name: "Dembela" }, ...(pool ?? { results: [], waiting_elsewhere: 0 }) },
      });
    }
    if (path.includes("officers")) return Promise.resolve({ data: officers });
    return Promise.resolve({ data: roster });
  });
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
  // The panel navigates to a linkage now, and `useNavigate` throws outside a
  // router — which failed every test in this file rather than the one that
  // navigates, because it throws on render.
  return render(
    <TestAuth user={user}>
      <LanguageProvider>
        <App>
          <MemoryRouter>
            <GroupRoster group={GROUP} onChanged={() => {}} />
          </MemoryRouter>
        </App>
      </LanguageProvider>
    </TestAuth>,
  );
}


/**
 * The laptop roster, scoped.
 *
 * The panel renders the table and the phone cards together — jsdom applies no
 * stylesheet, so both branches of a `.only-laptop` / `.only-phone` pair are in
 * the tree. Every query below would otherwise find each member twice. Which
 * branch actually shows at a given width is a stylesheet question, and
 * `src/styles/responsive.test.ts` is what guards it.
 */
function laptopRoster(): HTMLElement {
  const table = document.querySelector(".roster-table");
  if (!table) throw new Error("no roster table rendered");
  return table as HTMLElement;
}

describe("GroupRoster", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("names every current member, which the member count never did", async () => {
    mount([membership(), membership({ id: "m2", person: "p2", full_name: "Bontu Diriba" })]);

    await screen.findAllByText("Chaltu Bekele");
    expect(within(laptopRoster()).getByText("Chaltu Bekele")).toBeInTheDocument();
    expect(within(laptopRoster()).getByText("Bontu Diriba")).toBeInTheDocument();
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

    await screen.findAllByText("Chaltu Bekele");
    expect(screen.queryByRole("button", { name: /Add a member/i })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: /Record that she left/i })).toHaveLength(0);
  });

  it("offers both write controls to a facilitator", async () => {
    mount([membership()]);

    expect(await screen.findByRole("button", { name: /Add a member/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Edit members and officers/i })).toBeInTheDocument();
  });

  it("opens her record from her name on the roster", async () => {
    mount([membership()]);
    await screen.findAllByText("Chaltu Bekele");

    // A button, not text: the roster had her name and no way to reach her.
    const name = within(laptopRoster()).getByRole("button", { name: "Chaltu Bekele" });
    expect(name).toBeInTheDocument();
  });

  it("leaves a name plain when there is no record to open", async () => {
    // A membership written before `add_member` required a profile. A name that
    // looks like a link and does nothing is worse than plain text.
    mount([membership({ profile: null })]);
    await screen.findAllByText("Chaltu Bekele");

    expect(within(laptopRoster()).queryByRole("button", { name: "Chaltu Bekele" })).toBeNull();
    expect(within(laptopRoster()).getByText("Chaltu Bekele")).toBeInTheDocument();
  });

  it("keeps the exit behind the edit modal rather than on every row", async () => {
    // Twenty exit buttons made the roster read as a list of things to undo.
    mount([membership()]);
    await screen.findAllByText("Chaltu Bekele");

    expect(within(laptopRoster()).queryByRole("button", { name: /Record that she left/i })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /Edit members and officers/i }));
    expect(await screen.findByRole("button", { name: /Record that she left/i })).toBeInTheDocument();
  });

  it("tags the chair on the roster without a second lookup", async () => {
    mount([membership()], {
      officers: [
        { id: "o1", group: "g1", person: "p1", full_name: "Chaltu Bekele", role: "CHAIR", from_date: "2026-01-01", to_date: null },
      ],
    });

    await screen.findAllByText("Chaltu Bekele");
    expect(within(laptopRoster()).getByText("Chair")).toBeInTheDocument();
  });

  it("does not tag a term that has ended", async () => {
    // A term is a dated range: she was chair, and is not now.
    mount([membership()], {
      officers: [
        { id: "o1", group: "g1", person: "p1", full_name: "Chaltu Bekele", role: "CHAIR", from_date: "2026-01-01", to_date: "2026-06-01" },
      ],
    });

    await screen.findAllByText("Chaltu Bekele");
    expect(within(laptopRoster()).queryByText("Chair")).toBeNull();
  });

  it("refuses to record an exit with no reason", async () => {
    // The check constraint can only say "not blank". "Moved away" and
    // "expelled" are opposite programme outcomes, so the form asks.
    mount([membership()]);
    const person = userEvent.setup();

    await person.click(await screen.findByRole("button", { name: /Edit members and officers/i }));
    await person.click((await screen.findAllByRole("button", { name: /Record that she left/i }))[0]);
    await person.click(await screen.findByRole("button", { name: /Record the exit/i }));

    await waitFor(() => expect(screen.getByText(/Choose why she is leaving/)).toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });

  it("says how many women wait elsewhere when the pool is empty", async () => {
    // The reported fault: the picker showed nothing and read as broken. A group
    // recruits only in its own kebele, so an empty list usually means geography
    // — and geography is something a facilitator can act on.
    mount([membership()], { pool: { results: [], waiting_elsewhere: 3, registered_here: 1, already_grouped_here: 1 } });

    await userEvent.click(await screen.findByRole("button", { name: /add a member/i }));

    expect(await screen.findByText(/No eligible women are free to join in Dembela/i)).toBeTruthy();
    expect(screen.getByText(/3 eligible women are waiting for a group in other kebeles/i)).toBeTruthy();
    expect(screen.getByText(/1 woman is registered there; 1 already belongs to a group/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /View this kebele in the WLT register/i })).toBeTruthy();
  });

  it("does not claim women wait elsewhere when none do", async () => {
    // A zero here would be a sentence saying nothing, on a dialog whose whole
    // job at this moment is to explain an absence.
    mount([membership()], { pool: { results: [], waiting_elsewhere: 0 } });

    await userEvent.click(await screen.findByRole("button", { name: /add a member/i }));

    expect(await screen.findByText(/No eligible women are free to join in Dembela/i)).toBeTruthy();
    expect(screen.queryByText(/waiting for a group in other kebeles/i)).toBeNull();
  });

  it("says the exit keeps her history rather than deleting her", async () => {
    mount([membership()]);
    const person = userEvent.setup();

    await person.click(await screen.findByRole("button", { name: /Edit members and officers/i }));
    await person.click((await screen.findAllByRole("button", { name: /Record that she left/i }))[0]);

    expect(await screen.findByText(/stays on the record with the date she left/i)).toBeInTheDocument();
  });
});
