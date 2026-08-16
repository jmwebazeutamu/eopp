import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { LanguageProvider, useLang } from "./LanguageContext";
import { STRINGS } from "./strings";

/**
 * The handoff's language rules: a toggle swaps the strings, the font stack and
 * the leading together, and an untranslated string falls back to English rather
 * than showing a key — a half-translated row is a bug, but a visible key is a
 * worse one.
 */

function Probe() {
  const { t, lang, setLang } = useLang();
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="title">{t("cases.title")}</span>
      <span data-testid="interpolated">{t("case.slotsInUse", { used: 2, limit: 2 })}</span>
      <button type="button" onClick={() => setLang("am")}>
        switch
      </button>
    </div>
  );
}

describe("LanguageProvider", () => {
  it("interpolates named placeholders", () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("interpolated")).toHaveTextContent("2 of 2 parallel referrals in use");
  });

  it("swaps the font stack and the leading with the language", async () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--leading")).toBe("1.5");
    expect(root.style.getPropertyValue("--font-body")).toContain("Archivo");

    await userEvent.click(screen.getByText("switch"));

    // Ge'ez leads first and needs the looser leading.
    expect(root.style.getPropertyValue("--leading")).toBe("1.75");
    expect(root.style.getPropertyValue("--font-body")).toMatch(/^"Noto Sans Ethiopic"/);
    expect(root.lang).toBe("am");
  });

  it("falls back to English for a string the language has no table entry for", async () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await userEvent.click(screen.getByText("switch"));
    // Amharic is not populated yet; the user sees English, never "cases.title".
    expect(screen.getByTestId("title")).toHaveTextContent(STRINGS["cases.title"]);
  });

  it("remembers the choice across a reload", async () => {
    const { unmount } = render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await userEvent.click(screen.getByText("switch"));
    unmount();

    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("lang")).toHaveTextContent("am");
  });
});
