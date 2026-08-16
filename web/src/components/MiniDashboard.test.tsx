import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MiniDashboard from "./MiniDashboard";

const get = vi.fn();
vi.mock("../api/client", () => ({ api: { get: (...args: unknown[]) => get(...args) } }));

const SUMMARY = {
  total: 14,
  counters: [
    { param: "case_status", value: "ACTIVE", label: "Active", count: 11 },
    { param: "case_status", value: "STALLED", label: "Stalled", count: 3 },
  ],
};

function Probe() {
  const [params] = useSearchParams();
  return <span data-testid="query">{params.toString()}</span>;
}

function renderDashboard(props = {}) {
  return render(
    <MemoryRouter>
      <MiniDashboard resource="/cases" {...props} />
      <Probe />
    </MemoryRouter>,
  );
}

describe("MiniDashboard", () => {
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
    expect(screen.getByTestId("query")).toHaveTextContent("case_status=STALLED");
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
        <MiniDashboard resource="/cases" />
        <Probe />
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
    await waitFor(() => expect(container.querySelector(".grid-counters")).toBeNull());
  });

  it("renders nothing when there is nothing to count", async () => {
    get.mockResolvedValue({ data: { total: 0, counters: [] } });
    const { container } = renderDashboard();
    await waitFor(() => expect(container.querySelector(".grid-counters")).toBeNull());
  });
});
