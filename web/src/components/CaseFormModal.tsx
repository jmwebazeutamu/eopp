import { App, Alert, DatePicker, Form, Input, Modal, Select } from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import {
  CASE_STATUS_OPTIONS,
  type AssignableUser,
  type CaseDetail,
  type Paginated,
  type Youth,
} from "../api/types";

interface Props {
  open: boolean;
  /** null = open a new case; a record = edit that one. */
  record: CaseDetail | null;
  onClose: () => void;
  onSaved: (caseId?: string) => void;
}

/**
 * Open or edit a case — spec §4.2.
 *
 * Creating requires a youth who does not already have one (Case is one-to-one
 * with Youth, §3), so the picker is fed by `/youth/?without_case=true`. Note
 * that a case manager's own scope resolves through the case, so they cannot see
 * uncased youth at all — §7 gives case creation to the woreda-scoped outreach
 * worker, and the picker will be empty for anyone else.
 */
export default function CaseFormModal({ open, record, onClose, onSaved }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [youth, setYouth] = useState<Youth[]>([]);
  const [managers, setManagers] = useState<AssignableUser[]>([]);
  const [saving, setSaving] = useState(false);

  const status = Form.useWatch("case_status", form) as string | undefined;
  const isExiting = status === "EXITED";

  useEffect(() => {
    if (!open) return;

    api
      .get<AssignableUser[]>("/users/case-managers/")
      .then((response) => setManagers(response.data))
      .catch(() => setManagers([]));

    if (record) {
      form.setFieldsValue({
        ...record,
        opened_date: record.opened_date ? dayjs(record.opened_date) : undefined,
        closed_date: record.closed_date ? dayjs(record.closed_date) : undefined,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ case_status: "ACTIVE", opened_date: dayjs() });
      api
        // page_size: a picker that renders page 1 and ignores `next` silently
        // truncates its options, and the user cannot tell "not offered" from
        // "not there".
        .get<Paginated<Youth>>("/youth/", { params: { without_case: "true", page_size: 500 } })
        .then((response) => setYouth(response.data.results))
        .catch(() => setYouth([]));
    }
  }, [open, record, form]);

  async function submit(values: Record<string, unknown>) {
    setSaving(true);
    const payload = {
      ...values,
      opened_date: values.opened_date ? dayjs(values.opened_date as string).format("YYYY-MM-DD") : undefined,
      // Only an exited case may carry a closed date — the API rejects one
      // otherwise, so clear it rather than sending a stale value.
      closed_date:
        values.case_status === "EXITED" && values.closed_date
          ? dayjs(values.closed_date as string).format("YYYY-MM-DD")
          : null,
      exit_reason: values.case_status === "EXITED" ? values.exit_reason : "",
    };
    try {
      if (record) {
        await api.patch(`/cases/${record.id}/`, payload);
        message.success("Case updated.");
        onSaved(record.id);
      } else {
        const response = await api.post("/cases/", payload);
        message.success("Case opened.");
        onSaved(response.data.id);
      }
      onClose();
    } catch (error) {
      message.error(errorMessage(error, "Could not save the case."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      title={record ? `Edit case — ${record.youth_detail.full_name}` : "Open a case"}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={saving}
      okText={record ? "Save" : "Open case"}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        {!record && (
          <Form.Item
            name="youth"
            label="Youth"
            rules={[{ required: true }]}
            extra={
              youth.length === 0
                ? "No youth without a case are visible to your role. Register one first, or ask an outreach worker."
                : "Only youth who do not already have a case appear here."
            }
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={youth.map((y) => ({
                value: y.id,
                label: `${y.full_name} — ${y.woreda}, ${y.kebele} (age ${y.age})`,
              }))}
            />
          </Form.Item>
        )}

        <Form.Item
          name="case_manager"
          label="Case manager"
          rules={[{ required: true }]}
          extra="Only the Youth case manager role can hold a caseload (spec §7)."
        >
          <Select
            showSearch
            optionFilterProp="label"
            options={managers.map((m) => ({
              value: m.id,
              label: `${m.full_name}${m.woreda_assignment.length ? ` — ${m.woreda_assignment.join(", ")}` : ""}`,
            }))}
          />
        </Form.Item>

        <Form.Item name="opened_date" label="Opened" rules={[{ required: true }]}>
          <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
        </Form.Item>

        {record && (
          <Form.Item name="case_status" label="Status" rules={[{ required: true }]}>
            <Select options={CASE_STATUS_OPTIONS} />
          </Form.Item>
        )}

        {isExiting && (
          <>
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="Exiting closes the case"
              description="Cases are never deleted — an exit reason and date are the record of why it ended (spec §9)."
            />
            <Form.Item name="closed_date" label="Closed" rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
            </Form.Item>
            <Form.Item name="exit_reason" label="Exit reason" rules={[{ required: true }]}>
              <Input.TextArea rows={3} placeholder="e.g. Placed and retained past 90 days" />
            </Form.Item>
          </>
        )}

        <Form.Item name="next_action" label="Next action">
          <Input.TextArea rows={2} placeholder="What happens next, and who owns it" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
