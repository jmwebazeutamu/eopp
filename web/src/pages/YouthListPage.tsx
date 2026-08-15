import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Input, Segmented, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { Paginated, Youth } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import YouthFormModal from "../components/YouthFormModal";

type CaseFilter = "all" | "with" | "without";

/**
 * Youth register — spec §4.1.
 *
 * Records are never deleted: §9 makes the audit trail and the consent record
 * part of the register, and consent-withdrawal handling is still an open
 * question (§11). A youth who leaves the programme has their case exited.
 */
export default function YouthListPage() {
  const { message } = App.useApp();
  const { user } = useAuth();

  const [rows, setRows] = useState<Youth[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [caseFilter, setCaseFilter] = useState<CaseFilter>("all");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Youth | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const canWrite = user?.access.case_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<Youth>>("/youth/", {
        params: {
          page,
          search: search || undefined,
          without_case: caseFilter === "all" ? undefined : caseFilter === "without",
        },
      });
      setRows(response.data.results);
      setCount(response.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load youth records."));
    } finally {
      setLoading(false);
    }
  }, [page, search, caseFilter, message]);

  useEffect(() => {
    void load();
  }, [load]);

  function openForm(youth: Youth | null) {
    setEditing(youth);
    setFormOpen(true);
  }

  const columns: ColumnsType<Youth> = [
    {
      title: "Name",
      key: "name",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.full_name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.phone_number || "no phone"}
          </Typography.Text>
        </Space>
      ),
    },
    { title: "Sex", dataIndex: "sex", width: 90 },
    {
      title: "Age",
      dataIndex: "age",
      width: 120,
      render: (age: number, row) => (
        <Space>
          {age}
          {!row.is_age_eligible && (
            // §11 leaves the band unconfirmed, so this is a flag, not a failure.
            <Tooltip title="Outside the configured youth age band; eligibility needs confirmation">
              <Tag color="orange">Out of band</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    { title: "Woreda", dataIndex: "woreda", width: 130 },
    { title: "Kebele", dataIndex: "kebele", width: 130 },
    {
      title: "Consent",
      dataIndex: "consent_given",
      width: 120,
      render: (given: boolean, row) =>
        given ? <Tag color="green">{row.consent_date}</Tag> : <Tag color="red">Missing</Tag>,
    },
    { title: "Registered", dataIndex: "registration_date", width: 120 },
    ...(canWrite
      ? [
          {
            title: "",
            key: "actions",
            width: 90,
            render: (_: unknown, row: Youth) => (
              <Button type="link" icon={<EditOutlined />} onClick={() => openForm(row)}>
                Edit
              </Button>
            ),
          },
        ]
      : []),
  ];

  return (
    <Card
      title="Youth"
      extra={
        canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openForm(null)}>
            Register a youth
          </Button>
        )
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
        <Segmented
          value={caseFilter}
          onChange={(value) => {
            setCaseFilter(value as CaseFilter);
            setPage(1);
          }}
          options={[
            { value: "all", label: "All" },
            { value: "with", label: "Has a case" },
            { value: "without", label: "No case yet" },
          ]}
        />
      </Space>

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
          showTotal: (total) => `${total} youth`,
        }}
        locale={{
          emptyText: (
            <Typography.Text type="secondary">
              {caseFilter === "without"
                ? "No youth without a case are visible to your role. A case manager's scope resolves through the case, so uncased youth appear only to woreda-scoped roles."
                : "No youth records in your scope."}
            </Typography.Text>
          ),
        }}
      />

      <YouthFormModal open={formOpen} youth={editing} onClose={() => setFormOpen(false)} onSaved={load} />
    </Card>
  );
}
