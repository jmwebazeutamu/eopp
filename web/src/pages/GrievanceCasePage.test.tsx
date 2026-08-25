import { App } from "antd";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Grievance, GrievanceEvent } from "../api/types";
import { LanguageProvider } from "../i18n/LanguageContext";
import { TestAuth } from "../test/authHarness";

/**
 * The case file.
 *
 * What is worth asserting is not the layout but the two things the page exists
 * for: the statement is the first entry and is not editable, and the
 * acknowledgement step states its own absence rather than leaving a blank
 * somebody has to notice.
 */

const get = vi.fn();
const post = vi.fn();
vi.mock("../api/client", () => ({
  api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: GrievanceCasePage } = await import("./GrievanceCasePage");

const GRIEVANCE = {
  id: "g-1",
  short_reference: "A1B2C3D4",
  complaint_type_display: "Payment, stipend or grant",
  status: "RECEIVED",
  status_display: "Open",
  is_open: true,
  restricted: false,
  is_restricted: false,
  severity: "SERIOUS",
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
  severity_display: "Serious",
  can_act: true,
  due_on: "2026-09-01",
  standing: { state: "late", days: -3, due_on: "2026-09-01" },
  acknowledged_at: null,
  acknowledgement_method: "",
  woreda: "Lume",
  complainant_name: "Sisay Roba",
  subject_label: "Sisay Roba",
  date_raised: "2026-08-18",
  assigned_staff_name: "Supervisor One",
  summary: "The transport stipend has not been paid for two months.",
} as unknown as Grievance;

const EVENTS: GrievanceEvent[] = [
  {
    at: "2026-08-18",
    type: "STATEMENT",
    title: "Complaint received",
    body: "The transport stipend has not been paid for two months.",
    actor: "Outreach Worker One",
  },
  { at: "2026-08-22", type: "NOTE", title: "Note", body: "Payment roll checked.", actor: "Supervisor One" },
];

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/grievances/g-1"]}>
      <LanguageProvider>
        <TestAuth>
          <App>
            <Routes>
              <Route path="/grievances/:grievanceId" element={<GrievanceCasePage />} />
            </Routes>
          </App>
        </TestAuth>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  post.mockResolvedValue({ data: {} });
  get.mockImplementation((url: string) => {
    if (url === "/grievances/g-1/") return Promise.resolve({ data: GRIEVANCE });
    if (url === "/grievances/g-1/timeline/") return Promise.resolve({ data: { events: EVENTS } });
    return Promise.reject(new Error(`Unhandled GET ${url}`));
  });
});

describe("GrievanceCasePage", () => {
  it("puts the complainant's own words first, and says they are not editable", async () => {
    // A grievance record is evidence. The statement is the one thing on it that
    // nobody may improve; corrections are appended below.
    renderPage();

    const entries = await screen.findAllByRole("listitem");
    expect(entries[0]).toHaveTextContent("Complaint received");
    expect(entries[0]).toHaveTextContent("The transport stipend has not been paid for two months.");
    expect(entries[0]).toHaveTextContent(/not editable/i);
    // Not an input anywhere on the page.
    expect(screen.queryByDisplayValue(GRIEVANCE.summary)).not.toBeInTheDocument();
  });

  it("states that nobody has told the complainant it arrived", async () => {
    // The step most likely to be skipped and the one auditors check. Its
    // absence is a sentence, not a blank field somebody has to notice.
    renderPage();

    expect(await screen.findByText(/has not been told this arrived/i)).toBeInTheDocument();
  });

  it("says how late it is, in the module's own colour vocabulary", async () => {
    renderPage();
    expect(await screen.findByText("3 day(s) late")).toBeInTheDocument();
  });

  it("will not record an acknowledgement without saying how", async () => {
    // "Acknowledged" with no record of how is a tick somebody applies from a
    // desk, and the field exists to describe something that happened.
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Record acknowledgement" }));
    const save = await screen.findByRole("button", { name: /save/i });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/how they were told/i), "By phone");
    expect(save).toBeEnabled();
  });

  it("shows the shape of a restricted record and refuses its contents", async () => {
    get.mockImplementation((url: string) => {
      if (url === "/grievances/g-1/")
        return Promise.resolve({ data: { ...GRIEVANCE, restricted: true, is_restricted: true } });
      if (url === "/grievances/g-1/timeline/") return Promise.reject(new Error("403"));
      return Promise.reject(new Error(`Unhandled GET ${url}`));
    });

    renderPage();

    expect(await screen.findByText(/named safeguarding focal point/i)).toBeInTheDocument();
    expect(screen.queryByText(GRIEVANCE.summary)).not.toBeInTheDocument();
  });

  it("offers only the moves this state allows", async () => {
    // The workflow, as buttons. A screen that offered Close on a case nobody
    // has decided would be describing an edge the server does not have.
    renderPage();

    expect(await screen.findByRole("button", { name: "Record acknowledgement" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record the decision" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /close/i })).not.toBeInTheDocument();
  });

  it("will not shut the file until the complainant has been told the outcome", async () => {
    // The gate the whole rebuild turns on. It was possible to close a case
    // having told nobody anything.
    get.mockImplementation((url: string) => {
      if (url === "/grievances/g-1/")
        return Promise.resolve({ data: { ...GRIEVANCE, status: "DECIDED", outcome: "NOT_UPHELD" } });
      if (url === "/grievances/g-1/timeline/") return Promise.resolve({ data: { events: EVENTS } });
      return Promise.reject(new Error(`Unhandled GET ${url}`));
    });

    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Tell the complainant and close" }));
    const save = await screen.findByRole("button", { name: /save/i });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/how they were told the outcome/i), "In person at the kebele desk");
    expect(save).toBeEnabled();
  });

  it("offers an appeal only from a closed case", async () => {
    get.mockImplementation((url: string) => {
      if (url === "/grievances/g-1/")
        return Promise.resolve({ data: { ...GRIEVANCE, status: "CLOSED", is_open: false } });
      if (url === "/grievances/g-1/timeline/") return Promise.resolve({ data: { events: EVENTS } });
      return Promise.reject(new Error(`Unhandled GET ${url}`));
    });

    renderPage();

    expect(await screen.findByRole("button", { name: "Lodge an appeal" })).toBeInTheDocument();
  });
});
