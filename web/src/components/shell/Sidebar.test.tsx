import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import Sidebar from "./Sidebar";
import { buildNav } from "./navModel";

vi.mock("./GlobalSearch", () => ({
  default: () => <div>Search</div>,
}));

vi.mock("./ScopeSelector", () => ({
  default: () => <div>Scope</div>,
}));

const ADMIN = testUser("SYSTEM_ADMIN", {
  access: {
    case_scope: "ALL",
    case_write: true,
    referral_scope: "ALL",
    referral_write: true,
    group_scope: "ALL",
    group_write: true,
    delivery_write: true,
  },
});

/** The rail as an element, so a test can `rerender` it at another path. */
function rail(pathname: string) {
  return (
    <MemoryRouter>
      <LanguageProvider>
        <div style={{ height: 600 }}>
          <Sidebar
            user={ADMIN}
            sections={buildNav(ADMIN, { openAlerts: 12 })}
            pathname={pathname}
            collapsed={false}
            onToggleCollapse={vi.fn()}
            footer={<div>Footer</div>}
          />
        </div>
      </LanguageProvider>
    </MemoryRouter>
  );
}

function renderRail(pathname: string) {
  // Sections are remembered per sitting, so one test's clicks must not decide
  // what the next one sees.
  sessionStorage.clear();
  return render(rail(pathname));
}

describe("Sidebar", () => {
  it("lets a section collapse to reduce a long nav", async () => {
    const user = userEvent.setup();
    renderRail("/cases");

    expect(screen.getByRole("button", { name: "Cases" })).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "PSNP Beneficiary Referrals" }),
    );

    expect(screen.queryByRole("button", { name: "Cases" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Directory" }),
    ).toBeInTheDocument();
  });

  it("opens every section closed, and only expands the one holding the current page", () => {
    // Four open sections put fifteen items in the rail, which is a list to read
    // rather than a place to navigate. Closed by default makes it four choices.
    renderRail("/cases");

    // The section holding /cases is open, because that is where the reader is.
    expect(screen.getByRole("button", { name: "Cases" })).toBeInTheDocument();
    // Everything else is shut: its heading is there, its items are not.
    expect(screen.getByRole("button", { name: "Directory" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Partners" })).toBeNull();
    expect(screen.queryByRole("button", { name: "SHGs" })).toBeNull();
  });

  it("follows the reader as navigation moves between sections", () => {
    // Derived from the route rather than written into state on arrival: storing
    // it would leave a section open behind you, and the rail would drift back
    // to the fully-expanded list this replaces.
    const { rerender } = renderRail("/cases");
    expect(screen.queryByRole("button", { name: "Partners" })).toBeNull();

    rerender(rail("/partners"));

    expect(screen.getByRole("button", { name: "Partners" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cases" })).toBeNull();
  });

  it("lets an explicit close beat being the active section", () => {
    // Somebody who shuts the section they are standing in gets what they asked
    // for; the route does not argue with them.
    renderRail("/cases");

    return userEvent
      .setup()
      .click(screen.getByRole("button", { name: "PSNP Beneficiary Referrals" }))
      .then(() => {
        expect(screen.queryByRole("button", { name: "Cases" })).toBeNull();
      });
  });

  it("keeps grievances reachable with every section shut", () => {
    // It has no heading, so there is nothing to collapse it into. A complaints
    // channel that can be folded away is one nobody finds.
    renderRail("/cases");
    expect(screen.getByRole("button", { name: "Grievances" })).toBeInTheDocument();
  });
});
