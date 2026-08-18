import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageContext";
import { TestAuth } from "../test/authHarness";
import ListPage from "./ListPage";

/**
 * The shared list frame.
 *
 * What is asserted here is the arrangement's contract — one search field, the
 * chips, and either rows or a real empty state — not its appearance, which
 * jsdom cannot see and which is measured in a browser instead.
 */

const get = vi.fn();
vi.mock("../api/client", () => ({ api: { get: (...args: unknown[]) => get(...args) } }));

const SUMMARY = {
  total: 12,
  counters: [{ param: "case_status__in", value: "ACTIVE", label: "Active", count: 12 }],
};

function Probe() {
  const [params] = useSearchParams();
  return <span data-testid="query">{params.toString()}</span>;
}

function renderList(props: Partial<React.ComponentProps<typeof ListPage>> = {}, entry = "/cases") {
  localStorage.clear();
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <LanguageProvider>
        <TestAuth>
          <ListPage title="Caseload" searchPlaceholder="Search cases" resource="/cases" {...props}>
            {(density) => (
              <table className={`table ${density}`}>
                <tbody>
                  <tr data-testid="row">
                    <td>a row</td>
                  </tr>
                </tbody>
              </table>
            )}
          </ListPage>
          <Probe />
        </TestAuth>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ data: SUMMARY });
});

describe("ListPage", () => {
  it("carries the title, one search field and the chip row", async () => {
    renderList();
    expect(screen.getByRole("heading", { name: "Caseload" })).toBeInTheDocument();
    expect(screen.getAllByRole("searchbox")).toHaveLength(1);
    expect(await screen.findByRole("group", { name: "Filter the list" })).toBeInTheDocument();
  });

  it("puts the primary action on the title row", () => {
    renderList({ action: <button type="button">Open a case</button> });
    expect(screen.getByRole("button", { name: "Open a case" })).toBeInTheDocument();
  });

  it("renders rows when there are rows, and no empty state", () => {
    renderList({ empty: { when: false, title: "This is your caseload.", body: "…" } });
    expect(screen.getByTestId("row")).toBeInTheDocument();
    expect(screen.queryByText("This is your caseload.")).toBeNull();
  });

  it("replaces a bare table header with an explanation when there is nothing", () => {
    // The tables used to render a header over nothing, which reads as a
    // failure rather than a fact.
    renderList({ empty: { when: true, title: "This is your caseload.", body: "A case appears here once…" } });
    expect(screen.queryByTestId("row")).toBeNull();
    expect(screen.getByText("This is your caseload.")).toBeInTheDocument();
    expect(screen.getByText("A case appears here once…")).toBeInTheDocument();
  });

  it("says the filters are the reason when filters are the reason", async () => {
    // An empty caseload is a finding; an over-filtered one is a mistake. They
    // look identical and mean opposite things.
    renderList({ empty: { when: true, title: "This is your caseload.", body: "…" } }, "/cases?q=zzz");
    expect(screen.getByText("No rows match the filters in use.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByTestId("query")).not.toHaveTextContent("q=zzz");
  });

  it("never clears the woreda scope from an empty list", async () => {
    // Clearing it would silently widen the user's view past what they chose,
    // which is the one thing a "clear filters" button must not do.
    renderList({ empty: { when: true, title: "t", body: "b" } }, "/cases?woreda=Adama&q=zzz");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByTestId("query")).toHaveTextContent("woreda=Adama");
    expect(screen.getByTestId("query")).not.toHaveTextContent("q=zzz");
  });

  it("switches row density and remembers it for the account", async () => {
    const { unmount } = renderList();
    expect(screen.getByTestId("row").closest("table")).not.toHaveClass("table--compact");

    await userEvent.click(screen.getByRole("button", { name: /Compact rows/ }));
    expect(screen.getByTestId("row").closest("table")).toHaveClass("table--compact");

    unmount();
    render(
      <MemoryRouter>
        <LanguageProvider>
          <TestAuth>
            <ListPage title="Caseload" searchPlaceholder="Search cases">
              {(density) => (
                <table className={`table ${density}`}>
                  <tbody>
                    <tr data-testid="row2">
                      <td>a row</td>
                    </tr>
                  </tbody>
                </table>
              )}
            </ListPage>
          </TestAuth>
        </LanguageProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("row2").closest("table")).toHaveClass("table--compact");
  });

  it("offers no density control on a screen with no rows to resize", () => {
    // Partners and Users render stacked cards; a control that does nothing is
    // worse than no control.
    renderList({ rowDensity: false });
    expect(screen.queryByRole("button", { name: /Compact rows/ })).toBeNull();
  });
});
