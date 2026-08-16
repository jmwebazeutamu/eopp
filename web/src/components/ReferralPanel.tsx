import { PlusOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Tag, Tooltip, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../api/client";
import {
  REFERRAL_STATUS_COLOURS,
  type OutcomeTypeTerm,
  type Paginated,
  type Partner,
  type Referral,
  type ReferralCategoryTerm,
  type ReferralStackNode,
  type TaxonomyTerm,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";

/**
 * The referral stack for one case — spec §6.4.
 *
 * The stack is not a stored object; the API rebuilds it by query from the
 * parent/replacement links every time. This component just renders the tree it
 * is given, so it cannot drift from the data.
 */
interface Props {
  caseId: string;
  woreda: string;
  onChanged: () => void;
}

type ActionKind = "confirm" | "decline" | "complete" | "fail" | "cancel" | "onward" | "replace";

const ACTION_LABELS: Record<ActionKind, string> = {
  confirm: "Partner confirmed",
  decline: "Partner declined",
  complete: "Record outcome",
  fail: "Record failure",
  cancel: "Withdraw referral",
  onward: "Onward referral",
  replace: "Replacement referral",
};

export default function ReferralPanel({ caseId, woreda, onChanged }: Props) {
  const { user } = useAuth();
  const { message } = App.useApp();

  const [stack, setStack] = useState<ReferralStackNode[]>([]);
  const [categories, setCategories] = useState<ReferralCategoryTerm[]>([]);
  const [outcomeTypes, setOutcomeTypes] = useState<OutcomeTypeTerm[]>([]);
  const [failureReasons, setFailureReasons] = useState<TaxonomyTerm[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);

  const [action, setAction] = useState<{ kind: ActionKind; referral: Referral } | null>(null);
  const [initiating, setInitiating] = useState(false);
  const [form] = Form.useForm();

  const canWrite = user?.access.referral_write ?? false;

  // §5.1/§5.3/§5.4 mark some terms (the "Other" catch-alls) as requiring a
  // free-text note, and the backend rejects the write without one. Watching the
  // selection lets the form say so up front instead of surfacing a 400 after
  // the user has submitted.
  const selectedCategory = Form.useWatch("referral_category", form) as string | undefined;
  const selectedOutcome = Form.useWatch("outcome_type", form) as string | undefined;
  const selectedFailure = Form.useWatch("failure_reason_code", form) as string | undefined;

  const noteRequired =
    categories.some((c) => c.code === selectedCategory && c.requires_note) ||
    outcomeTypes.some((o) => o.code === selectedOutcome && o.requires_note) ||
    failureReasons.some((f) => f.code === selectedFailure && f.requires_note);

  const noteRules = noteRequired
    ? [{ required: true, message: "This selection requires a note." }]
    : [];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [stackRes, cats, outcomes, failures, parts] = await Promise.all([
        api.get<ReferralStackNode[]>(`/referrals/stack/${caseId}/`),
        api.get<ReferralCategoryTerm[]>("/referrals/categories/"),
        api.get<OutcomeTypeTerm[]>("/referrals/outcome-types/"),
        api.get<TaxonomyTerm[]>("/referrals/failure-reasons/"),
        // Only partners covering this case's woreda can realistically serve it.
        // page_size: the active-partner filter below runs client-side, so a
        // truncated first page could hide every partner that can actually
        // receive a referral.
        api.get<Paginated<Partner>>("/partners/", { params: { woreda, page_size: 500 } }),
      ]);
      setStack(stackRes.data);
      setCategories(cats.data);
      setOutcomeTypes(outcomes.data);
      setFailureReasons(failures.data);
      setPartners(parts.data.results.filter((p) => p.can_receive_referrals));
    } catch (error) {
      message.error(errorMessage(error, "Could not load referrals."));
    } finally {
      setLoading(false);
    }
  }, [caseId, woreda, message]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Flatten the tree so cap/parallel summaries can be computed. */
  const flat = useMemo(() => {
    const out: Referral[] = [];
    const walk = (nodes: ReferralStackNode[]) => {
      nodes.forEach((node) => {
        out.push(node.referral);
        walk(node.children);
      });
    };
    walk(stack);
    return out;
  }, [stack]);

  const activeCountingReferrals = flat.filter((r) => r.status === "ACTIVE" && r.counts_toward_parallel_cap);
  const atCap = activeCountingReferrals.length >= 2;

  async function submit(values: Record<string, unknown>) {
    if (!action) return;
    try {
      await api.post(`/referrals/${action.referral.id}/${action.kind}/`, values);
      message.success(`${ACTION_LABELS[action.kind]} recorded.`);
      setAction(null);
      form.resetFields();
      await load();
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, "Could not record that."));
    }
  }

  async function initiate(values: Record<string, unknown>) {
    try {
      await api.post("/referrals/initiate/", { ...values, case: caseId });
      message.success("Referral initiated.");
      setInitiating(false);
      form.resetFields();
      await load();
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, "Could not initiate the referral."));
    }
  }

  function actionsFor(referral: Referral): ActionKind[] {
    if (!canWrite) return [];
    // Mirrors the §6.2 table the API enforces. `allowed_transitions` comes from
    // the server, so this cannot drift from the real state machine.
    const allowed = referral.allowed_transitions;
    const kinds: ActionKind[] = [];
    if (allowed.includes("ACTIVE")) kinds.push("confirm");
    if (referral.status === "PENDING_CONFIRMATION" && allowed.includes("FAILED")) kinds.push("decline");
    if (allowed.includes("CANCELLED")) kinds.push("cancel");
    if (allowed.includes("COMPLETED")) kinds.push("complete");
    if (referral.status === "ACTIVE" && allowed.includes("FAILED")) kinds.push("fail");
    // Onward and replacement create a *new* referral rather than moving this one.
    if (referral.status === "COMPLETED" && !referral.replacement_referral) kinds.push("onward");
    if (referral.status === "FAILED") kinds.push("replace");
    return kinds;
  }

  function renderNode(node: ReferralStackNode, depth = 0) {
    const r = node.referral;
    return (
      <div key={r.id} style={{ marginLeft: depth * 24, marginBottom: 12 }}>
        <Card size="small" style={{ borderLeft: `3px solid ${depth ? "#d9d9d9" : "#1668dc"}` }}>
          <Space direction="vertical" size={4} style={{ width: "100%" }}>
            <Space wrap>
              <Typography.Text strong>{r.referral_category_label}</Typography.Text>
              <Tag color={REFERRAL_STATUS_COLOURS[r.status]}>{r.status_display}</Tag>
              {r.referral_trigger !== "MANUAL" && <Tag>{r.trigger_display}</Tag>}
              {r.is_parallel && (
                <Tooltip title="Ran concurrently with another referral on this case (spec §6.3)">
                  <Tag color="cyan">Parallel</Tag>
                </Tooltip>
              )}
              {!r.counts_toward_parallel_cap && (
                <Tooltip title="Complementary Service runs outside the two-referral cap">
                  <Tag color="geekblue">Outside cap</Tag>
                </Tooltip>
              )}
            </Space>

            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              To {r.receiving_partner_detail.partner_name} · initiated {r.initiated_date} by {r.initiated_by_name}
            </Typography.Text>

            {r.outcome_type_label && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Outcome: {r.outcome_type_label} on {r.outcome_date}
              </Typography.Text>
            )}
            {r.failure_reason_label && (
              <Typography.Text type="danger" style={{ fontSize: 12 }}>
                Failed: {r.failure_reason_label} on {r.failure_date}
              </Typography.Text>
            )}
            {r.notes && <Typography.Text style={{ fontSize: 12 }}>{r.notes}</Typography.Text>}

            {actionsFor(r).length > 0 && (
              <Space wrap style={{ marginTop: 4 }}>
                {actionsFor(r).map((kind) => (
                  <Button
                    key={kind}
                    size="small"
                    danger={kind === "decline" || kind === "fail"}
                    onClick={() => {
                      form.resetFields();
                      setAction({ kind, referral: r });
                    }}
                  >
                    {ACTION_LABELS[kind]}
                  </Button>
                ))}
              </Space>
            )}
          </Space>
        </Card>
        {node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  }

  const categoryOptions = categories.map((c) => ({ value: c.code, label: c.label }));
  const partnerOptions = partners.map((p) => ({
    value: p.id,
    label: `${p.partner_name} (${p.partner_type_display})`,
  }));

  return (
    <Card
      title="Referrals"
      loading={loading}
      extra={
        canWrite && (
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields();
              setInitiating(true);
            }}
          >
            New referral
          </Button>
        )
      }
    >
      {atCap && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Two active referrals — the parallel cap is full"
          description={
            "A third referral can be initiated but cannot be confirmed until one of these closes. " +
            "Complementary Service referrals are exempt and can still run alongside (spec §6.3)."
          }
        />
      )}

      {stack.length ? (
        stack.map((node) => renderNode(node))
      ) : (
        <Empty description="No referrals yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}

      {/* Initiate — §6.2 first row */}
      <Modal
        open={initiating}
        title="Initiate a referral"
        onCancel={() => setInitiating(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={initiate} requiredMark={false}>
          <Form.Item name="referral_category" label="Category" rules={[{ required: true }]}>
            <Select options={categoryOptions} />
          </Form.Item>
          <Form.Item
            name="receiving_partner"
            label="Receiving partner"
            rules={[{ required: true }]}
            extra={`Active partners covering ${woreda}.`}
          >
            <Select options={partnerOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="receiving_contact_name" label="Contact at the partner">
            <Input />
          </Form.Item>
          <Form.Item
            name="notes"
            label="Notes"
            rules={noteRules}
            extra={noteRequired ? "This category requires a note." : undefined}
          >
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Transitions — §6.2 */}
      <Modal
        open={!!action}
        title={action ? ACTION_LABELS[action.kind] : ""}
        onCancel={() => setAction(null)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        {/* Every action posts to /referrals/{id}/{kind}/, so one handler covers
            them all — including onward and replace, which create a new referral
            rather than moving this one. */}
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          {action?.kind === "confirm" && (
            <Form.Item name="confirmed_by" label="Confirmed by" rules={[{ required: true }]}>
              <Input placeholder="Name of the partner contact who confirmed" />
            </Form.Item>
          )}

          {(action?.kind === "decline" || action?.kind === "fail") && (
            <Form.Item name="failure_reason_code" label="Failure reason" rules={[{ required: true }]}>
              <Select options={failureReasons.map((f) => ({ value: f.code, label: f.label }))} />
            </Form.Item>
          )}

          {action?.kind === "complete" && (
            <>
              <Form.Item
                name="outcome_type"
                label="Outcome"
                rules={[{ required: true }]}
                extra={
                  outcomeTypes.filter(
                    (o) => o.applies_to.length === 0 || o.applies_to.includes(action.referral.referral_category),
                  ).length === 0
                    ? "No outcome type is configured for this referral category. An administrator must map one (spec §5.3)."
                    : undefined
                }
              >
                <Select
                  notFoundContent="No outcome type applies to this category."
                  options={outcomeTypes
                    .filter(
                      (o) =>
                        o.applies_to.length === 0 ||
                        o.applies_to.includes(action.referral.referral_category),
                    )
                    .map((o) => ({ value: o.code, label: o.label }))}
                />
              </Form.Item>
              <Form.Item name="outcome_verification_method" label="How was it verified?">
                <Input placeholder="e.g. Follow-up home visit" />
              </Form.Item>
            </>
          )}

          {(action?.kind === "onward" || action?.kind === "replace") && (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={
                  action.kind === "onward"
                    ? "The completed referral stays as it is; this creates the next one in the chain."
                    : "The failed referral moves to Replaced and this becomes its replacement."
                }
              />
              <Form.Item name="referral_category" label="Category" rules={[{ required: true }]}>
                <Select options={categoryOptions} />
              </Form.Item>
              <Form.Item name="receiving_partner" label="Receiving partner" rules={[{ required: true }]}>
                <Select options={partnerOptions} showSearch optionFilterProp="label" />
              </Form.Item>
            </>
          )}

          <Form.Item
            name="notes"
            label="Notes"
            rules={noteRules}
            extra={noteRequired ? "This selection requires a note." : undefined}
          >
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
