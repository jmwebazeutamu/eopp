import { ArrowLeftOutlined, EditOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Timeline,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import CaseAlerts from "../components/CaseAlerts";
import CaseFormModal from "../components/CaseFormModal";
import ReferralPanel from "../components/ReferralPanel";
import {
  PATHWAY_OPTIONS,
  type CaseDetail,
  type Paginated,
  type PathwayAssignment,
  type Pathway,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [record, setRecord] = useState<CaseDetail | null>(null);
  const [pathwayHistory, setPathwayHistory] = useState<PathwayAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [revising, setRevising] = useState(false);
  const [editing, setEditing] = useState(false);
  const [reviseForm] = Form.useForm<{ selected_pathway: Pathway; revision_reason: string }>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [detail, pathways] = await Promise.all([
        api.get<CaseDetail>(`/cases/${caseId}/`),
        api.get<Paginated<PathwayAssignment>>("/cases/pathways/", { params: { case: caseId } }),
      ]);
      setRecord(detail.data);
      setPathwayHistory(pathways.data.results);
    } catch (error) {
      // A case outside the user's scope 404s rather than 403 — the API does not
      // confirm that a record they cannot see exists.
      message.error(errorMessage(error, "Could not load this case."));
      navigate("/cases", { replace: true });
    } finally {
      setLoading(false);
    }
  }, [caseId, message, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveNextAction(values: { next_action: string }) {
    setSaving(true);
    try {
      const response = await api.patch<CaseDetail>(`/cases/${caseId}/`, values);
      setRecord(response.data);
      message.success("Next action updated.");
    } catch (error) {
      message.error(errorMessage(error, "Could not update the case."));
    } finally {
      setSaving(false);
    }
  }

  async function revisePathway(values: { selected_pathway: Pathway; revision_reason: string }) {
    if (!record?.current_pathway) return;
    try {
      await api.post(`/cases/pathways/${record.current_pathway.id}/revise/`, values);
      message.success("Pathway revised.");
      setRevising(false);
      reviseForm.resetFields();
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not revise the pathway."));
    }
  }

  if (loading)
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    );
  if (!record) return null;

  const youth = record.youth_detail;
  const canWrite = user?.access.case_write ?? false;
  const profiling = record.current_profiling;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/cases")} type="text">
          Back to cases
        </Button>
        {canWrite && (
          <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
            Edit case
          </Button>
        )}
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <span>{youth.full_name}</span>
                <Tag color={record.is_open ? "green" : "default"}>{record.case_status_display}</Tag>
                {record.is_stalled_by_threshold && <Tag color="red">Stalled</Tag>}
                {profiling?.priority_flag && <Tag color="volcano">Priority</Tag>}
              </Space>
            }
          >
            <Descriptions column={{ xs: 1, sm: 2 }} size="small" bordered>
              <Descriptions.Item label="Sex">{youth.sex}</Descriptions.Item>
              <Descriptions.Item label="Age">{youth.age}</Descriptions.Item>
              <Descriptions.Item label="Date of birth">{youth.date_of_birth}</Descriptions.Item>
              <Descriptions.Item label="Phone">{youth.phone_number || "—"}</Descriptions.Item>
              <Descriptions.Item label="Woreda">{record.woreda}</Descriptions.Item>
              <Descriptions.Item label="Kebele">{youth.kebele}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="Case">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Case manager">{record.case_manager_name}</Descriptions.Item>
              <Descriptions.Item label="Opened">{record.opened_date}</Descriptions.Item>
              <Descriptions.Item label="Last activity">
                {record.last_activity_date} ({record.days_since_activity} days ago)
              </Descriptions.Item>
              {record.closed_date && (
                <Descriptions.Item label="Closed">
                  {record.closed_date} — {record.exit_reason}
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        </Col>

        {/* Spec §4.4 — one current pathway, revisions preserved as history. */}
        <Col xs={24} lg={12}>
          <Card
            title="Pathway"
            extra={
              canWrite &&
              record.current_pathway && (
                <Button size="small" onClick={() => setRevising(true)}>
                  Revise
                </Button>
              )
            }
          >
            {record.current_pathway ? (
              <>
                <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
                  <Tag color="blue" style={{ fontSize: 14 }}>
                    {record.current_pathway.selected_pathway_display}
                  </Tag>
                  <Typography.Text type="secondary">
                    Assessed {record.current_pathway.assessment_date} by {record.current_pathway.assessor_name}
                  </Typography.Text>
                </Space>

                {pathwayHistory.length > 1 && (
                  <>
                    <Typography.Text strong>Revision history</Typography.Text>
                    <Timeline
                      style={{ marginTop: 12 }}
                      items={pathwayHistory.map((item) => ({
                        color: item.is_current ? "blue" : "gray",
                        children: (
                          <Space direction="vertical" size={0}>
                            <span>
                              {item.selected_pathway_display}
                              {item.is_current && <Tag color="blue" style={{ marginLeft: 8 }}>Current</Tag>}
                            </span>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {item.assessment_date} · {item.assessor_name}
                            </Typography.Text>
                            {item.revision_reason && (
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                Superseded: {item.revision_reason}
                              </Typography.Text>
                            )}
                          </Space>
                        ),
                      }))}
                    />
                  </>
                )}
              </>
            ) : (
              <Empty description="No pathway assigned yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Spec §4.3 — latest record is the current one. */}
        <Col xs={24} lg={12}>
          <Card title="Profiling and eligibility">
            {profiling ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="Eligible for">
                  {profiling.eligibility_flags_display.map((flag) => (
                    <Tag key={flag}>{flag}</Tag>
                  ))}
                </Descriptions.Item>
                <Descriptions.Item label="Skills">
                  {profiling.skills_list.length ? profiling.skills_list.join(", ") : "—"}
                </Descriptions.Item>
                <Descriptions.Item label="Vulnerability score">
                  {profiling.vulnerability_index_score ?? (
                    // §11: the methodology is still to be defined with M&E.
                    <Typography.Text type="secondary">Methodology pending</Typography.Text>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="Assessed">
                  {profiling.assessed_date} by {profiling.assessor_name}
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty description="No profiling record yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* What the system has noticed, above what the case manager intends. */}
        <Col span={24}>
          <CaseAlerts caseId={record.id} onChanged={load} />
        </Col>

        <Col span={24}>
          {/* Spec §4.2: next_action and its owner answer Core Design Principle
              questions 10 and 11 — what happens next, and who owns it. */}
          <Card title="Next action">
            {canWrite ? (
              <Form layout="vertical" initialValues={{ next_action: record.next_action }} onFinish={saveNextAction}>
                <Form.Item name="next_action" label="What happens next?">
                  <Input.TextArea rows={3} placeholder="e.g. Confirm TVET enrolment with Adama Polytechnic" />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={saving}>
                  Save
                </Button>
              </Form>
            ) : (
              <Typography.Paragraph>
                {record.next_action || <Typography.Text type="secondary">No next action recorded.</Typography.Text>}
              </Typography.Paragraph>
            )}
          </Card>
        </Col>

        <Col span={24}>
          <ReferralPanel caseId={record.id} woreda={record.woreda} onChanged={load} />
        </Col>
      </Row>

      <CaseFormModal open={editing} record={record} onClose={() => setEditing(false)} onSaved={() => load()} />

      <Modal
        open={revising}
        title="Revise pathway"
        onCancel={() => setRevising(false)}
        onOk={() => reviseForm.submit()}
        destroyOnHidden
      >
        <Form form={reviseForm} layout="vertical" onFinish={revisePathway} requiredMark={false}>
          <Form.Item name="selected_pathway" label="New pathway" rules={[{ required: true }]}>
            <Select options={PATHWAY_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="revision_reason"
            label="Why is it changing?"
            rules={[{ required: true, message: "A rationale is required on every pathway change." }]}
            extra="Recorded against the superseded assignment (spec §9)."
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
