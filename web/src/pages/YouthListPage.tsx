import { App, Card, Input, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { Paginated, YouthSummary } from "../api/types";

interface YouthRow extends YouthSummary {
  region: string;
  psnp_status: string;
  consent_given: boolean;
  registration_date: string;
  is_age_eligible: boolean;
}

export default function YouthListPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<YouthRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<YouthRow>>("/youth/", {
        params: { page, search: search || undefined },
      });
      setRows(response.data.results);
      setCount(response.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load youth records."));
    } finally {
      setLoading(false);
    }
  }, [page, search, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: ColumnsType<YouthRow> = [
    { title: "Name", dataIndex: "full_name" },
    { title: "Sex", dataIndex: "sex", width: 100 },
    {
      title: "Age",
      dataIndex: "age",
      width: 110,
      render: (age: number, row) => (
        <Space>
          {age}
          {!row.is_age_eligible && <Tag color="orange">Out of band</Tag>}
        </Space>
      ),
    },
    { title: "Woreda", dataIndex: "woreda", width: 140 },
    { title: "Kebele", dataIndex: "kebele", width: 140 },
    { title: "Registered", dataIndex: "registration_date", width: 130 },
  ];

  return (
    <Card title="Youth">
      <Input.Search
        placeholder="Name, phone, or ID"
        allowClear
        style={{ width: 280, marginBottom: 16 }}
        onSearch={(value) => {
          setSearch(value);
          setPage(1);
        }}
      />
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
        locale={{ emptyText: <Typography.Text type="secondary">No youth records in your scope.</Typography.Text> }}
      />
    </Card>
  );
}
