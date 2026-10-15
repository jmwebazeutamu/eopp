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
 * What the two rows say, derived from the URL. jsdom measures nothing, so the
 * overflow arithmetic is tested in `navOverflow.test.ts`; here every link is on
 * the row and the claims are about which one is current.
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
  it("names the two rows differently, as landmarks", () => {
    renderNav("/cases");
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Section navigation" })).toBeInTheDocument();
  });

  it("marks the page as the page and its module only as somewhere you are inside", () => {
    renderNav("/cases");
    const primary = screen.getByRole("navigation", { name: "Main navigation" });
    const secondary = screen.getByRole("navigation", { name: "Section navigation" });

    // The module is `true`, never `page`: it is an ancestor of the page.
    expect(within(primary).getByRole("link", { name: /PSNP Beneficiary Referrals/ })).toHaveAttribute("aria-current", "true");
    expect(within(secondary).getByRole("link", { name: "Cases" })).toHaveAttribute("aria-current", "page");
    expect(within(secondary).getByRole("link", { name: /Referrals/ })).not.toHaveAttribute("aria-current");
  });

  it("keeps the module and page lit on a detail route", () => {
    renderNav("/cases/6f1c2d3e");
    const secondary = screen.getByRole("navigation", { name: "Section navigation" });
    expect(within(secondary).getByRole("link", { name: "Cases" })).toHaveAttribute("aria-current", "page");
  });

  it("lights a screen that an entry only fronts, so delivery tabs keep the row", () => {
    renderNav("/training");
    const secondary = screen.getByRole("navigation", { name: "Section navigation" });
    expect(within(secondary).getByRole("link", { name: "Delivery" })).toHaveAttribute("aria-current", "page");
  });

  it("omits the secondary row for a module that is one page", () => {
    renderNav("/grievances");
    expect(screen.queryByRole("navigation", { name: "Section navigation" })).toBeNull();
    const primary = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(primary).getByRole("link", { name: "Grievances" })).toHaveAttribute("aria-current", "page");
  });

  it("does not offer a role the destinations it lacks", () => {
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

  it("shows no 'More' when everything fits", () => {
    renderNav("/cases");
    expect(screen.queryByRole("button", { name: /More/ })).toBeNull();
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
