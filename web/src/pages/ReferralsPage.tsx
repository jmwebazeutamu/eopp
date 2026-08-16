import {
  App,
  Badge,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import {
  REFERRAL_STATUS_COLOURS,
  type Paginated,
  type Partner,
  type Referral,
  type ReferralPrompts,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ReferralActionModal, {
  ACTION_LABELS,
  actionsFor,
  useReferralTaxonomy,
  type ReferralAction,
} from "../components/ReferralActions";

/**
 * The cross-case referral queue — spec §4.6, §6.
 *
 * The case screen shows one case's stack (§6.4). This screen is the other half:
 * every referral the user can see, as a work queue. It matters most for the
 * roles §7 scopes to LINKED records — referral partner staff above all, whose
 * scoping resolves through `receiving_partner` and gives them no case access at
 * all, so the case screen is unreachable and this is where their work lives.
 *
 * Rows are scoped by the API, never here.
 */

const PAGE_SIZE = 25;

/** Quick views over the queue. `prompts` is served by its own endpoint. */
type View = "pending" | "active" | "prompts" | "all";

const VIEW_STATUS: Record<Exclude<View, "prompts" | "all">, string> = {
  pending: "PENDING_CONFIRMATION",
  active: "ACTIVE",
};

export default function ReferralsPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const [rows, setRows] = useState<Referral[]>([]);
  const [prompts, setPrompts] = useState<ReferralPrompts>({ onward: [], replacement: [] });
  const [partners, setPartners] = useState<Partner[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [view, setView] = useState<View>("pending");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [partner, setPartner] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ReferralAction | null>(null);

  const { categories } = useReferralTaxonomy();
  const canWrite = user?.access.referral_write ?? false;

  // §7 scopes case records separately from referrals, and the two do not line
  // up: a LINKED-scope role (partner staff, trainers, employer liaison) sees
  // referrals but no case rows, so a link to the case screen would 404. See the
  // §7 questions raised for Phase 1 sign-off.
  const canOpenCases = user ? !["NONE", "LINKED"].includes(user.access.case_scope) : false;

  const promptIds = useMemo(
    () => new Set([...prompts.onward, ...prompts.replacement].map((r) => r.id)),
    [prompts],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The prompt conditions are querysets on the server (§6.2); asking for
      // them rather than recomputing "completed with no child" here keeps one
      // definition, the same one the Sprint 4 alert jobs materialise.
      const promptsRequest = api.get<ReferralPrompts>("/referrals/prompts/");

      if (view === "prompts") {
        const response = await promptsRequest;
        setPrompts(response.data);
        setRows([...response.data.onward, ...response.data.replacement]);
        setCount(response.data.onward.length + response.data.replacement.length);
      } else {
        const [list, promptsResponse] = await Promise.all([
          api.get<Paginated<Referral>>("/referrals/", {
            params: {
              page,
              status: view === "all" ? undefined : VIEW_STATUS[view],
              referral_category: category,
              receiving_partner: partner,
              search: search || undefined,
            },
          }),
          promptsRequest,
        ]);
        setRows(list.data.results);
        setCount(list.data.count);
        setPrompts(promptsResponse.data);
      }
    } catch (error) {
      message.error(errorMessage(error, "Could not load referrals."));
    } finally {
      setLoading(false);
    }
  }, [view, page, category, partner, search, message]);

  useEffect(() => {
    void load();
  }, [load]);

  // The partner filter lists every partner, not just those covering one woreda:
  // this queue spans cases, so narrowing by coverage would hide rows that exist.
  useEffect(() => {
    void (async () => {
      try {
        const response = await api.get<Paginated<Partner>>("/partners/", { params: { page_size: 500 } });
        setPartners(response.data.results);
      } catch {
        // The filter stays empty; everything else on the screen still works.
      }
    })();
  }, []);

  const promptCount = prompts.onward.length + prompts.replacement.length;

  const columns: ColumnsType<Referral> = [
    {
      title: "Youth",
      key: "youth",
      width: 180,
      render: (_, row) =>
        canOpenCases ? (
          <Button type="link" style={{ padding: 0, height: "auto" }} onClick={() => navigate(`/cases/${row.case}`)}>
            {row.youth_name}
          </Button>
        ) : (
          <Typography.Text>{row.youth_name}</Typography.Text>
        ),
    },
    {
      title: "Referral",
      key: "referral",
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Space wrap size={4}>
            <Typography.Text strong>{row.referral_category_label}</Typography.Text>
            {row.referral_trigger !== "MANUAL" && <Tag>{row.trigger_display}</Tag>}
            {row.is_parallel && (
              <Tooltip title="Running concurrently with another referral on this case (spec §6.3)">
                <Tag color="cyan">Parallel</Tag>
              </Tooltip>
            )}
            {!row.counts_toward_parallel_cap && (
              <Tooltip title="Complementary Service runs outside the two-referral cap">
                <Tag color="geekblue">Outside cap</Tag>
              </Tooltip>
            )}
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.receiving_partner_detail.partner_name} · {row.woreda}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Status",
      key: "status",
      width: 190,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Tag color={REFERRAL_STATUS_COLOURS[row.status]}>{row.status_display}</Tag>
          {promptIds.has(row.id) && (
            <Tooltip
              title={
                row.status === "COMPLETED"
                  ? "Completed with nothing following it — §6.2 prompts for an onward referral"
                  : "Failed and not yet replaced — §6.2 prompts for a replacement"
              }
            >
              <Tag color={row.status === "COMPLETED" ? "green" : "volcano"}>Needs a decision</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: "Initiated",
      key: "initiated",
      width: 150,
      render: (_, row) => {
        const days = dayjs().diff(dayjs(row.initiated_date), "day");
        return (
          <Space direction="vertical" size={0}>
            <span>{row.initiated_date}</span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {/* Days waiting, not a verdict: whether a confirmation is overdue
                  is judged by the §4.13 detection job against its configured
                  threshold, and surfaced on the alert inbox. */}
              {row.status === "PENDING_CONFIRMATION"
                ? days === 0
                  ? "sent today"
                  : `waiting ${days} day${days === 1 ? "" : "s"}`
                : `by ${row.initiated_by_name}`}
            </Typography.Text>
          </Space>
        );
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 240,
      render: (_, row) => {
        const kinds = actionsFor(row, canWrite);
        if (!kinds.length) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Space wrap size={4}>
            {kinds.map((kind) => (
              <Button
                key={kind}
                size="small"
                danger={kind === "decline" || kind === "fail"}
                type={promptIds.has(row.id) && (kind === "onward" || kind === "replace") ? "primary" : "default"}
                onClick={() => setAction({ kind, referral: row })}
              >
                {ACTION_LABELS[kind]}
              </Button>
            ))}
          </Space>
        );
      },
    },
  ];

  return (
    <Card
      title="Referrals"
      extra={
        <Space wrap>
          <Radio.Group
            size="small"
            optionType="button"
            value={view}
            onChange={(e) => {
              setView(e.target.value);
              setPage(1);
            }}
          >
            <Radio.Button value="pending">Awaiting confirmation</Radio.Button>
            <Radio.Button value="active">Active</Radio.Button>
            <Radio.Button value="prompts">
              <Space size={6}>
                Needs a decision
                {promptCount > 0 && <Badge count={promptCount} size="small" />}
              </Space>
            </Radio.Button>
            <Radio.Button value="all">All</Radio.Button>
          </Radio.Group>
          <Typography.Text type="secondary">
            {user?.partner_name
              ? user.partner_name
              : user?.access.referral_scope === "OWN_CASELOAD"
                ? "Your caseload"
                : user?.access.referral_scope === "OWN_WOREDA"
                  ? `Woredas: ${user.woreda_assignment.join(", ")}`
                  : "All woredas"}
          </Typography.Text>
        </Space>
      }
    >
      {view === "prompts" ? (
        <Typography.Paragraph type="secondary">
          Referrals that reached an end state and prompt for a next step (spec §6.2). Nothing is created until
          someone confirms — the detection jobs raise the prompt and stop there.
        </Typography.Paragraph>
      ) : (
        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search
            placeholder="Youth or partner name"
            allowClear
            style={{ width: 260 }}
            onSearch={(value) => {
              setSearch(value);
              setPage(1);
            }}
          />
          <Select
            placeholder="All categories"
            allowClear
            style={{ width: 220 }}
            value={category}
            onChange={(value) => {
              setCategory(value);
              setPage(1);
            }}
            options={categories.map((c) => ({ value: c.code, label: c.label }))}
          />
          <Select
            placeholder="All partners"
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: 240 }}
            value={partner}
            onChange={(value) => {
              setPartner(value);
              setPage(1);
            }}
            options={partners.map((p) => ({ value: p.id, label: p.partner_name }))}
          />
        </Space>
      )}

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        expandable={{
          expandedRowRender: (row) => (
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2, lg: 3 }}
              style={{ maxWidth: 1100 }}
              items={[
                { key: "by", label: "Initiated by", children: row.initiated_by_name },
                { key: "contact", label: "Contact at partner", children: row.receiving_contact_name || "—" },
                {
                  key: "confirmation",
                  label: "Confirmation",
                  children: [row.confirmation_status_display, row.confirmed_by, row.confirmed_date]
                    .filter(Boolean)
                    .join(" · "),
                },
                ...(row.outcome_type_label
                  ? [
                      {
                        key: "outcome",
                        label: "Outcome",
                        children: `${row.outcome_type_label} on ${row.outcome_date}`,
                      },
                    ]
                  : []),
                ...(row.outcome_verification_method
                  ? [{ key: "verified", label: "Verified by", children: row.outcome_verification_method }]
                  : []),
                ...(row.failure_reason_label
                  ? [
                      {
                        key: "failure",
                        label: "Failure reason",
                        children: `${row.failure_reason_label} on ${row.failure_date}`,
                      },
                    ]
                  : []),
                ...(row.notes ? [{ key: "notes", label: "Notes", span: 3, children: row.notes }] : []),
              ]}
            />
          ),
        }}
        pagination={
          view === "prompts"
            ? false
            : {
                current: page,
                pageSize: PAGE_SIZE,
                total: count,
                showSizeChanger: false,
                onChange: setPage,
                showTotal: (total) => `${total} referral${total === 1 ? "" : "s"}`,
              }
        }
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                view === "prompts"
                  ? "Nothing waiting on a decision."
                  : view === "pending"
                    ? "No referrals are waiting for a partner to confirm."
                    : "No referrals match this view."
              }
            />
          ),
        }}
      />

      <ReferralActionModal
        action={action}
        woreda={action?.referral?.woreda}
        onClose={() => setAction(null)}
        onDone={load}
      />
    </Card>
  );
}
