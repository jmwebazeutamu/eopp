import { App } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../auth/AuthContext";
import { LanguageProvider } from "../../i18n/LanguageContext";
import SignInCard from "./SignInCard";

/**
 * The sign-in form's accessibility contract, which the build prompt states as
 * seven requirements. Each one below is one of them, because they are the part
 * of this page a later refactor is most likely to quietly undo — the reason the
 * form is hand-built rather than antd's `Form` in the first place.
 */

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

function mount(login = vi.fn().mockResolvedValue(undefined)) {
  render(
    <MemoryRouter>
      <App>
        <AuthContext.Provider
          value={{ user: null, loading: false, login, logout: vi.fn(), setUser: vi.fn() }}
        >
          <LanguageProvider>
            <SignInCard />
          </LanguageProvider>
        </AuthContext.Provider>
      </App>
    </MemoryRouter>,
  );
  return login;
}

describe("SignInCard", () => {
  it("labels every input visibly rather than by placeholder", () => {
    mount();
    // `getByLabelText` passes on a placeholder too, so the label element itself
    // is what is asserted — a placeholder disappears the moment you type.
    expect(document.querySelectorAll("label")).toHaveLength(2);
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(document.querySelector("input[placeholder]")).toBeNull();
  });

  it("carries the autocomplete tokens a password manager needs", () => {
    mount();
    expect(screen.getByLabelText("Username")).toHaveAttribute("autocomplete", "username");
    expect(document.querySelector('input[type="password"]')).toHaveAttribute(
      "autocomplete",
      "current-password",
    );
  });

  it("does not block paste", () => {
    // WCAG 2.2 accessible authentication. Blocking paste breaks the password
    // manager, which is most of what makes a strong password usable at all.
    mount();
    const password = document.querySelector('input[type="password"]') as HTMLInputElement;
    const event = new Event("paste", { bubbles: true, cancelable: true });
    password.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("renders each error beside its own field, not as a summary", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const username = screen.getByLabelText("Username");
    expect(username).toHaveAttribute("aria-invalid", "true");
    // The message is what `aria-describedby` points at, so a screen reader
    // reads it as part of the field rather than as loose text somewhere above.
    const describedBy = username.getAttribute("aria-describedby") as string;
    expect(document.getElementById(describedBy)?.textContent).toContain("Enter your username");
  });

  it("moves focus to the first invalid field", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByLabelText("Username")).toHaveFocus();

    await user.type(screen.getByLabelText("Username"), "wlt1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(document.querySelector('input[type="password"]')).toHaveFocus();
  });

  it("toggles the password with a pressed state rather than swapping a label alone", async () => {
    const user = userEvent.setup();
    mount();
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelector('input[name="password"]')).toHaveAttribute("type", "text");
  });

  it("never fails silently", async () => {
    const user = userEvent.setup();
    mount(vi.fn().mockRejectedValue(new Error("nope")));

    await user.type(screen.getByLabelText("Username"), "wlt1");
    await user.type(document.querySelector('input[type="password"]') as HTMLElement, "pw");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // `role="alert"`, because this only ever appears because something failed.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Could not sign in");
  });

  it("hands the landing decision back to the root route", async () => {
    const user = userEvent.setup();
    const login = mount();

    await user.type(screen.getByLabelText("Username"), "wlt1");
    await user.type(document.querySelector('input[type="password"]') as HTMLElement, "pw");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("wlt1", "pw"));
    // Not "/cases". Every WLT role carries `case_scope: NONE`, and the old form
    // navigated there unconditionally.
    expect(navigate).toHaveBeenCalledWith("/", { replace: true });
  });

  it("offers no control it cannot honour", () => {
    // The mock draws "Forgot password" and "Trust this device for 30 days".
    // There is no reset flow and no device trust behind either, and a dead
    // control is worst on the screen where somebody has already failed to
    // get in.
    mount();
    expect(screen.queryByText(/forgot password/i)).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
