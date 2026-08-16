import { PlusOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Divider, Empty, Space, Tag, Tooltip, Typography } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, errorMessage } from "../api/client";
import { REFERRAL_STATUS_COLOURS, type Referral, type ReferralStackNode } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ReferralActionModal, { ACTION_LABELS, actionsFor, type ReferralAction } from "./ReferralActions";
import ReferralStackTimeline from "./referrals/ReferralStackTimeline";

/**
 * The referral stack for one case — spec §6.4.
 *
 * The stack is not a stored object; the API rebuilds it by query from the
 * parent/replacement links every time. This component just renders the tree it
 * is given, so it cannot drift from the data. The actions themselves live in
 * ReferralActions, shared with the cross-case queue.
 */
interface Props {
  caseId: string;
  woreda: string;
  onChanged: () => void;
}

export default function ReferralPanel({ caseId, woreda, onChanged }: Props) {
  const { user } = useAuth();
  const { message } = App.useApp();

  const [stack, setStack] = useState<ReferralStackNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ReferralAction | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // The timeline is read-only, so a click on a bar has to land somewhere that
  // can act. It selects the card below rather than opening a second detail
  // surface — the §6.2 buttons already live there.
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const canWrite = user?.access.referral_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<ReferralStackNode[]>(`/referrals/stack/${caseId}/`);
      setStack(response.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load referrals."));
    } finally {
      setLoading(false);
    }
  }, [caseId, message]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Flatten the tree so the cap summary can be computed. */
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

  const atCap = flat.filter((r) => r.status === "ACTIVE" && r.counts_toward_parallel_cap).length >= 2;

  function selectFromTimeline(referralId: string) {
    setSelectedId(referralId);
    cardRefs.current[referralId]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderNode(node: ReferralStackNode, depth = 0) {
    const r = node.referral;
    const kinds = actionsFor(r, canWrite);
    const isSelected = selectedId === r.id;
    return (
      <div
        key={r.id}
        ref={(element) => {
          cardRefs.current[r.id] = element;
        }}
        style={{ marginLeft: depth * 24, marginBottom: 12 }}
      >
        <Card
          size="small"
          style={{
            borderLeft: `3px solid ${depth ? "#d9d9d9" : "#1668dc"}`,
            boxShadow: isSelected ? "0 0 0 2px #1668dc" : undefined,
          }}
        >
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

            {kinds.length > 0 && (
              <Space wrap style={{ marginTop: 4 }}>
                {kinds.map((kind) => (
                  <Button
                    key={kind}
                    size="small"
                    danger={kind === "decline" || kind === "fail"}
                    onClick={() => setAction({ kind, referral: r })}
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
            onClick={() => setAction({ kind: "initiate", referral: null })}
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
        <>
          {/* Spec §6.4 as the Concept Note's Figure 4 draws it: one lane per
              referral across real time, colour for status, brackets for
              concurrency. The tree below carries the actions. */}
          <ReferralStackTimeline
            referrals={flat}
            onReferralClick={selectFromTimeline}
            selectedReferralId={selectedId}
          />
          <Divider style={{ margin: "16px 0" }} />
          {stack.map((node) => renderNode(node))}
        </>
      ) : (
        <Empty description="No referrals yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}

      <ReferralActionModal
        action={action}
        caseId={caseId}
        woreda={woreda}
        onClose={() => setAction(null)}
        onDone={() => {
          void load();
          onChanged();
        }}
      />
    </Card>
  );
}
