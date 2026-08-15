import { App, Alert, Checkbox, Col, DatePicker, Form, Input, Modal, Row, Select } from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { Youth } from "../api/types";
import LocationPicker from "./LocationPicker";

const SEX = [
  { value: "MALE", label: "Male" },
  { value: "FEMALE", label: "Female" },
  { value: "OTHER", label: "Other" },
];

const PSNP = [
  { value: "ENROLLED", label: "Enrolled" },
  { value: "GRADUATED", label: "Graduated" },
  { value: "NOT_PSNP", label: "Not PSNP" },
];

const EDUCATION = [
  { value: "NONE", label: "No formal education" },
  { value: "PRIMARY_INCOMPLETE", label: "Primary incomplete (grades 1-8)" },
  { value: "PRIMARY_COMPLETE", label: "Primary complete (grade 8)" },
  { value: "SECONDARY_INCOMPLETE", label: "Secondary incomplete (grades 9-12)" },
  { value: "SECONDARY_COMPLETE", label: "Secondary complete (grade 12)" },
  { value: "TVET", label: "TVET certificate or diploma" },
  { value: "TERTIARY", label: "University degree or above" },
];

const DISABILITY = [
  { value: "NONE", label: "No disability" },
  { value: "PHYSICAL", label: "Physical / mobility" },
  { value: "VISUAL", label: "Visual" },
  { value: "HEARING", label: "Hearing" },
  { value: "INTELLECTUAL", label: "Intellectual" },
  { value: "PSYCHOSOCIAL", label: "Psychosocial" },
  { value: "MULTIPLE", label: "Multiple" },
  { value: "UNDISCLOSED", label: "Not disclosed" },
];

interface Props {
  open: boolean;
  youth: Youth | null;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Youth intake and edit — spec §4.1.
 *
 * Consent is not an optional checkbox: §9 makes it the basis for holding the
 * record at all, and the API refuses to register a youth without it. The form
 * says so rather than letting the user discover it from a field error.
 */
export default function YouthFormModal({ open, youth, onClose, onSaved }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (youth) {
      form.setFieldsValue({
        ...youth,
        date_of_birth: youth.date_of_birth ? dayjs(youth.date_of_birth) : undefined,
        consent_date: youth.consent_date ? dayjs(youth.consent_date) : undefined,
      });
    } else {
      form.resetFields();
      // Consent is recorded at the moment of registration, so default the date
      // to today rather than making the worker pick it every time.
      form.setFieldsValue({ consent_given: true, consent_date: dayjs() });
    }
  }, [open, youth, form]);

  async function submit(values: Record<string, unknown>) {
    setSaving(true);
    const payload = {
      ...values,
      date_of_birth: values.date_of_birth ? dayjs(values.date_of_birth as string).format("YYYY-MM-DD") : undefined,
      consent_date: values.consent_date ? dayjs(values.consent_date as string).format("YYYY-MM-DD") : undefined,
    };
    try {
      if (youth) {
        await api.patch(`/youth/${youth.id}/`, payload);
        message.success("Youth record updated.");
      } else {
        const response = await api.post("/youth/", payload);
        // The API warns rather than blocks when the age falls outside the band
        // (spec §11 — the band itself is unconfirmed). Surface it.
        const warning = response.data?.age_band_warning;
        message.success("Youth registered.");
        if (warning) message.warning(warning, 6);
      }
      onSaved();
      onClose();
    } catch (error) {
      message.error(errorMessage(error, "Could not save the youth record."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      title={youth ? `Edit ${youth.full_name}` : "Register a youth"}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={saving}
      okText={youth ? "Save" : "Register"}
      width={720}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="full_name" label="Full name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={6}>
            <Form.Item name="sex" label="Sex" rules={[{ required: true }]}>
              <Select options={SEX} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={6}>
            <Form.Item
              name="date_of_birth"
              label="Date of birth"
              rules={[{ required: true }]}
              extra="Confirms age-band eligibility."
            >
              <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="phone_number" label="Phone" extra="Youth or next-of-kin contact.">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="national_or_kebele_id" label="National or kebele ID">
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <LocationPicker form={form} />

        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="household_id" label="PSNP household ID" extra="Where the youth is linked to one.">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="psnp_status" label="PSNP status">
              <Select options={PSNP} allowClear />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="education_level" label="Education level">
              <Select options={EDUCATION} allowClear />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="disability_status" label="Disability status">
              <Select options={DISABILITY} allowClear />
            </Form.Item>
          </Col>
        </Row>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Consent is required to hold this record"
          description="Data protection (spec §9). A youth cannot be registered without recorded consent."
        />
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item
              name="consent_given"
              valuePropName="checked"
              rules={[
                {
                  validator: (_, value) =>
                    value ? Promise.resolve() : Promise.reject(new Error("Consent must be recorded.")),
                },
              ]}
            >
              <Checkbox>Consent given</Checkbox>
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="consent_date" label="Consent date" rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
