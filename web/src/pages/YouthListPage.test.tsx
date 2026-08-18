import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Youth } from "../api/types";
import { ScopeProvider } from "../components/shell/ScopeContext";
import { LanguageProvider } from "../i18n/LanguageContext";

/**
 * The registry's two selection rules.
 *
 * Note on the queries: vitest applies no stylesheet, so the laptop table and
 * the phone cards both render here and every row matches twice. The tests take
 * the first match rather than asserting a single one.
 *
 *  - the case pill opens the *case*, not the youth record — it says "Open case"
 *    and used to open an edit form, which is the fault this pins down;
 *  - selecting a youth shows the record read-only, and editing is a deliberate
 *    step inside it rather than where every click lands.
 */

const get = vi.fn();
vi.mock("../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const YOUTH: Youth = {
  id: "y1",
  full_name: "Abebe Kebele",
  sex: "MALE",
  sex_display: "Male",
  date_of_birth: "2002-01-01",
  age: 24,
  phone_number: "+251911452207",
  woreda: "Adama",
  kebele: "Adama 01",
  national_or_kebele_id: "YE-004821",
  region: "Oromia",
  zone: "East Shewa",
  household_id: "",
  psnp_status: "NOT_PSNP",
  education_level: "SECONDARY_COMPLETE",
  disability_status: "NONE",
  consent_given: true,
  consent_date: "2026-01-14",
  has_open_case: true,
  open_case_id: "case-7",
  registration_date: "2026-01-14",
  registering_worker: "u1",
  registering_worker_name: "Outreach One",
  is_age_eligible: true,
};

function renderRegistry() {
  get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === "/youth/summary/") return Promise.resolve({ data: { total: 1, counters: [] } });
    if (config?.params?.without_case) return Promise.resolve({ data: { count: 0, results: [] } });
    return Promise.resolve({ data: { count: 1, results: [YOUTH] } });
  });

  return render(
    <MemoryRouter initialEntries={["/youth"]}>
      <LanguageProvider>
        <ScopeProvider user={null}>
        <Routes>
          <Route path="/youth" element={<YouthListPageWithAuth />} />
          <Route path="/cases/:caseId" element={<div>CASE SCREEN</div>} />
        </Routes>
        </ScopeProvider>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

/** The page reads the signed-in user for its write permission. */
function YouthListPageWithAuth() {
  return <Page />;
}

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { access: { case_write: true, case_scope: "OWN_WOREDA" }, full_name: "Tester" } }),
}));

vi.mock("../components/YouthFormModal", () => ({
  default: ({ open }: { open: boolean }) => (open ? <div>EDIT FORM</div> : null),
}));

const { default: Page } = await import("./YouthListPage");

describe("YouthListPage", () => {
  it("opens the case, not the youth record, from the case pill", async () => {
    renderRegistry();
    const pills = await screen.findAllByTitle("Open case");

    await userEvent.click(pills[0]);

    expect(screen.getByText("CASE SCREEN")).toBeInTheDocument();
    expect(screen.queryByText("EDIT FORM")).not.toBeInTheDocument();
  });

  it("shows a selected youth read-only, with edit as a separate step", async () => {
    renderRegistry();
    await userEvent.click((await screen.findAllByText("Abebe Kebele"))[0]);

    // The record, not a form.
    expect(screen.getByText("Consent recorded 2026-01-14")).toBeInTheDocument();
    expect(screen.queryByText("EDIT FORM")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Edit record"));
    expect(screen.getByText("EDIT FORM")).toBeInTheDocument();
  });

  it("keeps the phone masked in the record, behind a deliberate reveal", async () => {
    renderRegistry();
    await userEvent.click((await screen.findAllByText("Abebe Kebele"))[0]);

    expect(screen.getAllByText("+251 9•• •• 22 07").length).toBeGreaterThan(0);
    expect(screen.queryByText("+251911452207")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Reveal"));
    expect(screen.getByText("+251911452207")).toBeInTheDocument();
  });
});
