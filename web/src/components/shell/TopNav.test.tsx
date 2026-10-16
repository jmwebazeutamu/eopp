import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import MobileNav from "./MobileNav";
import { ScopeProvider } from "./ScopeContext";
import { buildNav } from "./navModel";
import TopNav from "./TopNav";

/**
 * What the row and its dropdown panels say, derived from the URL, and how a
 * panel opens and closes.
 */

const caseManager = testUser("CASE_MANAGER", {
  access: {
    case_scope: "OWN_CASELOAD",
    case_write: true,
    referral_scope: "OWN_CASELOAD",
    referral_write: true,
    group_scope: "NONE",
    group_write: false,
    delivery_write: true,
  },
});

function renderNav(path: string, user = caseManager) {
  const sections = buildNav(user, { openAlerts: 2 });
  return render(
    <LanguageProvider>
      <MemoryRouter initialEntries={[path]}>
        <TopNav sections={sections} pathname={path} />
      </MemoryRouter>
    </LanguageProvider>,
  );
}

describe("TopNav", () => {
  const nav = () => screen.getByRole("navigation", { name: "Main navigation" });
  const trigger = () => within(nav()).getByRole("button", { name: /PSNP Beneficiary Referrals/ });

  it("has one navigation landmark and no always-visible secondary row", () => {
    renderNav("/cases");
    expect(nav()).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Section navigation" })).toBeNull();
  });

  it("marks the current module without opening its panel on load", () => {
    renderNav("/cases");
    expect(trigger()).toHaveAttribute("data-current", "true");
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(within(nav()).queryByRole("link", { name: "Cases" })).toBeNull();
  });

  it("opens a panel of links, with the page marked as the page", async () => {
    renderNav("/cases/6f1c2d3e");
    await userEvent.setup().click(trigger());
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(within(nav()).getByRole("link", { name: "Cases" })).toHaveAttribute("aria-current", "page");
    expect(within(nav()).getByRole("link", { name: /Referrals/ })).not.toHaveAttribute("aria-current");
  });

  it("lights a screen that an entry only fronts", async () => {
    renderNav("/training");
    await userEvent.setup().click(trigger());
    expect(within(nav()).getByRole("link", { name: "Delivery" })).toHaveAttribute("aria-current", "page");
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    renderNav("/cases");
    await user.click(trigger());
    await user.keyboard("{Escape}");
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(trigger()).toHaveFocus();
  });

  it("closes on an outside click, and keeps only one panel open", async () => {
    const user = userEvent.setup();
    renderNav("/cases");
    await user.click(trigger());
    await user.click(document.body);
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes when a link is followed", async () => {
    const user = userEvent.setup();
    renderNav("/cases");
    await user.click(trigger());
    await user.click(within(nav()).getByRole("link", { name: /Referrals/ }));
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("renders a one-page module as a plain link", () => {
    renderNav("/grievances");
    expect(within(nav()).getByRole("link", { name: "Grievances" })).toHaveAttribute("aria-current", "page");
  });

  it("does not offer a role the destinations it lacks", async () => {
    const partner = testUser("PARTNER_STAFF", {
      access: {
        case_scope: "NONE",
        case_write: false,
        referral_scope: "LINKED",
        referral_write: false,
        group_scope: "NONE",
        group_write: false,
        delivery_write: false,
      },
    });
    renderNav("/partners", partner);
    expect(screen.queryByRole("link", { name: /registry/i })).toBeNull();
    expect(screen.queryByRole("link", { name: "Cases" })).toBeNull();
  });
});

describe("MobileNav", () => {
  function renderMobile(path = "/cases") {
    const sections = buildNav(caseManager, { openAlerts: 0 });
    return render(
      <LanguageProvider>
        <MemoryRouter initialEntries={[path]}>
          <ScopeProvider user={caseManager}>
            <MobileNav
              user={caseManager}
              sections={sections}
              pathname={path}
              onSignOut={() => {}}
              onOpenProfile={() => {}}
            />
          </ScopeProvider>
        </MemoryRouter>
      </LanguageProvider>,
    );
  }

  it("is a labelled button, and the menu is absent until it is opened", async () => {
    renderMobile();
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Main navigation" })).toBeNull();

    await userEvent.setup().click(button);

    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Cases" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Grievances" })).toBeInTheDocument();
  });

  it("carries the account actions, so sign-out is reachable on a phone", async () => {
    renderMobile();
    await userEvent.setup().click(screen.getByRole("button", { name: "Menu" }));
    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
