import { App, Input, Modal, Tooltip } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type {
  Paginated,
  ServiceLinkage,
  WltMemberSavingsCompliance,
  WltReadiness,
} from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, Card, CapsLabel, PageHeader } from "../../components/ui";
import {
  CONDITION_TONE,
  LINKAGE_TONE,
  WLT_GROUP_TONE,
} from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import { thresholdFrom } from "./compliance";
import GroupFollowUp from "./GroupFollowUp";
import GroupHistory from "./GroupHistory";
import { GroupLoadFailed, GroupSkeleton, PanelFailed } from "./GroupStates";
import LinkageTimeline from "./LinkageTimeline";
import GroupLoans from "./GroupLoans";
import GroupTabs from "./GroupTabs";
import GroupMeetings from "./GroupMeetings";
import { tabFor } from "./groupTabs";
import GroupRoster from "./GroupRoster";
import { freshness, summarise, type ConditionLine } from "./readinessLayout";

/**
 * The readiness card.
 *
 * The handoff calls immediate feedback at meeting close "most of the module's
 * behaviour-change value", and this is the screen that carries it. One rule
 * governs the whole page: **the actual value always sits next to the
 * threshold**. "Attendance 74% (need 80%)" tells a facilitator what to do next
 * week. A red dot tells her she failed and nothing else.
 *
 * Three states per condition, not two. "Not measurable yet" — no closed
 * meetings, no bylaw — is a different instruction from "below the threshold",
 * and rendering both in red would give the wrong one.
 */
