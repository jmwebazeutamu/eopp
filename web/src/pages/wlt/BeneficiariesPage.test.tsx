import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { TestAuth, testUser } from "../../test/authHarness";

const get = vi.fn();
vi.mock("../../api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

vi.mock("./RegisterWomanModal", () => ({ default: () => null }));
vi.mock("./ImportExtractModal", () => ({ default: () => null }));

const { default: BeneficiariesPage } = await import("./BeneficiariesPage");

function mount(entry = "/wlt/beneficiaries?page=2") {
  get.mockImplementation((url?: string) => {
    if (url?.endsWith("summary/")) {
      return Promise.resolve({
        data: { total: 60, counters: [{ value: "VERIFIED", label: "Verified", count: 38 }] },
      });
    }
    return Promise.resolve({
      data: {
        count: 60,
        results: [{
          id: "b1", full_name: "Aster Bekele", psnp_client_id: "PSNP-1", enrolment_route: "IMPORT",
          verification_status: "VERIFIED", is_programme_eligible: true,
        }],
      },
    });
  });

  return render(
    <TestAuth user={testUser("WLT_WOREDA_OFFICER")}>
      <LanguageProvider>
        <App>
          <MemoryRouter initialEntries={[entry]}>
            <BeneficiariesPage />
          </MemoryRouter>
        </App>
      </LanguageProvider>
    </TestAuth>,
  );
}

describe("BeneficiariesPage", () => {
  beforeEach(() => get.mockReset());

  it("requests one server-side page and keeps search-compatible URL filters", async () => {
    mount();

    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        "/wlt/profiles/",
        expect.objectContaining({ params: expect.objectContaining({ page: 2, page_size: 25 }) }),
      ),
    );
    expect(await screen.findByText("26–50 of 60")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Enrolment route"), { target: { value: "FACILITATOR" } });
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        "/wlt/profiles/",
        expect.objectContaining({
          params: expect.objectContaining({ page: 1, enrolment_route: "FACILITATOR" }),
        }),
      ),
    );
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });
});
