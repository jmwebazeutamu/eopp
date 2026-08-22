import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ServiceLinkage } from "../../api/types";
import LinkageTimeline from "./LinkageTimeline";

function linkage(overrides: Partial<ServiceLinkage>): ServiceLinkage {
  return {
    id: "linkage-1",
    linkage_type: "savings_account",
    type_label: "Group savings account",
    provider: "provider-1",
    provider_name: "Amhara Rural Bank",
    predecessor: null,
    predecessor_label: null,
    subject_group: "group-1",
    subject_cla: null,
    subject_federation: null,
    subject_type: "GROUP",
    subject_name: "Adey SHG 0123",
    status: "ACTIVE",
    status_display: "Active",
    opened_on: "2026-08-18",
    approved_on: null,
    activated_on: "2026-08-18",
    closed_on: null,
    value_etb: null,
    terms: {},
    guarantors: [],
    block_reasons: [],
    next_approval_role: null,
    next_action_role_display: null,
    can_current_user_approve: false,
    ...overrides,
  };
}

describe("LinkageTimeline", () => {
  it("renders dates, overlapping lanes, unknown status, an empty lane, and undated records", () => {
    const records = [
      linkage({ id: "active", opened_on: "2026-08-18" }),
      linkage({
        id: "unknown",
        type_label: "Market or offtake agreement",
        opened_on: "2026-08-19",
        status: "FUTURE_STATUS" as ServiceLinkage["status"],
        status_display: "Future status",
        predecessor: "active",
      }),
      linkage({ id: "undated", opened_on: null as unknown as string }),
    ];

    render(
      <LinkageTimeline linkages={records} today={new Date(2026, 7, 21)} />,
    );

    expect(screen.getByText("18 Aug")).toBeInTheDocument();
    expect(screen.getByText("19 Aug")).toBeInTheDocument();
    expect(
      screen.getByText(/Group savings account · Amhara Rural Bank/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Market or offtake agreement · Amhara Rural Bank/),
    ).toBeInTheDocument();
    expect(screen.getByText("? Future status")).toBeInTheDocument();
    expect(screen.getByText("Never used")).toBeInTheDocument();
    expect(screen.getByTestId("onward-unknown")).toBeInTheDocument();
    expect(screen.getByTestId("undated-linkages")).toHaveTextContent(
      "1 linkage not shown",
    );

    const first = screen
      .getByTestId("linkage-marker-active")
      .querySelector("rect");
    const second = screen
      .getByTestId("linkage-marker-unknown")
      .querySelector("rect");
    expect(first?.getAttribute("y")).not.toBe(second?.getAttribute("y"));
  });
});
