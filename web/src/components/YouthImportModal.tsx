import { App, Alert, Modal } from "antd";
import { useRef, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { YouthImportReport, YouthImportRow } from "../api/types";
import type { ImportOutcome } from "../design/status";
import { useLang } from "../i18n/LanguageContext";
import type { StringKey } from "../i18n/strings";
import { Button, CapsLabel, ImportOutcomeChip, MutedChip } from "./ui";

/** Spelled out rather than built from the code, so a missing string is a type error. */
const OUTCOME_LABEL: Record<ImportOutcome, StringKey> = {
  new: "import.outcome.new",
  duplicate: "import.outcome.duplicate",
  error: "import.outcome.error",
};

/**
 * Bulk youth intake from a woreda register — spec §4.1.
 *
 * Two steps, because this writes personal records in bulk: the file is uploaded
 * once to be checked and once to be saved, and the user approves the report in
 * between. The API validates the whole file before writing any of it, so the
 * preview the user approves is the report the save produces.
 *
 * Rows already on file are skipped rather than refused — registers get re-sent
 * with more names appended, and that has to be safe to upload.
 */

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

const IMPORT_URL = "/youth/import/";

export default function YouthImportModal({ open, onClose, onImported }: Props) {
  const { message } = App.useApp();
  const { t } = useLang();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<YouthImportReport | null>(null);
  const [busy, setBusy] = useState<"checking" | "saving" | null>(null);

  function reset() {
    setFile(null);
    setReport(null);
    setBusy(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  function close() {
    reset();
    onClose();
  }

  async function send(chosen: File, commit: boolean) {
    const body = new FormData();
    body.append("file", chosen);
    const response = await api.post<YouthImportReport>(`${IMPORT_URL}${commit ? "?commit=true" : ""}`, body);
    return response.data;
  }

  /** Step one: upload to be checked. Nothing is written. */
  async function check(chosen: File) {
    setFile(chosen);
    setReport(null);
    setBusy("checking");
    try {
      setReport(await send(chosen, false));
    } catch (error) {
      // A file the server cannot open at all comes back as a 400 detail rather
      // than a report — a missing column, the wrong sheet, or not a workbook.
      message.error(errorMessage(error, "The file could not be read."));
      reset();
    } finally {
      setBusy(null);
    }
  }

  /** Step two: the same file again, with the write. */
  async function commit() {
    if (!file) return;
    setBusy("saving");
    try {
      const saved = await send(file, true);
      const written = saved.counts.new;
      message.success(written ? t("import.done", { count: written }) : t("import.doneNone"));
      if (saved.counts.duplicate) message.info(t("import.skipped", { count: saved.counts.duplicate }), 6);

      // §11 leaves the youth age band unconfirmed, so an out-of-band row is
      // written and flagged rather than blocked. Surface the flag, or nobody
      // learns it was raised.
      const flagged = saved.rows.filter((row) => row.warning).length;
      if (flagged) message.warning(t("import.checkAge", { count: flagged }), 8);

      onImported();
      close();
    } catch (error) {
      message.error(errorMessage(error, "The import could not be saved."));
      setBusy(null);
    }
  }

  async function downloadTemplate() {
    try {
      const response = await api.get(`${IMPORT_URL}template/`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "youth-register-template.xlsx";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(errorMessage(error, "Could not download the template."));
    }
  }

  const counts = report?.counts;
  const blocked = Boolean(counts?.error);
  const importable = counts?.new ?? 0;

  return (
    <Modal
      open={open}
      title={t("import.title")}
      onCancel={close}
      width={720}
      destroyOnHidden
      footer={
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <Button onClick={close} disabled={busy === "saving"}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            disabled={!report || blocked || importable === 0 || busy !== null}
            blocked={blocked}
            onClick={() => void commit()}
          >
            {busy === "saving" ? t("import.saving") : t("import.commit", { count: importable })}
          </Button>
        </div>
      }
    >
      <p className="t-meta" style={{ marginTop: 0 }}>
        {t("import.intro")}
      </p>

      <Alert type="info" showIcon style={{ marginBottom: 12 }} title={t("import.consentNote")} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {/* A native input, not an antd Upload: the file dialog is the whole of
            the behaviour, and this keeps the button on the token layer. */}
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          style={{ display: "none" }}
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            if (chosen) void check(chosen);
          }}
        />
        <Button onClick={() => fileInput.current?.click()} disabled={busy !== null}>
          {file ? t("import.change") : t("import.choose")}
        </Button>
        <Button onClick={() => void downloadTemplate()}>{t("import.template")}</Button>
        {file && <span className="t-meta">{file.name}</span>}
      </div>

      <div className="t-meta" style={{ marginTop: 6 }}>
        {t("import.templateHint")}
      </div>

      {busy === "checking" && (
        <div className="t-meta" style={{ marginTop: 12 }}>
          {t("import.checking")}
        </div>
      )}

      {report && counts && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <ImportOutcomeChip outcome="new" label={t("import.countNew", { count: counts.new })} />
            {counts.duplicate > 0 && (
              <ImportOutcomeChip
                outcome="duplicate"
                label={t("import.countDuplicate", { count: counts.duplicate })}
              />
            )}
            {counts.error > 0 && (
              <ImportOutcomeChip outcome="error" label={t("import.countError", { count: counts.error })} />
            )}
          </div>

          {blocked && (
            <Alert type="error" showIcon style={{ marginTop: 12 }} title={t("import.blocked")} />
          )}
          {!blocked && importable === 0 && (
            <Alert type="warning" showIcon style={{ marginTop: 12 }} title={t("import.allDuplicates")} />
          )}

          <RowList rows={report.rows} />
        </div>
      )}
    </Modal>
  );
}

/**
 * The rows worth reading — the problems and the skips.
 *
 * A file of four hundred good rows has nothing to show but its count, and
 * listing them would bury the eight that need fixing. Rendered as a stack at
 * every width rather than a table that becomes cards at 780px: this sits inside
 * a modal, which is already narrow on a laptop.
 */
function RowList({ rows }: { rows: YouthImportRow[] }) {
  const { t } = useLang();
  const notable = rows.filter((row) => row.status !== "new");
  if (notable.length === 0) return null;

  return (
    <div style={{ marginTop: 12, maxHeight: 320, overflowY: "auto" }}>
      <CapsLabel>{t("import.title")}</CapsLabel>
      <div className="stack" style={{ marginTop: 6, gap: 6 }}>
        {notable.map((row) => (
          <div
            key={row.row}
            style={{
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
              flexWrap: "wrap",
              padding: "8px 10px",
              borderRadius: "var(--r-group)",
              background: "var(--fill-muted)",
            }}
          >
            <MutedChip>{t("import.row", { row: row.row })}</MutedChip>
            <span className="t-body-strong" style={{ flex: "1 1 140px" }}>
              {row.full_name || t("import.unnamed")}
            </span>
            <ImportOutcomeChip outcome={row.status} label={t(OUTCOME_LABEL[row.status])} />
            {row.status === "error" && (
              <ul style={{ flexBasis: "100%", margin: "2px 0 0", paddingLeft: 18, color: "var(--red-700)" }}>
                {Object.entries(row.errors).map(([field, messages]) => (
                  <li key={field} style={{ fontSize: 13 }}>
                    {messages.join(" ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
