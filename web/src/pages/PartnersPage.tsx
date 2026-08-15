import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import { PARTNER_TYPE_OPTIONS, type MouStatus, type Paginated, type Partner } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import PartnerFormModal from "../components/PartnerFormModal";

const MOU_COLOURS: Record<MouStatus, string> = {
  NONE: "default",
  DRAFT: "orange",
  SIGNED: "green",
  EXPIRED: "red",
  TERMINATED: "red",
};

/**
 * Partner directory — spec §4.11.
 *
 * Every operational user reads it (a case manager choosing a referral
 * destination needs to). Writing is limited to the roles that own partner
 * relationships. Deletion is not offered at all: referral history and the §8
 * partner performance dashboards depend on the record, so a partner that stops
 * taking referrals is deactivated instead.
 */
export default function PartnersPage() {
  const { message } = App.useApp();
  const { user } = useAuth();
  const [editing, setEditing] = useState<Partner | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  // §7 does not cover Partner, which is organisational reference data rather
  // than case content. Writes are limited to the roles that own partner
  // relationships; the API enforces the same set independently.
  const canWrite = user?.role === "SYSTEM_ADMIN" || user?.role === "PROGRAMME_MANAGER";
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
    ...(canWrite
      ? [
          {
            title: "",
            key: "actions",
            width: 90,
            render: (_: unknown, row: Partner) => (
              <Button type="link" icon={<EditOutlined />} onClick={() => openForm(row)}>
                Edit
              </Button>
            ),
          },
        ]
      : []),
  ];

  function openForm(partner: Partner | null) {
    setEditing(partner);
    setFormOpen(true);
  }

  return (
    <Card
      title="Partners and providers"
      extra={
        canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openForm(null)}>
            New partner
          </Button>
        )
      }
    >
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
          options={PARTNER_TYPE_OPTIONS}
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

      <PartnerFormModal
        open={formOpen}
        partner={editing}
        onClose={() => setFormOpen(false)}
        onSaved={load}
      />
    </Card>
  );
}
