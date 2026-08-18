import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageContext";
import FilterChips from "./FilterChips";

const get = vi.fn();
vi.mock("../api/client", () => ({ api: { get: (...args: unknown[]) => get(...args) } }));

const SUMMARY = {
  total: 14,
  counters: [
    { param: "case_status__in", value: "ACTIVE", label: "Active", count: 11 },
    { param: "case_status__in", value: "STALLED", label: "Stalled", count: 3 },
    { param: "case_status__in", value: "PLACED", label: "Placed", count: 0 },
  ],
};

function Probe() {
  const [params] = useSearchParams();
  return <span data-testid="query">{params.toString()}</span>;
}

function renderDashboard(props = {}) {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <FilterChips resource="/cases" {...props} />
        <Probe />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

describe("FilterChips", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: SUMMARY });
  });

  it("shows a count and its label per counter", async () => {
    renderDashboard();
    expect(await screen.findByText("11")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Stalled")).toBeInTheDocument();
  });

  it("applies the filter the counter itself declares", async () => {
    // The server names the query parameter, so the counter and the list it
    // filters to cannot disagree about what was counted.
    renderDashboard();
    await userEvent.click(await screen.findByText("Stalled"));
    expect(screen.getByTestId("query")).toHaveTextContent("case_status__in=STALLED");
  });

  it("clears the filter when the same counter is clicked again", async () => {
    renderDashboard();
    await userEvent.click(await screen.findByText("Stalled"));
    await userEvent.click(screen.getByText("Stalled"));
    expect(screen.getByTestId("query")).toHaveTextContent("");
  });

  it("drops the page cursor when the filter changes", async () => {
    render(
      <MemoryRouter initialEntries={["/cases?page=3"]}>
        <LanguageProvider>
          <FilterChips resource="/cases" />
          <Probe />
        </LanguageProvider>
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByText("Stalled"));
    expect(screen.getByTestId("query")).not.toHaveTextContent("page=3");
  });

  it("asks the server once, not once per render", async () => {
    // `params` arrives as an object literal, so a dependency on its identity
    // would refetch forever. This is that regression.
    renderDashboard({ params: { woreda: "Adama" } });
    await screen.findByText("11");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("passes the screen's own filters through to the counts", async () => {
    renderDashboard({ params: { woreda: "Adama" } });
    await screen.findByText("11");
    expect(get).toHaveBeenCalledWith("/cases/summary/", { params: { search: undefined, woreda: "Adama" } });
  });

  it("renders nothing rather than an error when the summary fails", async () => {
    get.mockRejectedValue(new Error("offline"));
    const { container } = renderDashboard();
    // The list below it still loads and reports its own failure.
    await waitFor(() => expect(container.querySelector(".chip-row")).toBeNull());
  });

  it("renders nothing when there is nothing to count", async () => {
    get.mockResolvedValue({ data: { total: 0, counters: [] } });
    const { container } = renderDashboard();
    await waitFor(() => expect(container.querySelector(".chip-row")).toBeNull());
  });

  it("leads with an All chip carrying the unfiltered total", async () => {
    renderDashboard();
    const all = await screen.findByRole("button", { name: /All/ });
    expect(all).toHaveTextContent("14");
    expect(all).toHaveAttribute("aria-pressed", "true");
  });

  it("clears every filter from the All chip", async () => {
    renderDashboard();
    await userEvent.click(await screen.findByText("Stalled"));
    expect(screen.getByTestId("query")).toHaveTextContent("case_status__in=STALLED");

    await userEvent.click(screen.getByRole("button", { name: /All/ }));
    expect(screen.getByTestId("query")).toHaveTextContent("");
  });

  it("selects more than one value on a parameter that supports it", async () => {
    // `__in` is django-filter's BaseInFilter, which reads a comma-separated
    // list. Without the suffix, sending two values returns rows matching
    // neither, so the component must not offer it.
    renderDashboard();
    await userEvent.click(await screen.findByText("Active"));
    await userEvent.click(screen.getByText("Stalled"));
    expect(screen.getByTestId("query")).toHaveTextContent("case_status__in=ACTIVE%2CSTALLED");
  });

  it("replaces rather than accumulates on a single-value parameter", async () => {
    get.mockResolvedValue({
      data: {
        total: 9,
        counters: [
          { param: "role", value: "CASE_MANAGER", label: "Case manager", count: 5 },
          { param: "role", value: "SUPERVISOR", label: "Supervisor", count: 4 },
        ],
      },
    });
    renderDashboard();
    await userEvent.click(await screen.findByText("Case manager"));
    await userEvent.click(screen.getByText("Supervisor"));
    expect(screen.getByTestId("query")).toHaveTextContent("role=SUPERVISOR");
    expect(screen.getByTestId("query")).not.toHaveTextContent("CASE_MANAGER");
  });

  it("keeps a zero-count chip clickable, at reduced emphasis", async () => {
    renderDashboard();
    const placed = await screen.findByRole("button", { name: /Placed/ });
    expect(placed).toHaveAttribute("data-empty", "true");
    expect(placed).not.toBeDisabled();

    // "No youth placed" is a finding, and a filter that demonstrates it is
    // worth being able to click.
    await userEvent.click(placed);
    expect(screen.getByTestId("query")).toHaveTextContent("case_status__in=PLACED");
  });

  it("paints a selected chip with a whole tone, never a foreground alone", async () => {
    // The counter cards took `{ fg }` only and painted CASE_TONE.PLACED — white,
    // designed for a dark green chip — onto a white card, so the Placed count
    // was invisible while the other four showed.
    renderDashboard({ tones: { PLACED: { fg: "#ffffff", bg: "rgb(28, 122, 91)" } } });
    const placed = await screen.findByRole("button", { name: /Placed/ });
    await userEvent.click(placed);
    expect(placed).toHaveStyle({ backgroundColor: "rgb(28, 122, 91)" });
  });

  it("reports the total upward so a page subtitle can state it", async () => {
    const onTotal = vi.fn();
    renderDashboard({ onTotal });
    await waitFor(() => expect(onTotal).toHaveBeenCalledWith(14));
  });
});
