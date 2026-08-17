import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { YouthImportReport } from "../api/types";
import { LanguageProvider } from "../i18n/LanguageContext";

/**
 * The rule this screen exists to hold: a bulk write of personal records is
 * previewed and approved before anything is saved.
 *
 * So the tests are about what the two uploads are, and when the save is
 * refused — not about how the report looks.
 */

const post = vi.fn();
const get = vi.fn();
vi.mock("../api/client", () => ({
  api: {
    post: (...args: unknown[]) => post(...args),
    get: (...args: unknown[]) => get(...args),
  },
  errorMessage: (_: unknown, fallback: string) => fallback,
}));

const { default: YouthImportModal } = await import("./YouthImportModal");

function report(overrides: Partial<YouthImportReport> = {}): YouthImportReport {
  return {
    committed: false,
    counts: { total: 2, new: 2, duplicate: 0, error: 0 },
    rows: [
      { row: 2, status: "new", full_name: "Almaz Tesfaye", errors: {}, warning: "", duplicate_of: null },
      { row: 3, status: "new", full_name: "Bekele Dinku", errors: {}, warning: "", duplicate_of: null },
    ],
    ...overrides,
  };
}

const onImported = vi.fn();

function renderModal() {
  return render(
    <LanguageProvider>
      <App>
        <YouthImportModal open onClose={() => {}} onImported={onImported} />
      </App>
    </LanguageProvider>,
  );
}

/** The input is hidden behind a token-styled button, so drive it directly. */
function chooseFile(name = "register.xlsx") {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], name)] } });
}

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  onImported.mockReset();
});

describe("YouthImportModal", () => {
  it("checks the file without saving it", async () => {
    post.mockResolvedValue({ data: report() });
    renderModal();
    chooseFile();

    await screen.findByText("2 to import");
    expect(post).toHaveBeenCalledTimes(1);
    // No `commit`: the first upload is a dry run, whatever the file contains.
    expect(post.mock.calls[0][0]).toBe("/youth/import/");
    expect(onImported).not.toHaveBeenCalled();
  });

  it("sends the same file again with the commit only once confirmed", async () => {
    post.mockResolvedValue({ data: report() });
    renderModal();
    chooseFile();

    await userEvent.click(await screen.findByText("Import 2 youth"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][0]).toBe("/youth/import/?commit=true");
    expect(onImported).toHaveBeenCalled();
  });

  it("refuses the save while any row is in error, and says nothing was written", async () => {
    post.mockResolvedValue({
      data: report({
        counts: { total: 2, new: 1, duplicate: 0, error: 1 },
        rows: [
          { row: 2, status: "new", full_name: "Almaz Tesfaye", errors: {}, warning: "", duplicate_of: null },
          {
            row: 3,
            status: "error",
            full_name: "Bekele Dinku",
            errors: { consent_given: ["A youth cannot be registered without recorded consent."] },
            warning: "",
            duplicate_of: null,
          },
        ],
      }),
    });
    renderModal();
    chooseFile();

    // The failing row is named by its sheet row number, so it can be found in Excel.
    expect(await screen.findByText("Row 3")).toBeInTheDocument();
    expect(screen.getByText(/without recorded consent/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been saved/)).toBeInTheDocument();

    const confirm = screen.getByText("Import 1 youth").closest("button");
    expect(confirm).toBeDisabled();

    await userEvent.click(confirm!);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("has nothing to do when every row is already on file", async () => {
    post.mockResolvedValue({
      data: report({
        counts: { total: 1, new: 0, duplicate: 1, error: 0 },
        rows: [
          { row: 2, status: "duplicate", full_name: "Almaz Tesfaye", errors: {}, warning: "", duplicate_of: "y1" },
        ],
      }),
    });
    renderModal();
    chooseFile();

    expect(await screen.findByText(/Every row is already on file/)).toBeInTheDocument();
    expect(screen.getByText("Import 0 youth").closest("button")).toBeDisabled();
  });

  it("lists the skipped rows but not the four hundred good ones", async () => {
    post.mockResolvedValue({
      data: report({
        counts: { total: 3, new: 2, duplicate: 1, error: 0 },
        rows: [
          { row: 2, status: "new", full_name: "Almaz Tesfaye", errors: {}, warning: "", duplicate_of: null },
          { row: 3, status: "new", full_name: "Bekele Dinku", errors: {}, warning: "", duplicate_of: null },
          { row: 4, status: "duplicate", full_name: "Chaltu Roba", errors: {}, warning: "", duplicate_of: "y9" },
        ],
      }),
    });
    renderModal();
    chooseFile();

    expect(await screen.findByText("Chaltu Roba")).toBeInTheDocument();
    expect(screen.queryByText("Almaz Tesfaye")).not.toBeInTheDocument();
  });

  it("clears the report when the file is swapped, so a stale preview cannot be approved", async () => {
    post.mockResolvedValueOnce({ data: report() });
    renderModal();
    chooseFile("first.xlsx");
    await screen.findByText("2 to import");

    post.mockImplementation(() => new Promise(() => {})); // second check never resolves
    chooseFile("second.xlsx");

    await waitFor(() => expect(screen.queryByText("2 to import")).not.toBeInTheDocument());
    expect(screen.getByText("Checking the file…")).toBeInTheDocument();
  });

  it("resets after a file the server cannot read", async () => {
    post.mockRejectedValue(new Error("bad file"));
    renderModal();
    chooseFile();

    await waitFor(() => expect(screen.queryByText("Checking the file…")).not.toBeInTheDocument());
    expect(screen.getByText("Choose a file")).toBeInTheDocument();
  });

  it("downloads the template as a blob rather than a link the browser cannot authenticate", async () => {
    URL.createObjectURL = vi.fn(() => "blob:t");
    URL.revokeObjectURL = vi.fn();
    get.mockResolvedValue({ data: new Blob(["x"]) });
    renderModal();

    await userEvent.click(screen.getByText("Download the template"));

    await waitFor(() => expect(get).toHaveBeenCalledWith("/youth/import/template/", { responseType: "blob" }));
  });
});
