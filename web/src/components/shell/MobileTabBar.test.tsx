import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Role } from "../../api/types";
import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import MobileTabBar from "./MobileTabBar";
import { buildNav } from "./navModel";

/**
 * What the phone bar carries, and what it moves out of the way.
 *
 * The bar used to carry every nav item — seven at the widest — across 390px,
 * which gave each 55px and made "Beneficiary registry" wrap to two lines at 9px.
 */

function renderBar(role: Role, access = {}, pathname = "/cases") {
  const user = testUser(role, {
    access: {
      case_scope: "OWN_CASELOAD",
      case_write: true,
      referral_scope: "OWN_CASELOAD",
      referral_write: true,
      group_scope: "NONE",
      group_write: false,
      delivery_write: false,
      ...access,
    },
  });
  render(
    <MemoryRouter>
      <LanguageProvider>
        <MobileTabBar
          user={user}
          sections={buildNav(user, { openAlerts: 4 })}
          pathname={pathname}
          onSignOut={vi.fn()}
        />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

const barLabels = () =>
  [...document.querySelectorAll("nav button")].map((b) => (b.textContent ?? "").trim());

describe("MobileTabBar", () => {
  it("carries five: the role's work, then More", () => {
    renderBar("CASE_MANAGER");
    expect(barLabels()).toEqual(["My work", "Cases", "Referrals", "Alerts", "More"]);
  });

  it("shortens the registry label so nothing wraps at 360px", async () => {
    renderBar("CASE_MANAGER");
    // Not on the bar — in the sheet, and shortened there too.
    expect(barLabels()).not.toContain("Beneficiary registry");
    await userEvent.click(screen.getByRole("button", { name: /More/ }));
    expect(await screen.findByRole("button", { name: "People" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Beneficiary registry" })).toBeNull();
  });

  it("puts only the role's first dashboard tier on the bar", () => {
    // An administrator is offered four tiers. Four dashboards on a phone bar is
    // not navigation.
    renderBar("SYSTEM_ADMIN", { case_scope: "ALL" });
    const labels = barLabels();
    expect(labels.filter((l) => ["My work", "Woreda", "Programme", "Results"].includes(l))).toEqual(["My work"]);
    expect(labels).toHaveLength(5);
  });

  it("holds the rest, the language switch and sign out in the More sheet", async () => {
    const signOut = vi.fn();
    const user = testUser("SYSTEM_ADMIN", {
      access: {
        case_scope: "ALL",
        case_write: true,
        referral_scope: "ALL",
        referral_write: true,
        group_scope: "NONE",
        group_write: false,
        delivery_write: false,
      },
    });
    render(
      <MemoryRouter>
        <LanguageProvider>
          <MobileTabBar user={user} sections={buildNav(user, { openAlerts: 0 })} pathname="/cases" onSignOut={signOut} />
        </LanguageProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: /More/ }));

    expect(await screen.findByRole("button", { name: "Partners" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("marks the active destination for a screen reader, not by colour alone", () => {
    renderBar("CASE_MANAGER", {}, "/cases/abc-123");
    const cases = screen.getByRole("button", { name: /Cases/ });
    expect(cases).toHaveAttribute("aria-current", "page");
  });

  it("marks More as active when the open screen lives inside it", () => {
    renderBar("CASE_MANAGER", {}, "/partners");
    expect(screen.getByRole("button", { name: /More/ })).toHaveAttribute("aria-current", "page");
  });
});
