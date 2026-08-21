import { Alert, App, Checkbox, DatePicker, Form, Input, Modal, Select } from "antd";
import { useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { Location } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The exception route — decision D5's "a facilitator standing in front of a
 * woman who is plainly eligible needs a legitimate route".
 *
 * Three things about this form are the decision rather than the layout:
 *
 * - **It says up front that she starts pending.** The control that stops the
 *   exception path becoming the main path is that a woreda officer verifies
 *   her, and a form that hid that would make the refusal at group assignment
 *   look like a bug.
 * - **The place is a kebele and nothing else.** Region, zone and woreda are
 *   derived server-side; offering them here invites a hand-typed woreda that
 *   disagrees with its kebele, which scopes to one place and reports in another.
 * - **The two ELS dates are on the form, marked as eligibility conditions.**
 *   They are optional to record and required to join a group, so collecting
 *   them now is the difference between a woman who can be seated next week and
 *   one who needs a second visit.
 */
export default function RegisterWomanModal({
  open,
  onClose,
  onDone,
  initialKebele,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  initialKebele?: string;
  onCreated?: (record: { profileId: string; personId: string }) => void;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [form] = Form.useForm();
  const [kebeles, setKebeles] = useState<Location[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await api.get<Location[]>("/locations/");
        if (!cancelled) {
          setKebeles(response.data.filter((row) => row.level === "KEBELE"));
          if (initialKebele) form.setFieldValue("kebele", initialKebele);
        }
      } catch {
        if (!cancelled) setKebeles([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [form, initialKebele, open]);

  const submit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { ...values };
      payload.has_device = Boolean(String(values.phone_number || "").trim());
      // antd hands back dayjs objects; the API wants plain dates.
      for (const field of ["date_of_birth", "consent_date", "els_completed_on", "els_grant_received_on"]) {
        const value = values[field] as { format?: (pattern: string) => string } | undefined;
        payload[field] = value?.format ? value.format("YYYY-MM-DD") : undefined;
      }
      const created = await api.post<{ id: string; full_name: string; person: string }>("/wlt/profiles/register/", payload);
      message.success(t("wlt.registerDone", { name: created.data.full_name }));
      form.resetFields();
      onCreated?.({ profileId: created.data.id, personId: created.data.person });
      onDone();
      onClose();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.registerFailed")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("wlt.registerTitle")}
      okText={t("wlt.registerOk")}
      cancelText={t("common.cancel")}
      confirmLoading={submitting}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      destroyOnHidden
      width={560}
    >
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t("wlt.registerIntro")} />

      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item name="full_name" label={t("wlt.fullName")} rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="date_of_birth" label={t("wlt.dateOfBirth")} rules={[{ required: true }]}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name="kebele"
          label={t("wlt.kebele")}
          extra={t("wlt.kebeleHelp")}
          rules={[{ required: true }]}
        >
          <Select
            showSearch
            optionFilterProp="label"
            options={kebeles.map((kebele) => ({ value: kebele.code, label: kebele.name }))}
          />
        </Form.Item>
        <Form.Item name="phone_number" label={t("wlt.phone")}>
          <Input />
        </Form.Item>
        <Form.Item name="psnp_client_id" label={t("wlt.clientId")}>
          <Input />
        </Form.Item>

        <Form.Item name="els_completed_on" label={t("wlt.elsCompleted")} extra={t("wlt.elsHelp")}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="els_grant_received_on" label={t("wlt.elsGrant")}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name="consent_given"
          valuePropName="checked"
          extra={t("wlt.consentHelp")}
          rules={[
            {
              // §9 makes consent the basis for holding the record at all, and
              // the server refuses it too. Asked here so the refusal is not the
              // first time anybody mentions it.
              validator: (_rule, value) =>
                value ? Promise.resolve() : Promise.reject(new Error(t("wlt.consentRequired"))),
            },
          ]}
        >
          <Checkbox>{t("wlt.consentGiven")}</Checkbox>
        </Form.Item>
        <Form.Item name="consent_date" label={t("wlt.consentDate")} rules={[{ required: true }]}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>

        <Form.Item name="note" label={t("wlt.registerNote")}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
