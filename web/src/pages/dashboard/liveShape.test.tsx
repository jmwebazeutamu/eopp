import type React from "react";

import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TestAuth } from "../../test/authHarness";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import myWork from "./__fixtures__/my-work.live.json";
import programme from "./__fixtures__/programme.live.json";
import results from "./__fixtures__/results.live.json";
import woreda from "./__fixtures__/woreda.live.json";

/**
 * Every tier renders against a payload captured from the running API.
 *
 * The hand-written fixtures in the other suites describe what each page *needs*
 * — useful for asserting behaviour, useless for catching drift, because they
 * are maintained alongside the component that consumes them. When the server
 * stopped sending `{ lag: { days, n } }` and started sending
 * `{ median_days, n }`, the fixture and the TypeScript type both still carried
 * the old shape, every test passed, and the Programme page rendered blank in
 * the browser.
 *
 * These fixtures are captured from `/api/v1/dashboard/*` and refreshed by hand.
 * They are not asserting numbers — the seed changes those constantly — only
 * that each page survives the shape the server actually sends.
 *
 * Refresh with:
 *   curl -H "Authorization: Bearer $TOKEN" \
 *     http://localhost:8007/api/v1/dashboard/programme/ | python3 -m json.tool \
 *     > src/pages/dashboard/__fixtures__/programme.live.json
 */

const get = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: ProgrammePage } = await import("./ProgrammePage");
const { default: WoredaPage } = await import("./WoredaPage");
const { default: ResultsPage } = await import("./ResultsPage");
const { default: MyWorkPage } = await import("./MyWorkPage");

function renderWith(Page: () => React.ReactNode, data: unknown) {
  get.mockResolvedValue({ data });
  return render(
    <MemoryRouter>
      <TestAuth>
      <LanguageProvider>
        <App>
          <Page />
        </App>
      </LanguageProvider>
    </TestAuth>
    </MemoryRouter>,
  );
}

beforeEach(() => get.mockReset());

describe("every tier renders against the live payload shape", () => {
  it("programme", async () => {
    renderWith(ProgrammePage, programme);
    // The heading proves the tree mounted; a shape error unmounts it entirely
    // and leaves the page blank, which is exactly how this reached the browser.
    expect(await screen.findByText("Programme performance")).toBeInTheDocument();
    expect(await screen.findByText("Partner performance")).toBeInTheDocument();
    expect(await screen.findByText("Confirmation lag by partner")).toBeInTheDocument();
  });

  it("woreda", async () => {
    renderWith(WoredaPage, woreda);
    expect(await screen.findByText("Woreda oversight")).toBeInTheDocument();
    expect(await screen.findByText("Partner response time")).toBeInTheDocument();
  });

  it("results", async () => {
    renderWith(ResultsPage, results);
    expect(await screen.findByText("Results against targets")).toBeInTheDocument();
    expect(await screen.findByText("Results framework")).toBeInTheDocument();
  });

  it("my work", async () => {
    renderWith(MyWorkPage, myWork);
    expect(await screen.findByText("My work today")).toBeInTheDocument();
  });
});
