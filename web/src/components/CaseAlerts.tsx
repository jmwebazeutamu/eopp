import { BellOutlined } from "@ant-design/icons";
import { App, Alert as AntAlert, Button, Card, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { Alert, Paginated } from "../api/types";
import { ALERT_TONE } from "../design/status";

/**
 * A geometric mark per alert type, so the chip is never colour alone.
 *
 * This chip previously read its colour from `ALERT_TYPE_COLOURS` — antd preset
 * names, outside the token layer, including a blue the handoff says is
 * deliberately absent and a red on STALL where the handoff assigns terracotta
 * and reserves red for genuine failure.
 */
const ALERT_MARK: Record<string, string> = {
  STALL: "\u25b2",
  REFERRAL_CONFIRMATION_OVERDUE: "\u25d4",
  FOLLOW_UP_DUE: "\u25cf",
  ONWARD_REFERRAL_PROMPT: "\u25cf",
  REPLACEMENT_REFERRAL_PROMPT: "\u25b2",
  RETENTION_CHECK_DUE: "\u25d4",
};
import { useAuth } from "../auth/AuthContext";

/**
 * Open alerts for one case — spec §4.13.
 *
 * Sprint 4's brief is to surface "next action" on the case screen. The Case's
 * own `next_action` field (§4.2) answers what a case manager intends; these
 * answer what the system has noticed. Both belong on the screen, so this sits
 * directly above the next-action editor.
 */
export default function CaseAlerts({ caseId, onChanged }: { caseId: string; onChanged: () => void }) {
  const { user } = useAuth();
  const { message } = App.useApp();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const canResolve = user?.access.case_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<Alert>>("/alerts/", {
        params: { case: caseId, status: "OPEN" },
      });
      setAlerts(response.data.results);
    } catch (error) {
      message.error(errorMessage(error, "Could not load alerts for this case."));
    } finally {
      setLoading(false);
    }
  }, [caseId, message]);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(alert: Alert, kind: "action" | "dismiss") {
    setBusy(alert.id);
    try {
      await api.post(`/alerts/${alert.id}/${kind}/`, {});
      message.success(kind === "action" ? "Alert actioned." : "Alert dismissed.");
      await load();
      // Resolving is case activity, so the parent's last-activity figure moves.
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, "Could not resolve the alert."));
    } finally {
      setBusy(null);
    }
  }

  // A case with nothing outstanding should not carry an empty card.
  if (!loading && alerts.length === 0) return null;

  return (
    <Card
      size="small"
      loading={loading}
      title={
        <Space>
          <BellOutlined />
          <span>Needs attention</span>
          <Tag color="gold">{alerts.length}</Tag>
        </Space>
      }
    >
      <Space orientation="vertical" size={8} style={{ width: "100%" }}>
        {alerts.map((alert) => (
          <AntAlert
            key={alert.id}
            type={alert.alert_type === "STALL" ? "error" : "warning"}
            showIcon
            title={
              <Space wrap>
                <span
                  className="chip"
                  style={{
                    color: (ALERT_TONE[alert.alert_type] ?? { fg: "var(--ink-600)" }).fg,
                    background: (ALERT_TONE[alert.alert_type] ?? { bg: "var(--fill-muted)" }).bg,
                    borderColor: "transparent",
                  }}
                >
                  <span aria-hidden="true">{ALERT_MARK[alert.alert_type] ?? "●"}</span> {alert.alert_type_display}
                </span>
                <Typography.Text style={{ fontSize: 13 }}>{alert.summary}</Typography.Text>
              </Space>
            }
            description={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Raised {alert.triggered_date}
                {alert.age_days > 0 && ` · ${alert.age_days} days ago`}
                {alert.threshold_days > 0 && ` · threshold ${alert.threshold_days} days`}
              </Typography.Text>
            }
            action={
              canResolve && (
                <Space orientation="vertical">
                  <Button size="small" type="primary" loading={busy === alert.id} onClick={() => resolve(alert, "action")}>
                    Action
                  </Button>
                  <Button size="small" loading={busy === alert.id} onClick={() => resolve(alert, "dismiss")}>
                    Dismiss
                  </Button>
                </Space>
              )
            }
          />
        ))}
      </Space>
    </Card>
  );
}
