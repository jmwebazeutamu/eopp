import { useNavigate } from "react-router-dom";

import { Button, Card, PageHeader } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The group record's loading and failure states.
 *
 * Both exist because the page used to have neither: it showed one line of
 * "Loading…" and then, if any of its four reads failed, nothing at all.
 */

/**
 * Skeletons in the shape of the real content.
 *
 * Not a spinner. A spinner says "wait" and nothing else; a skeleton in the
 * page's own grid teaches the layout while it loads and stops the content
 * jumping when it lands. Sized to the cards it stands in for.
 */
export function GroupSkeleton() {
  const { t } = useLang();
  return (
    <div className="page stack" aria-busy="true">
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--line" style={{ width: 280 }} />
      <div className="skeleton skeleton--tabs" />
      <div className="group-overview">
        <div className="stack">
          <div className="skeleton skeleton--card" style={{ height: 180 }} />
          <div className="skeleton skeleton--card" style={{ height: 220 }} />
        </div>
        <div className="stack">
          <div className="skeleton skeleton--card" style={{ height: 140 }} />
        </div>
      </div>
      {/* Announced once rather than on every block, so a screen reader hears
          "loading the group record", not eight identical placeholders. */}
      <p className="t-meta" role="status">
        {t("wlt.loadingGroup")}
      </p>
    </div>
  );
}

/**
 * The whole record failed to load.
 *
 * What failed, why, and what to do — the pattern §12 asks for. No stack trace
 * and no "something went wrong": the server's own sentence is usually the
 * useful part, so it is shown rather than replaced.
 */
export function GroupLoadFailed({
  groupId,
  detail,
  onRetry,
}: {
  groupId: string;
  detail?: string;
  onRetry: () => void;
}) {
  const { t } = useLang();
  const navigate = useNavigate();

  return (
    <div className="page stack">
      <PageHeader title={t("wlt.groupUnavailable")} subtitle={t("wlt.groupUnavailableBody")} />
      <Card>
        {detail && <p style={{ marginTop: 0 }}>{detail}</p>}
        {/* Two recovery actions, because one of them may not be the answer:
            a transient failure wants a retry, a wrong or out-of-scope id
            wants the list. */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button variant="primary" onClick={onRetry}>
            {t("common.retry")}
          </Button>
          <Button onClick={() => navigate("/wlt/groups")}>{t("wlt.backToGroups")}</Button>
        </div>
        <p className="t-meta" style={{ marginBottom: 0 }}>
          {t("wlt.groupUnavailableRef", { ref: groupId.slice(0, 8) })}
        </p>
      </Card>
    </div>
  );
}

/**
 * One panel failed while the rest of the page is fine.
 *
 * In place of the panel, never as a toast: a message that disappears after
 * three seconds cannot explain why a card is empty for the next ten minutes.
 */
export function PanelFailed({ detail, onRetry }: { detail: string; onRetry?: () => void }) {
  const { t } = useLang();
  return (
    <div className="callout callout--error" role="status">
      <p style={{ margin: 0 }}>{detail}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
