import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageContext";

/**
 * The dashboard's failure path, in its own file.
 *
 * It lives apart from `DashboardPage.test.tsx` because a rejected fetch shares
 * badly with the tests around it: vitest attributes the rejection to whichever
 * test is running when it settles, and the success-path tests in that file leave
 * their own effects in flight. One rejecting mock per module keeps the
 * attribution unambiguous.
 */

const get = vi.fn();
vi.mock("../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: DashboardPage } = await import("./DashboardPage");

describe("DashboardPage, when the figures cannot be loaded", () => {
  it("says so, rather than rendering a programme at zero", async () => {
    get.mockImplementation(() => Promise.reject(new Error("network")));

    render(
      <LanguageProvider>
        <App>
          <DashboardPage />
        </App>
      </LanguageProvider>,
    );

    // What the user sees is the whole point: a dashboard that failed to load
    // must say it failed. Rendering empty panels would read as a programme that
    // has registered nobody and placed nobody.
    expect(await screen.findByText("Could not load the dashboard.")).toBeInTheDocument();
    expect(screen.queryByText("Registration to placement")).not.toBeInTheDocument();
    expect(screen.queryByText("Placements this quarter")).not.toBeInTheDocument();
  });
});
