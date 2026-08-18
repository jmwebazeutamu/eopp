import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import { ScopeProvider, scopeParam, useScope } from "./ScopeContext";

/**
 * The woreda scope.
 *
 * Presentation, not permission: `ScopedQuerySetMixin` decides what an account
 * may read and this only narrows within it. What matters here is that the
 * narrowing is honest — a scope the account cannot see must not silently
 * filter a screen to nothing and read as an empty programme.
 */

function Probe() {
  const scope = useScope();
  const location = useLocation();
  return (
    <div>
      <span data-testid="value">{scope.woreda || "(all)"}</span>
      <span data-testid="label">{scope.label}</span>
      <span data-testid="selectable">{String(scope.selectable)}</span>
      <span data-testid="search">{location.search || "(none)"}</span>
      <button type="button" onClick={() => scope.setWoreda("Bishoftu")}>
        pick Bishoftu
      </button>
      <button type="button" onClick={() => scope.setWoreda("")}>
        pick all
      </button>
    </div>
  );
}

function renderScope(woredas: string[], entry = "/cases") {
  localStorage.clear();
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <LanguageProvider>
        <ScopeProvider user={testUser("CASE_MANAGER", { scopable_woredas: woredas })}>
          <Probe />
        </ScopeProvider>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

describe("ScopeProvider", () => {
  it("starts at all woredas and says so", () => {
    renderScope(["Adama", "Bishoftu"]);
    expect(screen.getByTestId("value")).toHaveTextContent("(all)");
    expect(screen.getByTestId("label")).toHaveTextContent("All woredas");
  });

  it("writes the selection into the URL so the view is shareable", async () => {
    renderScope(["Adama", "Bishoftu"]);
    await userEvent.click(screen.getByRole("button", { name: "pick Bishoftu" }));
    expect(screen.getByTestId("value")).toHaveTextContent("Bishoftu");
    expect(screen.getByTestId("search")).toHaveTextContent("woreda=Bishoftu");
  });

  it("drops the parameter entirely when the scope is cleared", async () => {
    renderScope(["Adama", "Bishoftu"]);
    await userEvent.click(screen.getByRole("button", { name: "pick Bishoftu" }));
    await userEvent.click(screen.getByRole("button", { name: "pick all" }));
    // `?woreda=` empty would be a filter on the empty string, not an absence.
    expect(screen.getByTestId("search")).not.toHaveTextContent("woreda");
  });

  it("resets the page when the scope changes", async () => {
    renderScope(["Adama", "Bishoftu"], "/cases?page=4");
    await userEvent.click(screen.getByRole("button", { name: "pick Bishoftu" }));
    // Page 4 of the old result set points at rows that may not exist in the new.
    expect(screen.getByTestId("search")).not.toHaveTextContent("page=4");
  });

  it("takes the scope from a shared link ahead of the stored preference", () => {
    renderScope(["Adama", "Bishoftu"], "/cases?woreda=Adama");
    expect(screen.getByTestId("value")).toHaveTextContent("Adama");
  });

  it("falls back to all woredas for a scope the account cannot see", () => {
    // A link naming a woreda outside the recipient's assignment would otherwise
    // filter their screen to nothing and look like a programme with no cases.
    renderScope(["Adama"], "/cases?woreda=Mekelle");
    expect(screen.getByTestId("value")).toHaveTextContent("(all)");
  });

  it("offers no choice to a single-woreda account, but still names it", () => {
    renderScope(["Adama"]);
    expect(screen.getByTestId("selectable")).toHaveTextContent("false");
  });
});

describe("scopeParam", () => {
  it("omits the parameter rather than sending an empty one", () => {
    expect(scopeParam("")).toEqual({});
    expect(scopeParam("", "case__woreda")).toEqual({});
  });

  it("names the column each endpoint actually filters on", () => {
    // Cases and youth carry `woreda`; referrals and alerts reach it through
    // their case. Sending the wrong one is a filter silently ignored by DRF.
    expect(scopeParam("Adama")).toEqual({ woreda: "Adama" });
    expect(scopeParam("Adama", "case__woreda")).toEqual({ case__woreda: "Adama" });
  });
});
