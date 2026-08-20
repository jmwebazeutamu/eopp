import { App } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
  resolution_status: "OPEN",
  status_display: "Open",
  resolution_date: null,
  resolution_notes: "",
  referral_quality_feedback_flag: false,
  days_open: 5,
  is_open: true,
  is_sensitive: false,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/grievances"]}>
      <LanguageProvider>
        <TestAuth>
          <App>
            <GrievancesPage />
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
    if (url === "/grievances/overdue/") return Promise.resolve({ data: { threshold_days: 3, results: [GRIEVANCE] } });
    if (url === "/grievances/summary/") return Promise.resolve({ data: { total: 1, counters: [] } });
    return Promise.reject(new Error(`Unhandled GET ${url}`));
  });
});

describe("GrievancesPage", () => {
  it("opens a grievance detail modal from the list", async () => {
    renderPage();

    await userEvent.click((await screen.findAllByText("Quality of the service received"))[0]);

    expect(await screen.findByText("Assigned to")).toBeInTheDocument();
    expect(screen.getByDisplayValue("The support visit was promised but nobody came.")).toBeInTheDocument();
    expect(screen.getByText("Supervisor One")).toBeInTheDocument();
  });

  it("closes a grievance from the detail modal", async () => {
    post.mockResolvedValue({
      data: {
        ...GRIEVANCE,
        resolution_status: "CLOSED",
        status_display: "Closed without resolution",
        resolution_notes: "The complainant withdrew the report.",
        resolution_date: "2026-08-20",
        is_open: false,
      },
    });

    renderPage();

    await userEvent.click((await screen.findAllByText("Quality of the service received"))[0]);
    await userEvent.type(screen.getByLabelText("Action notes"), "The complainant withdrew the report.");
    await userEvent.click(screen.getByRole("button", { name: "Close the file" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/grievances/g-1/close/", { reason: "The complainant withdrew the report." }),
    );
  });
});
