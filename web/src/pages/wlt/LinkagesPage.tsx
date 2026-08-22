import {
  App,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Skeleton,
  Switch,
} from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage, formErrors } from "../../api/client";
import type {
  LinkageEvent,
  Paginated,
  ServiceLinkage,
  ServiceLinkageType,
  Summary,
  WltGroup,
} from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import ListPage from "../../components/ListPage";
import Paginator from "../../components/Paginator";
import { Button, Card, CapsLabel, Field, MutedChip } from "../../components/ui";
import { LINKAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";

type Action =
  | "resolution"
  | "submit"
  | "approve"
  | "return"
  | "reject"
  | "activate"
  | "obligation"
  | "cure"
  | "close";
const LABEL: Record<Action, string> = {
  resolution: "Record group resolution",
  submit: "Submit for approval",
  approve: "Approve",
  return: "Return for revision",
  reject: "Reject",
  activate: "Activate linkage",
  obligation: "Log obligation",
  cure: "Record cure",
  close: "Close linkage",
};

const PAGE_SIZE = 25;

function Timeline({
  events,
  loading,
}: {
  events: LinkageEvent[];
  loading: boolean;
}) {
  if (loading) return <Skeleton active paragraph={{ rows: 3 }} />;
  if (!events.length)
    return <div className="t-meta">No evidence has been recorded yet.</div>;
  return (
    <ol
      style={{ listStyle: "none", margin: 0, padding: 0 }}
      aria-label="Linkage timeline"
    >
      {events.map((event, index) => {
        const obligation = event.gate_snapshot?.obligation;
        return (
          <li
            key={event.id}
            style={{
              display: "grid",
              gridTemplateColumns: "18px 1fr",
              gap: 10,
              paddingBottom: 16,
            }}
          >
            <div aria-hidden style={{ position: "relative" }}>
              <span
                style={{
                  display: "block",
                  width: 10,
                  height: 10,
                  borderRadius: 10,
                  background: "var(--green-500)",
                  marginTop: 5,
                }}
              />
              {index < events.length - 1 && (
                <span
                  style={{
                    position: "absolute",
                    top: 17,
                    left: 4,
                    bottom: -11,
                    borderLeft: "1px solid var(--border)",
                  }}
                />
              )}
            </div>
            <div>
              <strong>
                {event.from_status === event.to_status
                  ? "Activity recorded"
                  : `${event.from_status || "Started"} → ${event.to_status}`}
              </strong>
              <div className="t-meta">
                {new Date(event.occurred_at).toLocaleString()}
                {event.actor_name ? ` · ${event.actor_name}` : ""}
              </div>
              {obligation && (
                <div>
                  {obligation.kind} · {obligation.reference} ·{" "}
                  {obligation.missed ? "Missed" : "Met"} ·{" "}
                  {obligation.outstanding ? "Outstanding" : "Settled"}
                </div>
              )}
              {event.reason && <div>{event.reason}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function LinkagesPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [rows, setRows] = useState<ServiceLinkage[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ServiceLinkage | null>(null);
  const [events, setEvents] = useState<LinkageEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [action, setAction] = useState<Action | null>(null);
  const [saving, setSaving] = useState(false);
  const [types, setTypes] = useState<ServiceLinkageType[]>([]);
  const [groups, setGroups] = useState<WltGroup[]>([]);
  const [partners, setPartners] = useState<
    Array<{ id: string; partner_name: string }>
  >([]);
  const [onwardOptions, setOnwardOptions] = useState<ServiceLinkage[]>([]);
  const [form] = Form.useForm();
  const proposalGroup = Form.useWatch("subject_group", form);
  const proposalType = Form.useWatch("linkage_type", form);
  const openedFromGroup = useRef(false);
  const status = params.get("status") ?? "";
  const facilitator = ["WLT_FACILITATOR", "SYSTEM_ADMIN"].includes(
    user?.role ?? "",
  );
  const approver = [
    "WLT_WOREDA_OFFICER",
    "WLT_REGION_OFFICER",
    "WLT_FEDERAL_OFFICER",
    "SYSTEM_ADMIN",
  ].includes(user?.role ?? "");
  const subjectGroup = params.get("group") || undefined;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, counters] = await Promise.all([
        api.get<Paginated<ServiceLinkage>>("/wlt/linkages/", {
          params: {
            page: Number(params.get("page") ?? 1),
            page_size: PAGE_SIZE,
            search,
            status: status || undefined,
            subject_group: subjectGroup,
          },
        }),
        api.get<Summary>("/wlt/linkages/summary/", {
          params: { search, subject_group: subjectGroup },
        }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setSummary(counters.data);
    } catch (e) {
      message.error(errorMessage(e, t("wlt.linkagesLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, subjectGroup, message, t]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (selected) navigate(`/wlt/linkages/${selected.id}`);
  }, [navigate, selected]);
  const loadEvents = useCallback(
    async (row: ServiceLinkage) => {
      setEventsLoading(true);
      try {
        setEvents(
          (await api.get<LinkageEvent[]>(`/wlt/linkages/${row.id}/events/`))
            .data,
        );
      } catch (e) {
        message.error(errorMessage(e, "Could not load the timeline."));
      } finally {
        setEventsLoading(false);
      }
    },
    [message],
  );

  async function openProposal() {
    setProposalOpen(true);
    if (subjectGroup) form.setFieldValue("subject_group", subjectGroup);
    if (types.length) return;
    try {
      const [a, b] = await Promise.all([
        api.get<ServiceLinkageType[]>("/wlt/linkages/types/"),
        api.get<Paginated<WltGroup>>("/wlt/groups/", {
          params: { page_size: 200, status: "ACTIVE" },
        }),
      ]);
      setTypes(a.data);
      setGroups(b.data.results);
      if (subjectGroup) form.setFieldValue("subject_group", subjectGroup);
    } catch (e) {
      message.error(errorMessage(e, "Could not load proposal choices."));
    }
  }
  useEffect(() => {
    if (!proposalOpen || !proposalGroup || !proposalType) {
      setPartners([]);
      return;
    }
    let cancelled = false;
    form.setFieldValue("provider", undefined);
    void api
      .get<Array<{ id: string; name: string }>>(
        "/wlt/linkages/eligible-providers/",
        {
          params: { subject_group: proposalGroup, linkage_type: proposalType },
        },
      )
      .then((response) => {
        if (!cancelled)
          setPartners(
            response.data.map((row) => ({
              id: row.id,
              partner_name: row.name,
            })),
          );
      })
      .catch((error) => {
        if (!cancelled)
          message.error(
            errorMessage(error, "Could not load eligible providers."),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [form, message, proposalGroup, proposalOpen, proposalType]);
  useEffect(() => {
    if (!proposalOpen || !proposalGroup) {
      setOnwardOptions([]);
      return;
    }
    let cancelled = false;
    form.setFieldValue("predecessor", undefined);
    void api
      .get<Paginated<ServiceLinkage>>("/wlt/linkages/", {
        params: { subject_group: proposalGroup, page_size: 200 },
      })
      .then((response) => {
        if (!cancelled) setOnwardOptions(response.data.results);
      })
      .catch((error) => {
        if (!cancelled)
          message.error(
            errorMessage(error, "Could not load earlier linkages."),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [proposalOpen, proposalGroup, form, message]);
  useEffect(() => {
    if (
      facilitator &&
      params.get("propose") === "1" &&
      !openedFromGroup.current
    ) {
      openedFromGroup.current = true;
      void openProposal();
    }
  }, [facilitator, params]);
  async function propose(values: Record<string, unknown>) {
    setSaving(true);
    try {
      const response = await api.post<ServiceLinkage>("/wlt/linkages/", values);
      message.success(
        response.data.status === "BLOCKED"
          ? "Proposal saved. Review what is still needed."
          : "Proposal screened and ready for the group decision.",
      );
      setProposalOpen(false);
      form.resetFields();
      await load();
      setSelected(response.data);
      await loadEvents(response.data);
    } catch (e) {
      const fields = formErrors(e);
      if (fields.length) form.setFields(fields);
      message.error(errorMessage(e, "Could not create the proposal."));
    } finally {
      setSaving(false);
    }
  }
  function actions(row: ServiceLinkage): Action[] {
    const result: Action[] = [];
    if (facilitator && ["SCREENED", "BLOCKED", "RETURNED"].includes(row.status))
      result.push("resolution");
    if (facilitator && ["SCREENED", "BLOCKED"].includes(row.status))
      result.push("submit");
    if (
      approver &&
      row.status === "PENDING_APPROVAL" &&
      row.can_current_user_approve
    )
      result.push("approve", "return", "reject");
    if (facilitator && row.status === "APPROVED") result.push("activate");
    if (facilitator && ["ACTIVE", "DISTRESSED"].includes(row.status))
      result.push("obligation");
    if (
      facilitator &&
      row.status === "DISTRESSED" &&
      !row.terms?.outstanding_obligation
    )
      result.push("cure");
    if (facilitator && ["ACTIVE", "DISTRESSED"].includes(row.status))
      result.push("close");
    return result;
  }
  async function perform(values: Record<string, unknown>) {
    if (!selected || !action) return;
    setSaving(true);
    try {
      const path: Record<Action, string> = {
        resolution: "resolution",
        submit: "submit",
        approve: "approve",
        return: "return",
        reject: "reject",
        activate: "activate",
        obligation: "obligations",
        cure: "cure",
        close: "close",
      };
      const response = await api.post<ServiceLinkage>(
        `/wlt/linkages/${selected.id}/${path[action]}/`,
        values,
      );
      message.success(`${LABEL[action]} completed.`);
      setAction(null);
      form.resetFields();
      setSelected(response.data);
      await Promise.all([load(), loadEvents(response.data)]);
    } catch (e) {
      message.error(
        errorMessage(e, `Could not ${LABEL[action].toLowerCase()}.`),
      );
    } finally {
      setSaving(false);
    }
  }

  const filters = [
    { value: "", label: t("wlt.allLinkages"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).filter((x) => x.count > 0),
  ].map((x) => ({
    value: "value" in x ? String(x.value) : "",
    label: x.label,
    count: x.count,
  }));
  const detailActions = selected ? actions(selected) : [];
  return (
    <>
      <ListPage
        title={t("wlt.linkagesTitle")}
        subtitle={t("wlt.linkagesSubtitle", { count: total })}
        action={
          facilitator ? (
            <Button variant="primary" onClick={() => void openProposal()}>
              Propose linkage
            </Button>
          ) : undefined
        }
        searchPlaceholder={t("wlt.linkagesSearch")}
        empty={{
          when: !loading && rows.length === 0,
          title: t("wlt.noLinkages"),
          body: t("wlt.noLinkagesBody"),
        }}
      >
        {(density) => (
          <>
            <div
              className="pill-row"
              role="group"
              aria-label={t("filters.label")}
              style={{ marginBottom: 20 }}
            >
              {filters.map((filter) => (
                <button
                  key={filter.value || "all"}
                  type="button"
                  className="pill-filter"
                  data-active={filter.value === status ? "true" : undefined}
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    if (filter.value) next.set("status", filter.value);
                    else next.delete("status");
                    setParams(next, { replace: true });
                  }}
                >
                  {filter.label}
                  <span className="pill-filter__count">{filter.count}</span>
                </button>
              ))}
            </div>
            {loading ? (
              <div className="stack" aria-label="Loading linkages">
                <Skeleton active />
                <Skeleton active />
              </div>
            ) : (
              <>
                <div className="only-laptop">
                  <Card className="table-card">
                    <table className={`table ${density}`}>
                      <thead>
                        <tr>
                          <th scope="col">Group</th>
                          <th scope="col">Linkage Type</th>
                          <th scope="col">Provider</th>
                          <th scope="col">Activated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => {
                          const tone = LINKAGE_TONE[row.status];
                          return (
                            <tr
                              key={row.id}
                              onClick={() => {
                                setHistoryOpen(false);
                                setSelected(row);
                                void loadEvents(row);
                              }}
                              style={{ cursor: "pointer" }}
                            >
                              <td className="t-body-strong">
                                {row.subject_name ?? "—"}
                              </td>
                              <td>
                                <div>{row.type_label}</div>
                                <span
                                  className="chip"
                                  style={{
                                    color: tone.fg,
                                    background: tone.bg,
                                    borderColor: tone.bd,
                                    marginTop: 6,
                                  }}
                                >
                                  <span className="chip__mark" aria-hidden>
                                    {tone.mark}
                                  </span>
                                  {row.status_display}
                                </span>
                              </td>
                              <td>
                                {row.provider_name ?? t("wlt.noProvider")}
                              </td>
                              <td>{row.activated_on ?? "—"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </Card>
                </div>

                <div className="only-phone stack">
                  {rows.map((row) => {
                    const tone = LINKAGE_TONE[row.status];
                    return (
                      <Card
                        key={row.id}
                        onClick={() => {
                          setHistoryOpen(false);
                          setSelected(row);
                          void loadEvents(row);
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 12,
                          }}
                        >
                          <div className="t-body-strong">
                            {row.subject_name ?? "—"}
                          </div>
                          <span
                            className="chip"
                            style={{
                              color: tone.fg,
                              background: tone.bg,
                              borderColor: tone.bd,
                            }}
                          >
                            <span className="chip__mark" aria-hidden>
                              {tone.mark}
                            </span>
                            {row.status_display}
                          </span>
                        </div>
                        <Field label="Linkage Type">{row.type_label}</Field>
                        <Field label="Provider">
                          {row.provider_name ?? t("wlt.noProvider")}
                        </Field>
                        <Field label="Activated">
                          {row.activated_on ?? "—"}
                        </Field>
                      </Card>
                    );
                  })}
                </div>

                <Paginator
                  total={total}
                  pageSize={PAGE_SIZE}
                  label={t("wlt.linkagesTitle")}
                />
              </>
            )}
          </>
        )}
      </ListPage>
      <Modal
        open={Boolean(selected)}
        onCancel={() => {
          setHistoryOpen(false);
          setSelected(null);
        }}
        footer={null}
        width={760}
        title={selected?.type_label}
        destroyOnHidden
      >
        {selected && (
          <div className="stack">
            <Card muted>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                  gap: 16,
                }}
              >
                <Field label="Subject">{selected.subject_name || "—"}</Field>
                <Field label="Provider">{selected.provider_name || "—"}</Field>
                <Field label="Opened">{selected.opened_on}</Field>
                <Field label="Value">
                  {selected.value_etb
                    ? `${selected.value_etb} ETB`
                    : "Not recorded"}
                </Field>
              </div>
            </Card>
            {selected.block_reasons.length > 0 &&
              ["BLOCKED", "PENDING_APPROVAL"].includes(selected.status) && (
                <Card>
                  <CapsLabel>
                    {selected.status === "PENDING_APPROVAL"
                      ? "Exception under review"
                      : "Conditions to resolve"}
                  </CapsLabel>
                  <ul>
                    {selected.block_reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                  {selected.status === "BLOCKED" && (
                    <Button
                      disabled={saving}
                      onClick={() => {
                        setSaving(true);
                        api
                          .post<ServiceLinkage>(
                            `/wlt/linkages/${selected.id}/screen/`,
                          )
                          .then((r) => {
                            setSelected(r.data);
                            message.success("Screening refreshed.");
                            return load();
                          })
                          .catch((e) => message.error(errorMessage(e)))
                          .finally(() => setSaving(false));
                      }}
                    >
                      Re-screen now
                    </Button>
                  )}
                </Card>
              )}
            <Card>
              <CapsLabel>Decision & obligation safeguards</CapsLabel>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  flexWrap: "wrap",
                  marginTop: 8,
                }}
              >
                <MutedChip>
                  {selected.terms?.resolution_reference
                    ? `Resolution ${String(selected.terms.resolution_reference)}`
                    : "Resolution not recorded"}
                </MutedChip>
                <MutedChip>
                  {selected.terms?.outstanding_obligation
                    ? "Outstanding obligation"
                    : "No outstanding obligation recorded"}
                </MutedChip>
                {selected.status === "PENDING_APPROVAL" &&
                  selected.next_approval_role && (
                    <MutedChip>
                      Waiting for{" "}
                      {selected.next_approval_role
                        .replaceAll("_", " ")
                        .toLowerCase()}
                    </MutedChip>
                  )}
              </div>
            </Card>
            {detailActions.length > 0 && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {detailActions.map((item, i) => (
                  <Button
                    key={item}
                    variant={
                      i === 0
                        ? "primary"
                        : item === "close"
                          ? "destructive-soft"
                          : "secondary"
                    }
                    onClick={() => {
                      form.resetFields();
                      setAction(item);
                    }}
                  >
                    {LABEL[item]}
                  </Button>
                ))}
              </div>
            )}
            <div>
              <Button
                variant="secondary"
                onClick={() => setHistoryOpen((open) => !open)}
                aria-expanded={historyOpen}
              >
                {historyOpen
                  ? "Hide Evidence & immutable history"
                  : "View Evidence & immutable history"}
              </Button>
              {historyOpen && (
                <div style={{ marginTop: 16 }}>
                  <CapsLabel style={{ marginBottom: 10 }}>
                    Evidence & immutable history
                  </CapsLabel>
                  <Timeline events={events} loading={eventsLoading} />
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={proposalOpen}
        onCancel={() => setProposalOpen(false)}
        title="Propose a service linkage"
        okText="Create and screen"
        onOk={() => form.submit()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <p className="t-meta">
          The proposal is screened immediately against current policy.
        </p>
        <Form form={form} layout="vertical" onFinish={(v) => void propose(v)}>
          <Form.Item
            name="subject_group"
            label="Active group"
            rules={[{ required: true, message: "Choose the group." }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={groups.map((g) => ({
                value: g.id,
                label: `${g.name} · ${g.phase_display}`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="linkage_type"
            label="Linkage type"
            rules={[{ required: true }]}
          >
            <Select
              options={types
                .filter((x) => x.allowed_subject_types.includes("GROUP"))
                .map((x) => ({ value: x.code, label: x.label }))}
            />
          </Form.Item>
          <Form.Item
            name="provider"
            label="Provider"
            extra="Only active providers are shown. Woreda coverage is confirmed before saving."
            rules={[{ required: true }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={partners.map((p) => ({
                value: p.id,
                label: p.partner_name,
              }))}
            />
          </Form.Item>
          <Form.Item name="value_etb" label="Estimated value (ETB)">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="predecessor"
            label="Onward linkage (optional)"
            extra="Choose the earlier linkage that led to this one. Several onward linkages can follow it and run simultaneously."
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={onwardOptions.map((linkage) => ({
                value: linkage.id,
                label: `${linkage.type_label} · ${linkage.provider_name ?? "No provider"} · opened ${linkage.opened_on}`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        open={Boolean(action)}
        onCancel={() => setAction(null)}
        title={action ? LABEL[action] : ""}
        okText={
          action === "approve"
            ? "Approve"
            : action === "close"
              ? "Close linkage"
              : "Save"
        }
        onOk={() => form.submit()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => void perform(v)}
          initialValues={
            action === "obligation"
              ? { outstanding: true, missed: false }
              : undefined
          }
        >
          {action === "resolution" && (
            <>
              <Form.Item
                name="reference"
                label="Minute-book resolution reference"
                rules={[{ required: true }]}
              >
                <Input placeholder="e.g. Meeting 24, item 6" />
              </Form.Item>
              <Form.Item
                name="meeting_id"
                label="Digital meeting ID (optional)"
              >
                <Input />
              </Form.Item>
            </>
          )}
          {action === "submit" && selected?.status === "BLOCKED" && (
            <Form.Item
              name="override_reason"
              label="Override reason"
              extra="Adds another approval level. Credit minimum phase cannot be overridden."
              rules={[{ required: true }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {action === "approve" && (
            <Form.Item name="note" label="Decision note">
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {action === "return" && (
            <Form.Item
              name="reason"
              label="What must be corrected?"
              rules={[{ required: true }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {action === "reject" && (
            <Form.Item
              name="reason"
              label="Rejection reason"
              rules={[{ required: true }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {action === "activate" && (
            <Form.Item
              name={["terms", "reference"]}
              label="Provider agreement / account reference"
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          )}
          {action === "obligation" && (
            <>
              <Form.Item
                name="kind"
                label="Obligation type"
                rules={[{ required: true }]}
              >
                <Select
                  options={["Payment", "Repayment", "Deposit", "Delivery"].map(
                    (x) => ({ value: x.toLowerCase(), label: x }),
                  )}
                />
              </Form.Item>
              <Form.Item
                name="reference"
                label="Reference"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item name="missed" valuePropName="checked">
                <Checkbox>Obligation was missed</Checkbox>
              </Form.Item>
              <Form.Item
                name="outstanding"
                label="Still outstanding"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item name="note" label="Evidence note">
                <Input.TextArea rows={2} />
              </Form.Item>
            </>
          )}
          {action === "cure" && (
            <Form.Item
              name="note"
              label="Cure evidence note"
              rules={[{ required: true }]}
            >
              <Input.TextArea rows={3} />
            </Form.Item>
          )}
          {action === "close" && (
            <>
              <p className="t-meta">
                Closure is refused while an obligation is outstanding. Settle,
                approve a write-off, or transfer it first.
              </p>
              <Form.Item
                name="reason"
                label="Closure reason"
                rules={[{ required: true }]}
              >
                <Input.TextArea rows={3} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </>
  );
}
