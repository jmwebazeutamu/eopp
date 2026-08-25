import { App } from "antd";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Grievance } from "../api/types";
import { LanguageProvider } from "../i18n/LanguageContext";
import { TestAuth } from "../test/authHarness";

const get = vi.fn();
const patch = vi.fn();
const post = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    patch: (...args: unknown[]) => patch(...args),
    post: (...args: unknown[]) => post(...args),
  },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: GrievancesPage } = await import("./GrievancesPage");

const GRIEVANCE: Grievance = {
  id: "g-1",
  case: "case-1",
  youth_name: "Alem Tadesse",
  related_referral: null,
  about_partner: null,
  partner_name: null,
  woreda: "Adama",
  complaint_type: "SERVICE_QUALITY",
  complaint_type_display: "Quality of the service received",
  raised_by: "YOUTH",
  raised_by_display: "Youth",
  complainant_name: "Alem Tadesse",
  complainant_contact: "+251911000111",
  summary: "The support visit was promised but nobody came.",
  date_raised: "2026-08-15",
  assigned_staff: "staff-1",
  assigned_staff_name: "Supervisor One",
  status: "RECEIVED",
  status_display: "Open",
  resolution_date: null,
  resolution_notes: "",
  referral_quality_feedback_flag: false,
  days_open: 5,
  is_open: true,
  is_sensitive: false,
  severity: "ROUTINE" as const,
  tier: "KEBELE" as const,
  tier_display: "Kebele Appeals Committee",
  outcome: "" as const,
  outcome_display: "",
  outcome_reason: "",
  parent_grievance: null,
  appeal_ground: "",
  pause_reason: "",
  chase_date: null,
  feedback_given_at: null,
  feedback_method: "",
  complainant_satisfied: null,
  referred_to: "",
  severity_display: "Routine",
  can_act: true,
  due_on: "2026-09-01",
  standing: { state: "on_time" as const, days: 5, due_on: "2026-09-01" },
  acknowledged_at: null,
  acknowledgement_method: "",
  short_reference: "A1B2C3D4",
  is_restricted: false,
  restricted: false,
  subject_type: "CASE" as const,
  subject_label: "Sisay Roba",
  subject_youth: null,
  person_name: null,
  subject_group: null,
  group_name: null,
};

/** Reports where the router ended up, so a navigation can be asserted without
 *  mounting the destination page. */
function Location() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/grievances"]}>
      <LanguageProvider>
        <TestAuth>
          <App>
            <GrievancesPage />
            <Location />
          </App>
        </TestAuth>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
  post.mockReset();

  get.mockImplementation((url: string) => {
    if (url === "/grievances/") return Promise.resolve({ data: { count: 1, results: [GRIEVANCE] } });
    if (url === "/grievances/queue-counts/")
      return Promise.resolve({ data: { late: 0, due_this_week: 1, awaiting_acknowledgement: 1, restricted: 0 } });
    if (url === "/grievances/summary/") return Promise.resolve({ data: { total: 1, counters: [] } });
    return Promise.reject(new Error(`Unhandled GET ${url}`));
  });
});

describe("GrievancesPage", () => {
  it("sends the reader to the case file, not to a modal", async () => {
    // A grievance is worked over weeks by several people. A modal cannot be
    // linked to, cannot be printed for a committee, and has nowhere to put a
    // timeline.
    renderPage();

    await userEvent.click((await screen.findAllByText("Quality of the service received"))[0]);

    expect(await screen.findByTestId("location")).toHaveTextContent("/grievances/g-1");
  });

  it("leads the queue with what needs somebody today", async () => {
    // The banner it replaces said only how many were overdue, which answers
    // half the question a queue is opened with.
    renderPage();

    expect(await screen.findByText("awaiting acknowledgement")).toBeInTheDocument();
    expect(screen.getByText("due this week")).toBeInTheDocument();
  });

  it("says time remaining rather than age", async () => {
    // The Age column counted from creation and kept counting after resolution,
    // so a concluded row read "30 day(s) open".
    renderPage();

    expect(await screen.findAllByText("Due in 5 day(s)")).toHaveLength(2);
    expect(screen.queryByText(/day\(s\) open/)).not.toBeInTheDocument();
  });
});

describe("the safeguarding lane", () => {
  it("shows a restricted row's shape and nothing else", async () => {
    // Redacted, not omitted. A disclosure that vanishes from every list is one
    // nobody can be held to, and nothing counts it. The server sends no
    // `summary` at all for these rows, which is why it is absent here rather
    // than blank.
    const restricted = {
      ...GRIEVANCE,
      id: "g-2",
      restricted: true,
      is_restricted: true,
      short_reference: "7F2C91AA",
      complaint_type: "SAFEGUARDING",
      complaint_type_display: "Safeguarding or harassment",
      summary: "",
      complainant_name: "",
    };
    get.mockImplementation((url: string) => {
      if (url === "/grievances/") return Promise.resolve({ data: { count: 1, results: [restricted] } });
      if (url === "/grievances/queue-counts/")
        return Promise.resolve({ data: { late: 0, due_this_week: 0, awaiting_acknowledgement: 1, restricted: 1 } });
      if (url === "/grievances/summary/") return Promise.resolve({ data: { total: 1, counters: [] } });
      return Promise.reject(new Error(`Unhandled GET ${url}`));
    });

    renderPage();

    expect(await screen.findAllByText("7F2C91AA")).toHaveLength(2);
    expect(screen.getAllByText(/safeguarding focal point only/i).length).toBeGreaterThan(0);
    // Nothing that could identify a survivor or describe what happened.
    expect(screen.queryByText(GRIEVANCE.summary)).not.toBeInTheDocument();
    expect(screen.queryByText("Alem Tadesse")).not.toBeInTheDocument();
    // The lead has to see that a disclosure has been sitting for weeks without
    // reading it, so the age survives redaction. It rendered "undefined day(s)
    // open" while it did not.
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
    // Two, not one: the phone card and the table row must say the same thing.
    // The card used to print the category and the summary while the table beside
    // it showed a reference, so a narrow screen leaked what a wide one did not.
  });
});
