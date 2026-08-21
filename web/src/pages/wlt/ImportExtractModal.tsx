import { Alert, App, Form, Modal, Select, Upload } from "antd";
import { useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { Location, WltImportReport } from "../../api/types";
import { Button } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The PSNP ELS extract — decision D5's main route in.
 *
 * The report is the point of this screen, not the upload. Unlike the youth-side
 * register, an extract is **not all or nothing**: it is thousands of rows from a
 * system nobody here controls, and refusing the file because forty rows need a
 * woreda officer would mean importing nothing. So four outcomes come back and
 * all four are shown — registered, matched, queued for a person to confirm, and
 * already on file — plus rows whose cells could not be read at all.
 *
 * Those last two are kept apart deliberately. "We could not read this" and
 * "this needs a woreda officer" are different problems with different owners,
 * and folding them into one number would hide the second behind the first.
 */
export default function ImportExtractModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [form] = Form.useForm();
  const [kebeles, setKebeles] = useState<Location[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<WltImportReport | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await api.get<Location[]>("/locations/");
        if (!cancelled) setKebeles(response.data.filter((row) => row.level === "KEBELE"));
      } catch {
        if (!cancelled) setKebeles([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  function reset() {
    form.resetFields();
    setFile(null);
    setReport(null);
  }

  async function downloadTemplate() {
    try {
      const response = await api.get("/wlt/profiles/import-template/", { responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "psnp-els-extract-template.xlsx";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.importFailed")));
    }
  }

  const submit = async (values: { kebele: string }) => {
    if (!file) return;
    setSubmitting(true);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("kebele", values.kebele);
      const response = await api.post<WltImportReport>("/wlt/profiles/import/", body);
      setReport(response.data);
      onDone();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.importFailed")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("wlt.importTitle")}
      okText={t("wlt.importOk")}
      cancelText={t("common.cancel")}
      confirmLoading={submitting}
      okButtonProps={{ disabled: !file || report !== null }}
      onCancel={() => {
        reset();
        onClose();
      }}
      onOk={() => form.submit()}
      destroyOnHidden
      width={560}
    >
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t("wlt.importIntro")} />

      {report ? (
        <ImportReport report={report} />
      ) : (
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <div style={{ marginBottom: 16 }}>
            <Button onClick={downloadTemplate}>{t("wlt.importTemplate")}</Button>
          </div>
          <Form.Item name="kebele" label={t("wlt.kebele")} rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={kebeles.map((kebele) => ({ value: kebele.code, label: kebele.name }))}
            />
          </Form.Item>
          <Form.Item label={t("wlt.importFile")} required>
            <Upload
              beforeUpload={(selected) => {
                setFile(selected);
                return false; // never auto-upload; the form owns the request
              }}
              onRemove={() => setFile(null)}
              maxCount={1}
              accept=".xlsx"
            >
              <Button>Choose .xlsx file</Button>
            </Upload>
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function ImportReport({ report }: { report: WltImportReport }) {
  const { t } = useLang();
  const lines = [
    { key: "created", text: t("wlt.importCreated", { count: report.outcomes.created }) },
    { key: "linked", text: t("wlt.importLinked", { count: report.outcomes.linked }) },
    { key: "queued", text: t("wlt.importQueued", { count: report.outcomes.queued }) },
    { key: "skipped", text: t("wlt.importSkipped", { count: report.outcomes.skipped }) },
  ];
  return (
    <div className="stack">
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {lines.map((line) => (
          <li key={line.key}>{line.text}</li>
        ))}
      </ul>

      {report.unreadable.length > 0 && (
        <div>
          <p className="t-meta">{t("wlt.importUnreadable", { count: report.unreadable.length })}</p>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {report.unreadable.map((row) => (
              <li key={row.row} className="t-meta">
                {t("wlt.importRowError", { row: row.row, error: Object.keys(row.errors).join(", ") })}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.errors.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {report.errors.map((row) => (
            <li key={row.row} className="t-meta">
              {t("wlt.importRowError", { row: row.row, error: row.error })}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
