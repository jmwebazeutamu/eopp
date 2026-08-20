import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Journey, JourneyStage, JourneyStageState } from "../../api/types";
import { Button, CapsLabel, Card, PageHeader } from "../../components/ui";
import { STAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";

/**
 * One woman's path: registered → verified → in a group → linked.
 *
 * The four stages existed only as services that refuse things. A facilitator
 * found out that a woman was ineligible at the moment she tried to seat her,
 * and was told *that* she was refused rather than which of the conditions was
 * the problem. This is the same set of refusals, read forwards.
 *
 * It follows the readiness card's rule exactly, because it is the same kind of
 * screen and a facilitator should not have to learn it twice: **the actual
 * value always sits next to the threshold**. "ELS grant received: No (need
 * Yes)" tells her what to collect on the next visit.
 *
 * Four states per stage rather than two. `waiting` is not `blocked` — one is a
 * woreda officer's decision and the other is hers — and only `ready` carries a
 * button. A screen that offered a facilitator a button for somebody else's
 * decision would be lying about who is accountable.
 */
export default function JourneyPage() {
  const { profileId } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();

  const [journey, setJourney] = useState<Journey | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Journey>(`/wlt/profiles/${profileId}/journey/`);
      setJourney(response.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.journeyLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [profileId, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !journey) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!journey) return null;

  const next = journey.next_action;

  return (
    <div className="page stack">
      <PageHeader
        title={journey.full_name}
        subtitle={
          <span>
            {t("wlt.journeyTitle")} ·{" "}
            {t("wlt.journeyProgress", { done: journey.stages_done, total: journey.stages_total })}
          </span>
        }
      />

      <Card>
        <CapsLabel>{t("wlt.journeyTitle")}</CapsLabel>
        <p style={{ marginTop: 8 }}>
          {next ? t("wlt.journeyNext", { stage: next.label }) : t("wlt.journeyComplete")}
        </p>
      </Card>

      {journey.stages.map((stage) => (
        <StageCard key={stage.code} stage={stage} onNavigate={navigate} />
      ))}
    </div>
  );
}

/** Written out rather than derived from the state name: a template-literal key
 *  cannot be checked against the string table, which is the whole point of it. */
const STATE_LABEL = {
  done: "wlt.stateDone",
  ready: "wlt.stateReady",
  waiting: "wlt.stateWaiting",
  blocked: "wlt.stateBlocked",
} as const satisfies Record<JourneyStageState, string>;

function StageCard({ stage, onNavigate }: { stage: JourneyStage; onNavigate: (to: string) => void }) {
  const { t } = useLang();
  const tone = STAGE_TONE[stage.state];
  const group = stage.detail.group as string | undefined;
  const groupName = stage.detail.group_name as string | undefined;

  return (
    <Card>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{stage.label}</CapsLabel>
        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
          <span className="chip__mark" aria-hidden>
            {tone.mark}
          </span>
          {t(STATE_LABEL[stage.state])}
        </span>
      </div>

      <ul className="stack" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
        {stage.conditions.map((condition) => {
          const conditionTone = condition.met ? STAGE_TONE.done : STAGE_TONE.blocked;
          return (
            <li
              key={condition.code}
              style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}
            >
              <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span aria-hidden style={{ color: conditionTone.fg }}>
                  {conditionTone.mark}
                </span>
                <span>{condition.label}</span>
              </span>
              {/* The rule this screen shares with the readiness card — what she
                  has, then what she needs — but the threshold is shown only
                  where it is still wanted. Most conditions here are yes/no, and
                  "Yes (need Yes)" is noise on a satisfied row: it says nothing,
                  and at 360px it wraps the rows that *do* need reading. */}
              <span style={{ whiteSpace: "nowrap" }}>
                <strong style={{ color: conditionTone.fg }}>{condition.actual ?? "—"}</strong>
                {!condition.met && <span className="t-meta"> (need {condition.threshold})</span>}
              </span>
            </li>
          );
        })}
      </ul>

      {stage.code === "VERIFIED" && stage.state === "waiting" && (
        <p className="t-meta" style={{ marginTop: 12 }}>
          {t("wlt.awaitingVerification")}
        </p>
      )}

      {stage.code === "GROUPED" && stage.state === "ready" && (
        <p className="t-meta" style={{ marginTop: 12 }}>
          {t("wlt.addToGroupHelp")}
        </p>
      )}

      {stage.code === "GROUPED" && stage.state === "done" && group && (
        <div style={{ marginTop: 12 }}>
          <p className="t-meta">
            {t("wlt.joinedGroupOn", { name: groupName ?? "", date: String(stage.detail.joined_on ?? "") })}
          </p>
          <Button size="sm" onClick={() => onNavigate(`/wlt/groups/${group}`)}>
            {t("wlt.goToGroup")}
          </Button>
        </div>
      )}

      {stage.code === "LINKED" && <LinkageDetail stage={stage} onNavigate={onNavigate} />}
    </Card>
  );
}

type LinkageRow = {
  code: string;
  label: string;
  min_phase_display: string;
  group_phase_display: string;
};

function LinkageDetail({ stage, onNavigate }: { stage: JourneyStage; onNavigate: (to: string) => void }) {
  const { t } = useLang();
  const available = (stage.detail.available_types as LinkageRow[] | undefined) ?? [];
  const blocked = (stage.detail.blocked_types as LinkageRow[] | undefined) ?? [];
  const inPlace =
    (stage.detail.service_linkages as { id: string; type_label: string; status_display: string }[] | undefined) ?? [];

  if (!stage.detail.group) return null;

  return (
    <div className="stack" style={{ marginTop: 12 }}>
      {inPlace.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.currentLinkages")}</CapsLabel>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {inPlace.map((linkage) => (
              <li key={linkage.id}>
                {linkage.type_label} — {linkage.status_display}
              </li>
            ))}
          </ul>
        </div>
      )}

      {available.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.availableLinkages")}</CapsLabel>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {available.map((row) => (
              <li key={row.code}>{row.label}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Named rather than omitted. A facilitator asking why the bank option is
          absent gets the phase it needs, not an empty list. */}
      {blocked.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.blockedLinkages")}</CapsLabel>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {blocked.map((row) => (
              <li key={row.code} className="t-meta">
                {row.label} —{" "}
                {t("wlt.needsPhase", {
                  phase: row.min_phase_display,
                  actual: row.group_phase_display || t("wlt.noPhaseYet"),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <Button size="sm" onClick={() => onNavigate("/wlt/linkages")}>
          {t("wlt.goToLinkages")}
        </Button>
      </div>
    </div>
  );
}
