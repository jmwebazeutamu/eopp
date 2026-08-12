import { App, Card, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { MouStatus, Paginated, Partner } from "../api/types";

const MOU_COLOURS: Record<MouStatus, string> = {
  NONE: "default",
  DRAFT: "orange",
  SIGNED: "green",
  EXPIRED: "red",
  TERMINATED: "red",
};

/** Partner directory — spec §4.11. Read-only here; §7 gives writes to the
 *  programme manager and system administrator, who use the Django admin. */
export default function PartnersPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Partner[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [type, setType] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<Partner>>("/partners/", {
        params: { page, search: search || undefined, partner_type: type },
      });
      setRows(response.data.results);
      setCount(response.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load partners."));
    } finally {
      setLoading(false);
    }
  }, [page, search, type, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ColumnsType<Partner> = [
    {
      title: "Organisation",
      key: "name",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{row.partner_name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.partner_type_display}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Coverage",
      dataIndex: "woreda_coverage",
      render: (values: string[]) => values.map((w) => <Tag key={w}>{w}</Tag>),
    },
    {
      title: "Contact",
      key: "contact",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <span>{row.contact_name}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.phone}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "MOU",
      dataIndex: "mou_status",
      width: 140,
      render: (value: MouStatus, row) => (
        <Space direction="vertical" size={0}>
          <Tag color={MOU_COLOURS[value]}>{row.mou_status_display}</Tag>
          {row.mou_date && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {row.mou_date}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "Referrals",
      dataIndex: "can_receive_referrals",
      width: 130,
      render: (value: boolean) =>
        value ? <Tag color="green">Accepting</Tag> : <Tag color="default">Inactive</Tag>,
    },
  ];

  return (
    <Card title="Partners and providers">
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="Name, contact, or email"
          allowClear
          style={{ width: 280 }}
          onSearch={(value) => {
            setSearch(value);
            setPage(1);
          }}
        />
        <Select
          placeholder="All types"
          allowClear
          style={{ width: 260 }}
          value={type}
          onChange={(value) => {
            setType(value);
            setPage(1);
          }}
          options={[
            { value: "TVET_INSTITUTION", label: "TVET Institution" },
            { value: "EMPLOYER", label: "Employer" },
            { value: "ENTERPRISE_DEVELOPMENT_AGENCY", label: "Enterprise Development Agency" },
            { value: "SAVINGS_GROUP", label: "Savings Group" },
            { value: "HEALTH_SERVICE", label: "Health Service" },
            { value: "PSYCHOSOCIAL_SERVICE", label: "Psychosocial Service" },
            { value: "LEGAL_AID", label: "Legal Aid" },
            { value: "FINANCE_INSTITUTION", label: "Finance Institution" },
            { value: "OTHER", label: "Other" },
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
          showTotal: (total) => `${total} partner${total === 1 ? "" : "s"}`,
        }}
      />
    </Card>
  );
}
