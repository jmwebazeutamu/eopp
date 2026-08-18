import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import UserMenu, { initialsOf } from "./UserMenu";

/**
 * The account menu's behaviour, which is the part that can break invisibly.
 *
 * Appearance is checked in a browser — jsdom applies no stylesheet. What is
 * asserted here is that the menu opens, closes on Escape, returns focus to its
 * trigger, and that sign-out is reachable at all: before this menu existed the
 * only sign-out button in the application sat at the foot of a rail that
 * stretched to the height of the page, 2,153px below the fold.
 */

function renderMenu(onSignOut = vi.fn(), collapsed = false) {
  render(
    <LanguageProvider>
      <UserMenu user={testUser("CASE_MANAGER", { full_name: "Almaz Tesfaye", woreda_assignment: ["Adama"] })}
        collapsed={collapsed} onSignOut={onSignOut} />
    </LanguageProvider>,
  );
  return onSignOut;
}

describe("UserMenu", () => {
  it("opens on click and shows name, role, woreda and sign out", async () => {
    const user = userEvent.setup();
    renderMenu();
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { expanded: false }));

    const menu = screen.getByRole("dialog");
    expect(menu).toHaveTextContent("Almaz Tesfaye");
    expect(menu).toHaveTextContent("CASE_MANAGER");
    expect(menu).toHaveTextContent("Adama");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("says All woredas rather than an empty label for an unassigned account", () => {
    // The header used to render "Woreda: —" for an administrator whose scope is
    // every woreda. An em dash reads as "none", which is the opposite.
    render(
      <LanguageProvider>
        <UserMenu user={testUser("SYSTEM_ADMIN", { woreda_assignment: [] })} collapsed={false} onSignOut={vi.fn()} />
      </LanguageProvider>,
    );
    return userEvent.setup().click(screen.getByRole("button", { expanded: false })).then(() => {
      expect(screen.getByRole("dialog")).toHaveTextContent("All woredas");
    });
  });

  it("closes on Escape and puts focus back on the trigger", async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole("button", { expanded: false });
    await user.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).toBeNull();
    // Without this a keyboard user lands on the document body and restarts
    // from the top of the page.
    expect(screen.getByRole("button", { expanded: false })).toHaveFocus();
  });

  it("carries the language switch, so it is reachable once signed in", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "አማርኛ", pressed: false })).toBeInTheDocument();
  });

  it("signs out through the callback", async () => {
    const user = userEvent.setup();
    const onSignOut = renderMenu();
    await user.click(screen.getByRole("button", { expanded: false }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
  });

  it("keeps the account reachable by name when the rail is collapsed", async () => {
    const user = userEvent.setup();
    renderMenu(vi.fn(), true);
    // At 64px the name is not drawn, so it has to be in the accessible name or
    // the avatar is an unlabelled circle.
    const trigger = screen.getByRole("button", { name: /Almaz Tesfaye/ });
    await user.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("initialsOf", () => {
  it("takes the first and last name", () => {
    expect(initialsOf("Almaz Tesfaye")).toBe("AT");
    expect(initialsOf("Selam Feyisa Bekele")).toBe("SB");
  });

  it("handles a single name and empty input without throwing", () => {
    expect(initialsOf("Almaz")).toBe("A");
    expect(initialsOf("   ")).toBe("?");
  });

  it("counts a Ge'ez syllable as one character", () => {
    // Naive `name[0]` is fine here, but spread-then-index is what keeps it
    // correct if a name ever carries a surrogate pair.
    expect(initialsOf("አlmaz ተsfaye")).toBe("አተ");
  });
});
