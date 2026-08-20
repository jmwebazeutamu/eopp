import { App, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Referral } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, CapsLabel, MutedChip } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

/**
 * The M&E screen — §10 Sprint 6, "screens for M&E staff".
 *
 * It exists because of one gap. §8.3 makes the **externally verified** subset
 * of outcomes the reportable headline, and until Sprint 6 there was no way to
 * move an outcome into that subset: verification was a field somebody typed.
 * A follow-up that reached the youth is now the route, so the difference between
 * the recorded rate and the reportable one is a queue with a number on it
 * rather than a permanent shortfall.
 *
 * Two queues, in the order the work happens: contact the youth, then verify what
 * she said. Recording the contact is a case manager's job and appears here too,
 * because M&E is who notices that nobody has done it.
 */
export default function VerificationPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const [unverified, setUnverified] = useState<Referral[]>([]);
  const [due, setDue] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState<Referral | null>(null);
  const [source, setSource] = useState("PROVIDER_CONFIRMED");
  const [busy, setBusy] = useState(false);

  const view = params.get("view") ?? "unverified";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [outcomes, contacts] = await Promise.all([
        api.get<Paginated<Referral>>("/followups/unverified/", { params: { page_size: 200 } }),
        api.get<Paginated<Referral>>("/followups/due/", { params: { page_size: 200 } }),
      ]);
      setUnverified(outcomes.data.results ?? []);
      setDue(contacts.data.results ?? []);
    } catch (error) {
      message.error(errorMessage(error, t("verification.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setView(next: string) {
    const updated = new URLSearchParams(params);
    updated.set("view", next);
    setParams(updated, { replace: true });
  }

  async function submitVerification() {
    if (!verifying) return;
    setBusy(true);
    try {
      // Verification hangs off a follow-up, not off the referral: §6.2 verifies
      // an outcome "via follow-up visit", and a verification with no contact
      // behind it is the self-reported figure wearing a better label.
      const contact = await api.post("/followups/", {
        case: verifying.case,
        related_referral: verifying.id,
        contact_method: "PHONE",
        contact_outcome: "REACHED_ENGAGED",
        notes: t("verification.contactNote"),
      });
      await api.post(`/followups/${contact.data.id}/verify/`, { verification_source: source });
      message.success(t("verification.verified"));
      setVerifying(null);
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("verification.verifyFailed")));
    } finally {
      setBusy(false);
    }
  }

  const canWrite = Boolean(user?.access.case_write);

  return (
    <ListPage
      title={t("verification.title")}
      subtitle={t("verification.subtitle", { unverified: unverified.length, due: due.length })}
      searchPlaceholder={t("verification.search")}
      empty={{
        when: !loading && unverified.length === 0 && due.length === 0,
        title: t("verification.empty"),
        body: t("verification.emptyBody"),
      }}
    >
      {() => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
            <button
              type="button"
              className="pill-filter"
              data-active={view === "unverified" ? "true" : undefined}
              onClick={() => setView("unverified")}
            >
              {t("verification.unverified")}
              <span className="pill-filter__count">{unverified.length}</span>
            </button>
            <button
              type="button"
              className="pill-filter"
              data-active={view === "due" ? "true" : undefined}
              onClick={() => setView("due")}
            >
              {t("verification.contactDue")}
              <span className="pill-filter__count">{due.length}</span>
            </button>
          </div>

          <Card className="card--muted" style={{ marginBottom: 16 }}>
            {/* The whole reason this screen exists, said once. */}
            {t("verification.explainer")}
          </Card>

          <div className="stack">
            {(view === "unverified" ? unverified : due).map((referral) => (
              <Card key={referral.id}>
                <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                  <div>
                    <strong>{referral.youth_name}</strong>
                    <div className="t-meta">
                      {referral.referral_category_label} · {referral.receiving_partner_detail.partner_name}
                    </div>
                  </div>
                  <MutedChip>
                    {view === "unverified"
                      ? referral.outcome_type_label ?? t("verification.outcomeRecorded")
                      : t("verification.activeSince", { date: referral.confirmed_date ?? referral.initiated_date })}
                  </MutedChip>
                </div>

                {view === "unverified" && (
                  <div className="t-meta" style={{ marginTop: 6 }}>
                    <CapsLabel>{t("verification.currentSource")}</CapsLabel>{" "}
                    {referral.verification_source || t("verification.noSource")}
                  </div>
                )}

                {canWrite && view === "unverified" && (
                  <div style={{ marginTop: 10 }}>
                    <Button size="compact" variant="primary" onClick={() => setVerifying(referral)}>
                      {t("verification.record")}
                    </Button>
                  </div>
                )}
              </Card>
            ))}
          </div>

          <Modal
            open={verifying !== null}
            title={t("verification.record")}
            okText={t("common.save")}
            cancelText={t("common.cancel")}
            confirmLoading={busy}
            onCancel={() => setVerifying(null)}
            onOk={() => void submitVerification()}
          >
            <p>{t("verification.modalBody")}</p>
            <Select
              value={source}
              onChange={(next) => setSource(next)}
              style={{ width: "100%" }}
              options={[
                { value: "PROVIDER_CONFIRMED", label: t("verification.providerConfirmed") },
                { value: "EMPLOYER_CONFIRMED", label: t("verification.employerConfirmed") },
                { value: "DOCUMENT_VERIFIED", label: t("verification.documentVerified") },
                // Recorded, and deliberately still not verification: §8.3's
                // headline counts only what somebody other than the youth
                // stood behind.
                { value: "SELF_REPORTED", label: t("verification.selfReported") },
              ]}
            />
          </Modal>
        </>
      )}
    </ListPage>
  );
}
