import { App, DatePicker, Form, Input, InputNumber, Modal, Select } from "antd";
import { useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { WltLoan, WltLoanPurpose, WltMeetingRegister } from "../../api/types";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * Lending, on the meeting screen.
 *
 * Both halves of it belong here rather than on the group, because both move
 * cash in the room: a disbursement takes money out of the box and a repayment
 * puts it back, and the till count at the end of the meeting has to balance
 * around them. Lending outside a meeting would leave the box short by the
 * principal with nothing to explain it.
 *
 * Every refusal comes from the service and its wording is passed straight
 * through — "this group has held 6 savings meetings, lending starts after 10"
 * is the answer a facilitator needs, not a generic failure.
 *
 * Until this existed, completed loan cycles and portfolio at risk read as zero
 * on every readiness card, because nothing outside a shell could write a loan.
 */

const PURPOSES: WltLoanPurpose[] = ["IGA", "EMERGENCY", "HOUSEHOLD", "EDUCATION", "OTHER"];

export default function MeetingLending({
  meetingId,
  data,
  canWrite,
  onChanged,
}: {
  meetingId: string;
  data: WltMeetingRegister;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [disburseForm] = Form.useForm();
  const [repayForm] = Form.useForm();

  const [disbursing, setDisbursing] = useState(false);
  const [repaying, setRepaying] = useState<WltLoan | null>(null);
  const [saving, setSaving] = useState(false);

  const isOpen = data.meeting.status === "OPEN";

  async function disburse(values: Record<string, unknown>) {
    setSaving(true);
    try {
      const due = values.due_on as { format?: (pattern: string) => string } | undefined;
      const created = await api.post<WltLoan>(`/wlt/meetings/${meetingId}/loans/`, {
        person: values.person,
        principal_etb: String(values.principal_etb ?? ""),
        purpose: values.purpose,
        purpose_note: values.purpose_note || "",
        due_on: due?.format ? due.format("YYYY-MM-DD") : undefined,
      });
      message.success(
        t("wlt.disburseDone", { amount: created.data.principal_etb, name: created.data.borrower_name }),
      );
      disburseForm.resetFields();
      setDisbursing(false);
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.disburseFailed")));
    } finally {
      setSaving(false);
    }
  }

  async function repay(values: Record<string, unknown>) {
    if (!repaying) return;
    const principal = Number(values.principal_etb ?? 0);
    const charge = Number(values.charge_etb ?? 0);
    // Caught here as well as in the service, so the facilitator is told before
    // the round trip rather than after it.
    if (principal <= 0 && charge <= 0) {
      message.error(t("wlt.repaySomething"));
      return;
    }
    setSaving(true);
    try {
      await api.post(`/wlt/meetings/${meetingId}/loans/${repaying.id}/repay/`, {
        principal_etb: String(principal),
        charge_etb: String(charge),
      });
      message.success(t("wlt.repayDone"));
      repayForm.resetFields();
      setRepaying(null);
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.repayFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
          <CapsLabel>{t("wlt.lending")}</CapsLabel>
          {/* The ceiling on what can be lent. Shown so a refusal is not the
              first time anyone learns the money is not there. */}
          <span className="t-meta">
            {t("wlt.inTheBox")}: <span className="tabular">{data.cash_balance_etb} ETB</span>
          </span>
        </span>
        {isOpen && canWrite && (
          <Button size="sm" disabled={data.members.length === 0} onClick={() => setDisbursing(true)}>
            {t("wlt.disburse")}
          </Button>
        )}
      </div>

      {/* Nobody to lend to. The register is the roster **as at the meeting
          date**, so a meeting dated before anyone joined has an empty one —
          and an empty borrower dropdown with no explanation reads as a broken
          form rather than as a date problem. It was reported as one. */}
      {data.members.length === 0 && (
        <p className="t-meta" style={{ marginTop: 8 }}>
          {t("wlt.noBorrowers", { date: data.meeting.held_on })}
        </p>
      )}

      {data.loans.length === 0 && (
        <>
          <p style={{ marginTop: 8 }}>{t("wlt.noLoans")}</p>
          <p className="t-meta">{t("wlt.noLoansBody")}</p>
        </>
      )}

      {data.loans.length > 0 && (
        <table className="roster-table">
          <tbody>
            {data.loans.map((loan) => (
              <tr key={loan.id}>
                <td style={{ fontWeight: 600 }}>{loan.borrower_name}</td>
                <td className="t-meta">
                  {t(`wlt.purpose${loan.purpose}`)} · {t("wlt.loanDue", { date: loan.due_on })}
                </td>
                <td className="tabular">
                  {t("wlt.outstanding")} {loan.outstanding_principal_etb} ETB
                </td>
                <td style={{ textAlign: "right" }}>
                  {isOpen && canWrite && (
                    <Button size="sm" onClick={() => setRepaying(loan)}>
                      {t("wlt.repay")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Modal
        open={disbursing}
        title={t("wlt.disburseTitle")}
        okText={t("wlt.disburseOk")}
        confirmLoading={saving}
        onCancel={() => setDisbursing(false)}
        onOk={() => disburseForm.submit()}
        destroyOnHidden
      >
        <Form form={disburseForm} layout="vertical" onFinish={disburse} requiredMark="optional">
          <Form.Item
            name="person"
            label={t("wlt.borrower")}
            rules={[{ required: true, message: t("wlt.borrowerRequired") }]}
          >
            {/* The roster as at this meeting — a loan is given to somebody in
                the room, and the register already carries exactly that list. */}
            <Select
              showSearch
              optionFilterProp="label"
              options={data.members.map((member) => ({ value: member.person, label: member.full_name }))}
            />
          </Form.Item>

          <Form.Item
            name="principal_etb"
            label={t("wlt.principal")}
            rules={[{ required: true, message: t("wlt.principalRequired") }]}
          >
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item
            name="purpose"
            label={t("wlt.loanPurpose")}
            rules={[{ required: true, message: t("wlt.loanPurposeRequired") }]}
          >
            <Select options={PURPOSES.map((purpose) => ({ value: purpose, label: t(`wlt.purpose${purpose}`) }))} />
          </Form.Item>

          <Form.Item name="purpose_note" label={t("wlt.purposeNote")}>
            <Input />
          </Form.Item>

          <Form.Item
            name="due_on"
            label={t("wlt.dueOn")}
            rules={[{ required: true, message: t("wlt.dueOnRequired") }]}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={repaying !== null}
        title={t("wlt.repayTitle", { name: repaying?.borrower_name ?? "" })}
        okText={t("wlt.repayOk")}
        confirmLoading={saving}
        onCancel={() => setRepaying(null)}
        onOk={() => repayForm.submit()}
        destroyOnHidden
      >
        <p className="t-meta">{t("wlt.repayHelp")}</p>
        <Form form={repayForm} layout="vertical" onFinish={repay} requiredMark="optional">
          <Form.Item name="principal_etb" label={t("wlt.repayPrincipal")}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="charge_etb" label={t("wlt.repayCharge")}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
