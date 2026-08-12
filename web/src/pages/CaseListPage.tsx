import { App, Card, Input, Select, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { CaseListRow, CaseStatus, Paginated } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const STATUS_COLOURS: Record<CaseStatus, string> = {
  ACTIVE: "green",
  STALLED: "orange",
  REFERRAL_PENDING: "blue",
  PLACED: "purple",
  EXITED: "default",
};

const PAGE_SIZE = 25;

export default function CaseListPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [rows, setRows] = useState<CaseListRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<CaseStatus | undefined>();
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<CaseListRow>>("/cases/", {
        params: { page, case_status: status, search: search || undefined },
      });
      setRows(response.data.results);
      setCount(response.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load cases."));
    } finally {
      setLoading(false);
    }
  }, [page, status, search, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ColumnsType<CaseListRow> = [
    {
      title: "Youth",
      key: "youth",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.youth.full_name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.youth.sex} · {row.youth.age} · {row.youth.kebele}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Status",
      dataIndex: "case_status",
      width: 160,
      render: (value: CaseStatus, row) => <Tag color={STATUS_COLOURS[value]}>{row.case_status_display}</Tag>,
    },
    { title: "Woreda", dataIndex: "woreda", width: 130 },
    { title: "Case manager", dataIndex: "case_manager_name", width: 170 },
    {
      title: "Last activity",
      key: "last_activity",
      width: 170,
      render: (_, row) => (
        // The stall flag is computed against the configured threshold, which is
        // still a placeholder pending Phase 1 sign-off (spec §11).
        <Space>
          <span>{row.last_activity_date}</span>
          {row.is_stalled_by_threshold && (
            <Tooltip title={`No activity for ${row.days_since_activity} days`}>
              <Tag color="red">Stalled</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: "Next action",
      dataIndex: "next_action",
      ellipsis: true,
      render: (value: string) => value || <Typography.Text type="secondary">—</Typography.Text>,
    },
  ];

  return (
    <Card
      title="Cases"
      extra={
        <Typography.Text type="secondary">
          {user?.access.case_scope === "OWN_CASELOAD"
            ? "Your caseload"
            : user?.access.case_scope === "OWN_WOREDA"
              ? `Woredas: ${user.woreda_assignment.join(", ")}`
              : "All woredas"}
        </Typography.Text>
      }
    >
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="Name, phone, or ID"
          allowClear
          style={{ width: 280 }}
          onSearch={(value) => {
            setSearch(value);
            setPage(1);
          }}
        />
        <Select
          placeholder="All statuses"
          allowClear
          style={{ width: 200 }}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: "ACTIVE", label: "Active" },
            { value: "STALLED", label: "Stalled" },
            { value: "REFERRAL_PENDING", label: "Referral Pending" },
            { value: "PLACED", label: "Placed" },
            { value: "EXITED", label: "Exited" },
          ]}
        />
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        onRow={(row) => ({ onClick: () => navigate(`/cases/${row.id}`), style: { cursor: "pointer" } })}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: count,
          showSizeChanger: false,
          onChange: setPage,
          showTotal: (total) => `${total} case${total === 1 ? "" : "s"}`,
        }}
        locale={{ emptyText: "No cases match this view." }}
      />
    </Card>
  );
}
