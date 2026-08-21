import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { TestAuth, testUser } from "../../test/authHarness";

const get = vi.fn();
vi.mock("../../api/client", () => ({ api: { get: (...args: unknown[]) => get(...args), post: vi.fn() }, errorMessage: (_: unknown, fallback: string) => fallback }));
const { default: LinkagesPage } = await import("./LinkagesPage");

const linkage = {
  id: "l1", linkage_type: "savings_account", type_label: "Savings account", provider: "p1", provider_name: "Afar Bank",
  subject_type: "GROUP", subject_name: "Hidase SHG", status: "SCREENED", status_display: "Screened", opened_on: "2026-08-20",
  approved_on: null, activated_on: null, closed_on: null, value_etb: null, terms: {}, guarantors: [], block_reasons: [],
};

function mount(role: "WLT_FACILITATOR" | "WLT_WOREDA_OFFICER" | "SYSTEM_ADMIN" = "WLT_FACILITATOR") {
  get.mockImplementation((url?: string) => {
    if (!url) return Promise.resolve({ data: { count: 0, results: [] } });
    if (url.endsWith("summary/")) return Promise.resolve({ data: { total: 1, counters: [] } });
    if (url.endsWith("events/")) return Promise.resolve({ data: [{ id: "e1", from_status: "PROPOSED", to_status: "SCREENED", occurred_at: "2026-08-20T10:00:00Z", actor: "u1", actor_name: "Sara", reason: "", gate_snapshot: null }] });
    return Promise.resolve({ data: { count: 1, results: [linkage] } });
  });
  return render(<TestAuth user={testUser(role, { access: { case_scope: "NONE", case_write: false, referral_scope: "NONE", referral_write: false, group_scope: "OWN_GROUPS", group_write: true, delivery_write: false } })}><LanguageProvider><App><MemoryRouter><LinkagesPage /></MemoryRouter></App></LanguageProvider></TestAuth>);
}

describe("LinkagesPage", () => {
  beforeEach(() => get.mockReset());

  it("gives a facilitator the resolution step before submission and shows evidence", async () => {
    mount();
    fireEvent.click(await screen.findByText("Savings account"));
    expect(await screen.findByText("Record group resolution")).toBeInTheDocument();
    expect(screen.getByText("Submit for approval")).toBeInTheDocument();
    expect(await screen.findByText("PROPOSED → SCREENED")).toBeInTheDocument();
  });

  it("does not expose facilitator actions to an approver", async () => {
    mount("WLT_WOREDA_OFFICER");
    fireEvent.click(await screen.findByText("Savings account"));
    await waitFor(() => expect(screen.getByText("Evidence timeline")).toBeInTheDocument());
    expect(screen.queryByText("Submit for approval")).not.toBeInTheDocument();
  });

  it("gives a system administrator the WLT operational actions", async () => {
    mount("SYSTEM_ADMIN");
    expect(await screen.findByText("Propose linkage")).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Savings account"));
    expect(await screen.findByText("Record group resolution")).toBeInTheDocument();
    expect(screen.getByText("Submit for approval")).toBeInTheDocument();
  });
});
