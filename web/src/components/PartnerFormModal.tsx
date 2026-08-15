import { App, Col, DatePicker, Form, Input, Modal, Row, Select, Switch } from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import { MOU_STATUS_OPTIONS, PARTNER_TYPE_OPTIONS, type Location, type Partner } from "../api/types";

interface Props {
  open: boolean;
  partner: Partner | null;
  onClose: () => void;
  onSaved: () => void;
}

/** MOU states that record something that happened, so a date is required (§4.11). */
const MOU_NEEDS_DATE = ["SIGNED", "EXPIRED", "TERMINATED"];

/**
 * Partner create and edit — spec §4.11.
 *
 * Partners are deactivated, never deleted: referral history and the §8 partner
 * performance dashboards both depend on the record surviving.
 */
export default function PartnerFormModal({ open, partner, onClose, onSaved }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [woredas, setWoredas] = useState<Location[]>([]);
  const [saving, setSaving] = useState(false);

  const mouStatus = Form.useWatch("mou_status", form) as string | undefined;

  useEffect(() => {
    if (!open) return;
    api
      .get<Location[]>("/locations/", { params: { level: "WOREDA" } })
      .then((response) => setWoredas(response.data))
      .catch(() => setWoredas([]));

    if (partner) {
      form.setFieldsValue({ ...partner, mou_date: partner.mou_date ? dayjs(partner.mou_date) : undefined });
    } else {
      form.resetFields();
      form.setFieldsValue({ active_status: true, mou_status: "NONE", woreda_coverage: [] });
    }
  }, [open, partner, form]);

  async function submit(values: Record<string, unknown>) {
    setSaving(true);
    const payload = {
      ...values,
      mou_date: values.mou_date ? dayjs(values.mou_date as string).format("YYYY-MM-DD") : null,
    };
    try {
      if (partner) {
        await api.patch(`/partners/${partner.id}/`, payload);
        message.success("Partner updated.");
      } else {
        await api.post("/partners/", payload);
        message.success("Partner created.");
      }
      onSaved();
      onClose();
    } catch (error) {
      message.error(errorMessage(error, "Could not save the partner."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      title={partner ? `Edit ${partner.partner_name}` : "New partner"}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={saving}
      width={640}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Row gutter={12}>
          <Col xs={24} sm={14}>
            <Form.Item name="partner_name" label="Organisation name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={10}>
            <Form.Item name="partner_type" label="Type" rules={[{ required: true }]}>
              <Select options={PARTNER_TYPE_OPTIONS} />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="woreda_coverage"
          label="Woreda coverage"
          rules={[{ required: true, message: "List at least one woreda this partner covers." }]}
          extra="A partner covering nothing can never be matched to a case."
        >
          <Select
            mode="multiple"
            options={woredas.map((w) => ({ value: w.name, label: w.full_path }))}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

        <Row gutter={12}>
          <Col xs={24} sm={8}>
            <Form.Item name="contact_name" label="Contact name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item name="phone" label="Phone" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col xs={24} sm={8}>
            <Form.Item name="mou_status" label="MOU status">
              <Select options={MOU_STATUS_OPTIONS} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item
              name="mou_date"
              label="MOU date"
              rules={[{ required: MOU_NEEDS_DATE.includes(mouStatus ?? ""), message: "Required for this MOU status." }]}
            >
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item
              name="active_status"
              label="Accepting referrals"
              valuePropName="checked"
              extra="Deactivate rather than delete."
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="performance_notes"
          label="Performance notes"
          extra="Qualitative input alongside the §8 partner performance dashboards."
        >
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
