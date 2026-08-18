import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Partner } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import FilterChips, { SearchBox } from "../components/FilterChips";
import PartnerDetailModal, { MOU_TONE } from "../components/PartnerDetailModal";
import PartnerFormModal from "../components/PartnerFormModal";
import { Button, CapsLabel, Card, Field, MutedChip, PageHeader } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

/**
 * Partners and providers — stacked cards, per the handoff.
 *
 * The MOU chip is the thing supervisors look for, so it sits top-right on every
 * card rather than in a column someone has to scroll to. Its tone follows the
 * status system: signed is green, a draft is gold (waiting), and no MOU is
 * terracotta — a gap to close, not a failure.
 */


export default function PartnersPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();

  const [params] = useSearchParams();
  const [rows, setRows] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<Partner | null>(null);
  const [editing, setEditing] = useState<Partner | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  // §7 gives partner records to the system administrator; everyone else reads.
  const canWrite = user?.role === "SYSTEM_ADMIN";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<Partner>>("/partners/", {
        params: {
          page_size: 200,
          search: params.get("q") || undefined,
          active_status: params.get("active_status") ?? undefined,
          mou_status: params.get("mou_status") ?? undefined,
        },
      });
      setRows(response.data.results);
    } catch (error) {
      message.error(errorMessage(error, "Could not load partners."));
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page stack">
      <PageHeader
        title={t("partners.title")}
        subtitle={`${rows.length} partners`}
        action={
          canWrite ? (
            <Button
              variant="primary"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              {t("partners.add")}
            </Button>
          ) : undefined
        }
      />

      <SearchBox placeholder="Search by name, contact or email" />

      <FilterChips resource="/partners" />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {rows.map((partner) => {
          const tone = MOU_TONE[partner.mou_status];
          return (
            /* Any role may open the record; only some may then edit it. */
            <Card key={partner.id} onClick={() => setViewing(partner)}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <CapsLabel>{partner.partner_type_display}</CapsLabel>
                  <div className="t-card-title">{partner.partner_name}</div>
                </div>
                <span
                  className="chip"
                  style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}
                  title={partner.mou_date ? `MOU dated ${partner.mou_date}` : undefined}
                >
                  {partner.mou_status_display}
                </span>
              </div>

              <div className="card__rule" />

              <div className="grid-pairs">
                <Field label={t("partners.coverage")}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {partner.woreda_coverage.length ? (
                      partner.woreda_coverage.map((woreda) => (
                        <MutedChip key={woreda} style={{ fontSize: 12 }}>
                          {woreda}
                        </MutedChip>
                      ))
                    ) : (
                      <span className="t-meta">{t("common.none")}</span>
                    )}
                  </div>
                </Field>

                <Field label={t("partners.contact")}>
                  <div style={{ fontSize: 14 }}>{partner.contact_name || t("common.none")}</div>
                  <div className="t-meta tabular">{partner.phone}</div>
                </Field>

                <Field label="Status">
                  <span
                    style={{
                      color: partner.can_receive_referrals ? "var(--green-ink)" : "var(--ink-400)",
                      fontWeight: 600,
                      fontSize: 14,
                    }}
                  >
                    {partner.can_receive_referrals ? `● ${t("partners.accepting")}` : `○ ${t("partners.paused")}`}
                  </span>
                </Field>
              </div>

              {partner.performance_notes && (
                <div className="t-meta" style={{ marginTop: 8 }}>
                  {partner.performance_notes}
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <PartnerDetailModal
        partner={viewing}
        canEdit={canWrite}
        onClose={() => setViewing(null)}
        onEdit={(partner) => {
          setViewing(null);
          setEditing(partner);
          setFormOpen(true);
        }}
      />

      <PartnerFormModal
        open={formOpen}
        partner={editing}
        onClose={() => setFormOpen(false)}
        onSaved={() => {
          setFormOpen(false);
          void load();
        }}
      />
    </div>
  );
}
