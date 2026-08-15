import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Empty, Input, Modal, Radio, Row, Space, Statistic, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import {
  ALERT_TYPES_PENDING_ENTITIES,
  ALERT_TYPE_COLOURS,
  type Alert,
  type AlertSummary,
  type AlertTypeCode,
  type Paginated,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";

type Scope = "mine" | "all";

/**
 * Alert inbox — spec §4.13, §10 Sprint 4.
 *
 * Alerts are raised by the detection jobs, never created here, so this screen
 * only reads and resolves. Resolution is deliberately two-valued: §4.13
 * separates Actioned from Dismissed so reporting can distinguish "we did
 * something" from "this did not warrant anything".
 */
export default function AlertsPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [rows, setRows] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [scope, setScope] = useState<Scope>("mine");
  const [showResolved, setShowResolved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<{ alert: Alert; kind: "action" | "dismiss" } | null>(null);
  const [note, setNote] = useState("");

  const canResolve = user?.access.case_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const listUrl = scope === "mine" && !showResolved ? "/alerts/my-inbox/" : "/alerts/";
      const [list, counts] = await Promise.all([
        api.get<Paginated<Alert>>(listUrl, {
          params: {
            page,
            // my-inbox is already open-and-mine; the general list needs filtering.
            ...(listUrl === "/alerts/" ? { status: showResolved ? undefined : "OPEN" } : {}),
          },
        }),
        api.get<AlertSummary>("/alerts/summary/"),
      ]);
      setRows(list.data.results);
      setCount(list.data.count);
      setSummary(counts.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load alerts."));
    } finally {
      setLoading(false);
    }
  }, [page, scope, showResolved, message]);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve() {
    if (!resolving) return;
    try {
      await api.post(`/alerts/${resolving.alert.id}/${resolving.kind}/`, { note });
      message.success(resolving.kind === "action" ? "Alert actioned." : "Alert dismissed.");
      setResolving(null);
      setNote("");
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not resolve the alert."));
    }
  }

  const columns: ColumnsType<Alert> = [
    {
      title: "Alert",
      key: "alert",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Tag color={ALERT_TYPE_COLOURS[row.alert_type]}>{row.alert_type_display}</Tag>
          <Typography.Text style={{ fontSize: 12 }}>{row.summary}</Typography.Text>
        </Space>
      ),
    },
    {
      title: "Youth",
      key: "youth",
      width: 190,
      render: (_, row) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/cases/${row.case}`)}>
          {row.youth_name}
        </Button>
      ),
    },
    { title: "Woreda", dataIndex: "woreda", width: 120 },
    {
      title: "Raised",
      key: "raised",
      width: 150,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <span>{row.triggered_date}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.age_days === 0 ? "today" : `${row.age_days} days ago`}
          </Typography.Text>
        </Space>
      ),
    },
    { title: "Assigned to", dataIndex: "assigned_to_name", width: 160 },
    {
      title: "Status",
      key: "status",
      width: 220,
      render: (_, row) => {
        if (row.status !== "OPEN") {
          return (
            <Space direction="vertical" size={0}>
              <Tag color={row.status === "ACTIONED" ? "green" : "default"}>{row.status_display}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {/* No actor means the resolution sweep closed it because the
                    underlying condition cleared on its own. */}
                {row.actioned_by_name ?? "auto-resolved"} · {row.actioned_date}
              </Typography.Text>
            </Space>
          );
        }
        if (!canResolve) return <Tag color="gold">Open</Tag>;
        return (
          <Space>
            <Button
              size="small"
              type="primary"
              icon={<CheckOutlined />}
              onClick={() => {
                setNote("");
                setResolving({ alert: row, kind: "action" });
              }}
            >
              Action
            </Button>
            <Button
              size="small"
              icon={<CloseOutlined />}
              onClick={() => {
                setNote("");
                setResolving({ alert: row, kind: "dismiss" });
              }}
            >
              Dismiss
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Open alerts in scope" value={summary?.open_total ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Assigned to me" value={summary?.assigned_to_me ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" title="By type">
            <Space wrap size={[8, 8]}>
              {summary?.by_type.map((row) => (
                <Tooltip
                  key={row.alert_type}
                  title={
                    ALERT_TYPES_PENDING_ENTITIES.includes(row.alert_type as AlertTypeCode)
                      ? "Detection for this type arrives with its entity in a later sprint"
                      : undefined
                  }
                >
                  <Tag
                    color={row.count ? ALERT_TYPE_COLOURS[row.alert_type] : "default"}
                    style={{
                      opacity: ALERT_TYPES_PENDING_ENTITIES.includes(row.alert_type as AlertTypeCode) ? 0.5 : 1,
                    }}
                  >
                    {row.label}: {row.count}
                  </Tag>
                </Tooltip>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card
        title="Alerts"
        extra={
          <Space>
            <Radio.Group
              size="small"
              value={scope}
              onChange={(e) => {
                setScope(e.target.value);
                setPage(1);
              }}
              options={[
                { value: "mine", label: "Mine" },
                { value: "all", label: "All in scope" },
              ]}
              optionType="button"
            />
            <Radio.Group
              size="small"
              value={showResolved}
              onChange={(e) => {
                setShowResolved(e.target.value);
                setPage(1);
              }}
              options={[
                { value: false, label: "Open" },
                { value: true, label: "Include resolved" },
              ]}
              optionType="button"
            />
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          pagination={{
            current: page,
            pageSize: 25,
            total: count,
            showSizeChanger: false,
            onChange: setPage,
            showTotal: (total) => `${total} alert${total === 1 ? "" : "s"}`,
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="Nothing outstanding. Alerts appear here when the detection jobs find a case that needs attention."
              />
            ),
          }}
        />
      </Card>

      <Modal
        open={!!resolving}
        title={resolving?.kind === "action" ? "Action this alert" : "Dismiss this alert"}
        onCancel={() => setResolving(null)}
        onOk={resolve}
        okText={resolving?.kind === "action" ? "Mark actioned" : "Dismiss"}
      >
        <Typography.Paragraph type="secondary">
          {resolving?.kind === "action"
            ? "Use this when the underlying situation has been dealt with."
            : "Use this when the alert did not warrant action. Kept separate from Actioned so reporting can tell them apart."}
        </Typography.Paragraph>
        <Typography.Paragraph strong>{resolving?.alert.summary}</Typography.Paragraph>
        <Input.TextArea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What was done, or why no action was needed"
        />
      </Modal>
    </Space>
  );
}
