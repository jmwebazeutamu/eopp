import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageContext";
import { ScopeProvider } from "../components/shell/ScopeContext";
import { TestAuth } from "../test/authHarness";

/**
 * The filter parameter round-trips: the chip row writes what the list reads.
 *
 * This is the gap that shipped. The server names the query parameter on each
 * counter, the chips write it to the URL, and the page is supposed to read the
 * same key back. When the counters were renamed to the `__in` lookups so the
 * chips could multi-select, only the alerts page's reader was updated — so on
 * Cases and Referrals the URL changed, the chip lit up, and the list did not
 * filter at all.
 *
 * Nothing caught it. `FilterChips.test.tsx` asserts the URL the chips write;
 * the page tests never asserted the request the page makes. This closes that
 * seam by checking the actual outgoing params.
 */

const get = vi.fn();
vi.mock("../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));
vi.mock("../components/CaseFormModal", () => ({ default: () => null }));
vi.mock("../components/YouthFormModal", () => ({ default: () => null }));
vi.mock("../components/YouthDetailModal", () => ({ default: () => null }));

const { default: CaseListPage } = await import("./CaseListPage");
const { default: ReferralsPage } = await import("./ReferralsPage");

function renderAt(Page: () => React.ReactNode, url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <LanguageProvider>
        <TestAuth>
          <ScopeProvider user={null}>
            <Page />
          </ScopeProvider>
        </TestAuth>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

/** Every `params` object the page sent, merged. */
function sentParams() {
  return get.mock.calls.map((call) => (call[1] as { params?: Record<string, unknown> })?.params ?? {});
}

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ data: { count: 0, results: [], total: 0, counters: [], onward: [], replacement: [] } });
});

describe("list filter round-trip", () => {
  it("Cases sends the status filter the chip row wrote", async () => {
    renderAt(CaseListPage, "/cases?case_status__in=STALLED");
    await waitFor(() => expect(get).toHaveBeenCalled());
    // The page used to read `case_status`, so this key never left the browser.
    await waitFor(() =>
      expect(sentParams().some((p) => p.case_status__in === "STALLED")).toBe(true),
    );
  });

  it("Cases passes a multi-select list through untouched", async () => {
    renderAt(CaseListPage, "/cases?case_status__in=STALLED,PLACED");
    await waitFor(() =>
      expect(sentParams().some((p) => p.case_status__in === "STALLED,PLACED")).toBe(true),
    );
  });

  it("Cases sends no status filter when no chip is selected", async () => {
    renderAt(CaseListPage, "/cases");
    await waitFor(() => expect(get).toHaveBeenCalled());
    // Not the empty string — an empty value is a filter on "", not an absence.
    expect(sentParams().every((p) => p.case_status__in === undefined)).toBe(true);
  });

  it("Referrals narrows its queues to the selected statuses", async () => {
    renderAt(ReferralsPage, "/referrals?status__in=ACTIVE");
    await waitFor(() => expect(get).toHaveBeenCalled());
    const statuses = sentParams()
      .map((p) => p.status)
      .filter(Boolean);
    // The queue is grouped by status, so a chosen status asks for that group
    // and skips the other rather than filtering client-side.
    expect(statuses).toContain("ACTIVE");
    expect(statuses).not.toContain("PENDING_CONFIRMATION");
  });

  it("Referrals asks for both queues when a chip selects both", async () => {
    renderAt(ReferralsPage, "/referrals?status__in=ACTIVE,PENDING_CONFIRMATION");
    await waitFor(() => expect(get).toHaveBeenCalled());
    const statuses = sentParams()
      .map((p) => p.status)
      .filter(Boolean);
    expect(statuses).toContain("ACTIVE");
    expect(statuses).toContain("PENDING_CONFIRMATION");
  });

  it("Referrals asks for every queue when nothing is selected", async () => {
    renderAt(ReferralsPage, "/referrals");
    await waitFor(() => expect(get).toHaveBeenCalled());
    const statuses = sentParams()
      .map((p) => p.status)
      .filter(Boolean);
    expect(statuses).toContain("ACTIVE");
    expect(statuses).toContain("PENDING_CONFIRMATION");
  });
});