export default function GroupReadinessPage() {
  const { groupId, tab: tabSlug } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState<WltReadiness | null>(null);
  const [linkages, setLinkages] = useState<ServiceLinkage[]>([]);
  const [loading, setLoading] = useState(true);
  /** Which phase gate the card is showing. Empty means the group's next one. */
  const [gateSet, setGateSet] = useState("");
  /** Per-panel failures, keyed by source. A panel that failed says so in place
   *  rather than the page going blank or a toast standing in for the content. */
  const [errors, setErrors] = useState<Record<string, string>>({});
  const tab = tabFor(tabSlug);
  /** For the Meetings badge. The panel itself only mounts on its own tab. */
  const [meetingCount, setMeetingCount] = useState<number | null>(null);
  const [phaseEvents, setPhaseEvents] = useState<PhaseEvent[]>([]);
  const [action, setAction] = useState<"edit" | "submit" | "reject" | null>(
    null,
  );
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [eligibleHere, setEligibleHere] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    // `allSettled`, not `all`. These are four independent reads and one of them
    // failing used to lose the other three — a linkages outage blanked the
    // readiness card, which is the panel the page exists for. Each failure is
    // recorded against its own panel and the rest still render.
    const [readiness, linkageList, phases] = await Promise.allSettled([
      api.get<WltReadiness>(`/wlt/groups/${groupId}/readiness/`, {
        params: { gate_set: gateSet || undefined },
      }),
      api.get<{ results: ServiceLinkage[] }>("/wlt/linkages/", {
        params: { subject_group: groupId, page_size: 200 },
      }),
      api.get<Paginated<PhaseEvent>>("/wlt/phase-events/", {
        params: { group: groupId, page_size: 100 },
      }),
    ]);

    const problems: Record<string, string> = {};

    if (readiness.status === "fulfilled") {
      setData(readiness.value.data);
      // Only worth asking once readiness told us which kebele to ask about.
      try {
        const pool = await api.get<{ results: unknown[] }>(
          "/wlt/profiles/candidates/",
          {
            params: { kebele: readiness.value.data.group.kebele },
          },
        );
        setEligibleHere(pool.data.results.length);
      } catch {
        // A missing "eligible women here" count is a smaller loss than a
        // message about it. The readiness card reads fine without it.
        setEligibleHere(0);
      }
    } else {
      problems.readiness = errorMessage(
        readiness.reason,
        t("wlt.readinessLoadFailed"),
      );
    }

    if (linkageList.status === "fulfilled")
      setLinkages(linkageList.value.data.results ?? []);
    else
      problems.linkages = errorMessage(
        linkageList.reason,
        t("wlt.linkagesLoadFailed"),
      );

    if (phases.status === "fulfilled")
      setPhaseEvents(phases.value.data.results ?? []);
    else
      problems.phases = errorMessage(phases.reason, t("wlt.phasesLoadFailed"));

    setErrors(problems);
    setLoading(false);
  }, [groupId, t, gateSet]);

  useEffect(() => {
    void load();
  }, [load]);

  // A count, not the list: one row fetched for its envelope total, so the badge
  // is right on every tab without the Meetings panel having to be mounted.
  useEffect(() => {
    let cancelled = false;
    void api
      .get<{ count: number }>("/wlt/meetings/", {
        params: { group: groupId, page_size: 1 },
      })
      .then((response) => {
        if (!cancelled) setMeetingCount(response.data.count ?? null);
      })
      .catch(() => {
        // A missing badge is not worth an error message. The tab still opens.
        if (!cancelled) setMeetingCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [groupId]);

  // Skeletons in the shape of the content, not a spinner: the reader learns
  // the page's layout while it loads, and nothing jumps when it arrives.
  if (loading && !data) return <GroupSkeleton />;

  // A readiness failure no longer blanks the page. The record still has a name,
  // and the other tabs still hold their data — losing all of it because one
  // read failed is the fault this replaces.
  if (!data)
    return (
      <GroupLoadFailed
        groupId={String(groupId)}
        detail={errors.readiness}
        onRetry={load}
      />
    );

  const { group, indicators, risk_flags: riskFlags } = data;
  const summary = summarise(data.gate);
  const tone = WLT_GROUP_TONE[group.status];
  const stale = freshness(
    data.computed_at,
    new Date().toISOString().slice(0, 10),
  );
  const memberCompliance = (indicators.savings_compliance_members ??
    []) as WltMemberSavingsCompliance[];
  const pendingPhase = phaseEvents.find((event) => !event.decided_at);
  const canManage = Boolean(user?.access.group_write);
  const canDecide = [
    "WLT_WOREDA_OFFICER",
    "WLT_REGION_OFFICER",
    "WLT_FEDERAL_OFFICER",
    "SYSTEM_ADMIN",
  ].includes(user?.role ?? "");
  const constitutionBlocks =
    summary?.lines
      .filter((line) => line.state !== "met")
      .map((line) => line.sentence) ?? [];

  async function postGroupAction(name: "constitute" | "activate") {
    setSaving(true);
    try {
      await api.post(`/wlt/groups/${groupId}/${name}/`, {});
      message.success(
        name === "constitute" ? "Group constituted." : "Group activated.",
      );
      await load();
    } catch (error) {
      message.error(errorMessage(error, `Could not ${name} the group.`));
    } finally {
      setSaving(false);
    }
  }

  async function saveModalAction() {
    if (!action) return;
    setSaving(true);
    try {
      if (action === "edit") {
        if (!value.trim()) return;
        await api.patch(`/wlt/groups/${groupId}/`, { name: value.trim() });
        message.success("Group details updated.");
      } else if (action === "submit") {
        await api.post("/wlt/phase-events/submit/", {
          group: groupId,
          override_reason: value.trim(),
        });
        message.success("Readiness submitted for phase approval.");
      } else if (pendingPhase) {
        if (!value.trim()) return;
        await api.post(`/wlt/phase-events/${pendingPhase.id}/reject/`, {
          reason: value.trim(),
        });
        message.success("Phase request refused.");
      }
      setAction(null);
      setValue("");
      await load();
    } catch (error) {
      message.error(
        errorMessage(error, "Could not complete the group action."),
      );
    } finally {
      setSaving(false);
    }
  }

  async function approvePhase() {
    if (!pendingPhase) return;
    setSaving(true);
    try {
      await api.post(`/wlt/phase-events/${pendingPhase.id}/approve/`, {});
      message.success("Phase transition approved.");
      await load();
    } catch (error) {
      message.error(
        errorMessage(error, "Could not approve the phase transition."),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page stack group-title">
      <PageHeader
        title={group.name}
        subtitle={
          <span>
            {group.kebele_name} · {group.members_current}{" "}
            {group.members_current === 1 ? "member" : "members"} ·{" "}
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
              {group.status_display}
            </span>
          </span>
        }
      />

      {/* Read-only is stated once, at the top. Write controls are hidden
          rather than disabled everywhere else — a row of dead buttons reads as
          a broken screen, not as a permission. */}
      {!canManage && (
        <div className="callout callout--warn" role="status">
          <p style={{ margin: 0 }}>{t("wlt.readOnlyBanner")}</p>
        </div>
      )}

      <GroupTabs
        groupId={String(groupId)}
        active={tab.slug}
        counts={{
          members: group.members_current,
          meetings: meetingCount ?? undefined,
          linkages: linkages.length,
        }}
      />

      <div
        role="tabpanel"
        id={`group-panel-${tab.slug}`}
        aria-labelledby={`group-tab-${tab.slug}`}
        tabIndex={-1}
        className="stack"
      >
        {/* Group management stays on every tab: constituting, activating and
          submitting for a phase are what the page is opened to do, and burying
          them one tab deep would trade one scroll for one click. */}
        <Card className="card--tight">
          <CapsLabel>Group management</CapsLabel>
          <div
            style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}
          >
            {canManage && (
              <Button
                onClick={() => {
                  setValue(group.name);
                  setAction("edit");
                }}
              >
                Edit group
              </Button>
            )}
            {canManage && group.status === "DRAFT" && (
              /* D12: the reason has to survive a phone and a screen reader. The
               tooltip alone is hover-only, so the same sentence is also a
               native `title`, an `aria-disabled` and a visible line below. */
              <Tooltip
                title={
                  constitutionBlocks.length
                    ? constitutionBlocks.join("; ")
                    : undefined
                }
              >
                <span
                  title={
                    constitutionBlocks.length
                      ? constitutionBlocks.join("; ")
                      : undefined
                  }
                  aria-disabled={constitutionBlocks.length > 0 || undefined}
                >
                  <Button
                    variant="primary"
                    disabled={saving || constitutionBlocks.length > 0}
                    onClick={() => void postGroupAction("constitute")}
                  >
                    Constitute group
                  </Button>
                </span>
              </Tooltip>
            )}
            {canManage && group.status === "CONSTITUTED" && (
              <Button
                variant="primary"
                disabled={saving}
                onClick={() => void postGroupAction("activate")}
              >
                Activate group
              </Button>
            )}
            {canManage &&
              group.status === "ACTIVE" &&
              !pendingPhase &&
              group.current_phase !== "P4" && (
                <Button
                  variant="primary"
                  onClick={() => {
                    setValue("");
                    setAction("submit");
                  }}
                >
                  Submit readiness for next phase
                </Button>
              )}
            <Button onClick={() => void load()}>Recompute readiness</Button>
            <Button
              onClick={() =>
                navigate(`/wlt/linkages?group=${group.id}&propose=1`)
              }
            >
              Manage service linkages
            </Button>
          </div>
          {canManage &&
            group.status === "DRAFT" &&
            constitutionBlocks.length > 0 && (
              <ul
                className="t-meta"
                style={{ margin: "10px 0 0", paddingLeft: 18 }}
              >
                {constitutionBlocks.map((block) => (
                  <li key={block}>{block}</li>
                ))}
              </ul>
            )}

          {pendingPhase && (
            <div style={{ marginTop: 12 }}>
              <div className="t-meta">
                Phase request: {pendingPhase.from_phase || "Not phased"} →{" "}
                {pendingPhase.to_phase}
              </div>
              {canDecide && pendingPhase.submitted_by !== user?.id && (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <Button
                    variant="primary"
                    disabled={saving}
                    onClick={() => void approvePhase()}
                  >
                    Approve phase
                  </Button>
                  <Button
                    variant="destructive-soft"
                    onClick={() => {
                      setValue("");
                      setAction("reject");
                    }}
                  >
                    Refuse phase
                  </Button>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* A stale card that is honest about its age beats a fresh one that is
          wrong — the handoff's rule for offline reading. */}
        {stale && <div className="t-meta">{stale}</div>}

        {tab.slug === "overview" && (
          <div className="group-overview">
            <div className="stack">
              {/* Readiness leads the Overview tab, because it is why the page exists.
          It used to sit at the same weight as a note about former members. */}
              <>
                <Card className="card--tight">
                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "baseline",
                      justifyContent: "space-between",
                    }}
                  >
                    <CapsLabel>{t("wlt.readiness")}</CapsLabel>
                    <span className="t-meta">
                      {group.current_phase
                        ? group.phase_display
                        : t("wlt.noPhase")}
                      {summary
                        ? ` · ${t("wlt.conditionsMet", { met: summary.met, total: summary.total })}`
                        : ""}
                    </span>
                  </div>

                  {/* Only when there is something to look back at. A forming group has
            one gate, and a row of one control is a puzzle rather than a choice. */}
                  {(data?.gate_sets?.length ?? 0) > 1 && (
                    <div
                      className="pill-row"
                      role="group"
                      aria-label={t("wlt.gateSetLabel")}
                      style={{ marginTop: 10 }}
                    >
                      {data?.gate_sets.map((row) => (
                        <button
                          key={row.name}
                          type="button"
                          className="pill-filter"
                          data-active={
                            (data.gate_set ?? "") === row.name
                              ? "true"
                              : undefined
                          }
                          onClick={() =>
                            setGateSet(row.is_next ? "" : row.name)
                          }
                        >
                          {row.label}
                          {row.is_next && (
                            <span className="pill-filter__count">
                              {t("wlt.gateSetNext")}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Said plainly, because the same conditions mean a different thing
            here: this is not "not yet promoted", it is "does it still hold". */}
                  {data?.gate_set &&
                    !data.gate_sets.find((row) => row.name === data.gate_set)
                      ?.is_next && (
                      <p className="t-meta" style={{ marginTop: 8 }}>
                        {t("wlt.gateSetPastHelp")}
                      </p>
                    )}

                  {!summary && <p className="t-meta">{t("wlt.noGate")}</p>}
                  <p className="t-meta">
                    Roster size {group.members_current} (need 15–25) ·{" "}
                    {eligibleHere} eligible{" "}
                    {eligibleHere === 1 ? "woman" : "women"} in this kebele
                  </p>

                  {summary && (
                    <>
                      <p style={{ marginTop: 8 }}>
                        {summary.passed
                          ? t("wlt.gatePassed")
                          : t("wlt.gateOutstanding", {
                              count: summary.outstanding.length,
                            })}
                      </p>
                      <div className="condition-grid">
                        {summary.lines.map((line) => (
                          <ConditionTile key={line.code} line={line} />
                        ))}
                      </div>
                    </>
                  )}
                </Card>
              </>

              {/* What needs chasing, stated in words. */}
              <GroupFollowUp
                groupId={String(groupId)}
                members={memberCompliance}
                conditions={data?.gate?.conditions}
              />

              {/* Five rows and a way through. The full list is one tab away. */}
              <GroupMeetings group={group} compact />
            </div>

            {/* The side column: figures read *about* the group rather than acted on. */}
            <div className="stack">
              <GroupLoans group={group} />
            </div>
          </div>
        )}

        {/* The roster is its own tab now. Several gate conditions are *about* it
          — group size, the office holders — so the readiness card states those
          values, and the names are one click away rather than 1,800px down. */}
        {tab.slug === "members" && (
          <GroupRoster
            group={group}
            onChanged={load}
            compliance={memberCompliance}
            threshold={thresholdFrom(data?.gate?.conditions)}
          />
        )}

        {/* A meeting is registered against the roster, and it is the only thing
          that moves the money figures. */}
        {tab.slug === "meetings" && <GroupMeetings group={group} />}

        {tab.slug === "savings" && <GroupLoans group={group} />}

        {tab.slug === "history" && <GroupHistory group={group} />}

        {/* Three cards became one with three columns. They are read together —
          a fund covering four weeks means one thing beside 91% attendance and
          another beside 60%. */}
        {(tab.slug === "savings" || tab.slug === "overview") && (
          <Card className="card--tight">
            <div className="indicator-cols">
              <IndicatorColumn
                title={t("wlt.savings")}
                rows={[
                  [t("wlt.fund"), `${String(indicators.fund_etb ?? "0")} ETB`],
                  [
                    t("wlt.cash"),
                    `${String(indicators.cash_balance_etb ?? "0")} ETB`,
                  ],
                  [
                    t("wlt.bank"),
                    `${String(indicators.bank_balance_etb ?? "0")} ETB`,
                  ],
                  [
                    t("wlt.fundWeeks"),
                    indicators.fund_weeks_of_contribution === null
                      ? t("wlt.notMeasurable")
                      : t("wlt.weeks", {
                          count: String(indicators.fund_weeks_of_contribution),
                        }),
                  ],
                ]}
              />
              <IndicatorColumn
                title={t("wlt.meetings")}
                rows={[
                  [
                    t("wlt.meetingsHeld"),
                    String(indicators.meetings_held_total ?? 0),
                  ],
                  [
                    t("wlt.attendance"),
                    indicators.attendance_pct === null
                      ? t("wlt.notMeasurable")
                      : `${indicators.attendance_pct}%`,
                  ],
                  [
                    t("wlt.savingsCompliance"),
                    indicators.savings_compliance_pct === null
                      ? t("wlt.notMeasurable")
                      : `${indicators.savings_compliance_pct}%`,
                  ],
                  [
                    t("wlt.lastMeeting"),
                    String(indicators.last_meeting_on ?? "—"),
                  ],
                ]}
              />
              <IndicatorColumn
                title={t("wlt.lending")}
                rows={[
                  [
                    t("wlt.outstanding"),
                    `${String(indicators.loans_outstanding_etb ?? "0")} ETB`,
                  ],
                  [
                    "PAR30",
                    indicators.par30_pct === null
                      ? t("wlt.notMeasurable")
                      : `${indicators.par30_pct}%`,
                  ],
                  [
                    t("wlt.completedCycles"),
                    String(indicators.completed_loan_cycles ?? 0),
                  ],
                ]}
              />
            </div>
          </Card>
        )}

        {tab.slug === "savings" && (
          <Card className="card--tight">
            <CapsLabel>{t("wlt.memberSavingsCompliance")}</CapsLabel>
            <p className="t-meta" style={{ marginTop: 8 }}>
              {t("wlt.memberSavingsComplianceBody")}
            </p>
            {memberCompliance.length === 0 ? (
              <p style={{ marginTop: 12 }}>
                {t("wlt.noSavingsComplianceMembers")}
              </p>
            ) : (
              <div style={{ overflowX: "auto", marginTop: 12 }}>
                <table className="roster-table">
                  <thead>
                    <tr>
                      <th>{t("wlt.memberName")}</th>
                      <th>{t("wlt.savingsMeetingsMet")}</th>
                      <th>{t("wlt.savingsMeetingsExpected")}</th>
                      <th>{t("wlt.complianceRate")}</th>
                      <th>{t("wlt.complianceStatus")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberCompliance.map((member) => (
                      <tr key={member.person_id}>
                        <td style={{ fontWeight: 600 }}>
                          {member.full_name}
                          {!member.is_current && (
                            <span className="t-meta">
                              {" "}
                              · {t("wlt.formerMember")}
                            </span>
                          )}
                        </td>
                        <td>{member.meetings_met}</td>
                        <td>{member.meetings_expected}</td>
                        <td>
                          {member.compliance_pct === null
                            ? t("wlt.notMeasurable")
                            : `${member.compliance_pct}%`}
                        </td>
                        <td style={{ fontWeight: 600 }}>
                          {member.is_compliant
                            ? t("wlt.compliant")
                            : t("wlt.notCompliant")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {riskFlags.length > 0 && (
          <Card className="card--tight">
            <CapsLabel>{t("wlt.atRisk")}</CapsLabel>
            {/* An early warning, not a demotion. It is visible to the facilitator
              and does not by itself move the group backwards. */}
            <p className="t-meta">{t("wlt.atRiskExplainer")}</p>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {riskFlags.map((flag) => (
                <li key={flag.id}>
                  {flag.reason_code.replace(/_/g, " ").toLowerCase()} ·{" "}
                  {flag.raised_on}
                </li>
              ))}
            </ul>
          </Card>
        )}

        {(tab.slug === "linkages" || tab.slug === "overview") && (
          <Card className="card--tight">
            <CapsLabel>{t("wlt.linkages")}</CapsLabel>
            {/* Linkages fail independently of readiness, so this says so here
            rather than the whole page going blank or a toast standing in. */}
            {errors.linkages && (
              <PanelFailed detail={errors.linkages} onRetry={load} />
            )}
            {linkages.length === 0 && (
              <p className="t-meta">{t("wlt.noLinkages")}</p>
            )}
            {linkages.length > 0 && (
              <div style={{ marginTop: 12, marginBottom: 18 }}>
                <LinkageTimeline
                  linkages={linkages}
                  onLinkageClick={(linkage) =>
                    navigate(`/wlt/linkages/${linkage.id}`)
                  }
                />
              </div>
            )}
            {tab.slug === "linkages" && (
              <div className="stack" style={{ marginTop: 8 }}>
                {linkages.map((linkage) => {
                  const linkageTone = LINKAGE_TONE[linkage.status];
                  return (
                    <div key={linkage.id}>
                      <div
                        style={{
                          display: "flex",
                          gap: 12,
                          alignItems: "baseline",
                          justifyContent: "space-between",
                        }}
                      >
                        <strong>{linkage.type_label}</strong>
                        <span
                          className="chip"
                          style={{
                            color: linkageTone.fg,
                            background: linkageTone.bg,
                            borderColor: linkageTone.bd,
                          }}
                        >
                          <span className="chip__mark" aria-hidden>
                            {linkageTone.mark}
                          </span>
                          {linkage.status_display}
                        </span>
                      </div>
                      <div className="t-meta">
                        {linkage.provider_name ?? t("wlt.noProvider")}
                      </div>
                      {linkage.predecessor_label && (
                        <div className="t-meta">
                          Onward from {linkage.predecessor_label}
                        </div>
                      )}
                      {linkage.block_reasons.length > 0 && (
                        <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                          {linkage.block_reasons.map((reason) => (
                            <li key={reason} className="t-meta">
                              {reason}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        )}
      </div>

      <Modal
        open={action !== null}
        title={
          action === "edit"
            ? "Edit group"
            : action === "submit"
              ? "Submit readiness"
              : "Refuse phase request"
        }
        okText={
          action === "edit"
            ? "Save changes"
            : action === "submit"
              ? "Submit"
              : "Refuse"
        }
        confirmLoading={saving}
        onOk={() => void saveModalAction()}
        onCancel={() => {
          setAction(null);
          setValue("");
        }}
      >
        {action === "edit" ? (
          <label>
            <span className="t-caps">Group name</span>
            <Input
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
        ) : (
          <label>
            <span className="t-caps">
              {action === "submit"
                ? "Override reason (only needed when a readiness condition is unmet)"
                : "Reason"}
            </span>
            <Input.TextArea
              rows={3}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
        )}
      </Modal>
    </div>
  );
}
type PhaseEvent = {
  id: string;
  from_phase: string;
  to_phase: string;
  submitted_by: string | null;
  decided_at: string | null;
};

function ConditionTile({ line }: { line: ConditionLine }) {
  const tone = CONDITION_TONE[line.state];
  return (
    <div className="condition-tile">
      <div className="condition-tile__label">
        <span aria-hidden style={{ color: tone.fg }}>
          {tone.mark}
        </span>
        <span>{line.label}</span>
      </div>
      {/* Smaller box, unchanged rule: what it has, then what it needs. The
          threshold stays on every tile because these values are quantitative —
          "91.7%" says nothing without "(need 90%)" beside it. */}
      <div className="condition-tile__value" style={{ color: tone.fg }}>
        {line.state === "unmeasurable" ? "—" : line.actual}
        <span className="t-meta" style={{ fontWeight: 500 }}>
          {" "}
          (need {line.threshold})
        </span>
      </div>
    </div>
  );
}

/** One indicator column — label left, value right, one line rather than two. */
function IndicatorColumn({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, string]>;
}) {
  return (
    <div className="indicator-col">
      <CapsLabel>{title}</CapsLabel>
      {rows.map(([label, value]) => (
        <div key={label} className="indicator-row">
          <span className="t-meta">{label}</span>
          <span className="tabular" style={{ fontWeight: 600 }}>
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}
