import { useEffect, useState } from "react";

import { api } from "../../api/client";
import LanguageSwitch from "../../components/shell/LanguageSwitch";
import { LogoMark } from "../../components/ui";
import { LINKAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import type { StringKey } from "../../i18n/strings";
import LandingIcon, { type LandingIconName } from "./LandingIcon";
import SignInCard from "./SignInCard";
import { phaseRail, statStrip, type Parameters } from "./landingFacts";

/**
 * The public front door — `docs/design_handoff_youth_employment/LANDING_PAGE_BUILD_PROMPT.md`.
 *
 * Built from `Landing_Page_Redesign_v1.html` for layout, spacing and copy. Two
 * classes of deliberate departure, both required by the prompt's own rules:
 *
 * **Numbers.** Every threshold on this page arrives from
 * `GET /wlt/public-parameters/`, never from the markup — see `landingFacts.ts`.
 * The mock's "33 linkage steps" is not among them because no source carries a
 * 33, and the mock's illustrative sync trace ("21 of 23 present", "12.4 weeks")
 * is gone because rule 4 keeps group data off a public page and rule 2 forbids
 * inventing it.
 *
 * **Colour.** The mock ships its own `:root`. This reads `tokens.css`, which
 * the prompt names as the authority where the two disagree, and adds no new
 * variable. The mock's `--on-green` is this repo's `--on-dark`.
 *
 * Dark mode is **not** built. The mock carries a `prefers-color-scheme` block
 * and this codebase has no dark token set at all, so honouring it would mean
 * authoring a second palette for every screen in the application — far outside
 * a landing page, and against rule 1's "add no new colour variables". Flagged
 * rather than half-done.
 */

interface Module {
  key: string;
  icon: LandingIconName;
  titleKey: StringKey;
  bodyKey: StringKey;
  /** Core to the ledger story, so it leads the grid. */
  core?: boolean;
  /** Schema and gates only — stage 9 of the handoff's own sequence. */
  soon?: boolean;
}

const MODULES: Module[] = [
  { key: "ledger", icon: "ledger", titleKey: "landing.modLedger", bodyKey: "landing.modLedgerBody", core: true },
  { key: "gates", icon: "gate", titleKey: "landing.modGates", bodyKey: "landing.modGatesBody", core: true },
  { key: "enrolment", icon: "people", titleKey: "landing.modEnrolment", bodyKey: "landing.modEnrolmentBody" },
  { key: "formation", icon: "addPerson", titleKey: "landing.modFormation", bodyKey: "landing.modFormationBody" },
  { key: "meetings", icon: "calendar", titleKey: "landing.modMeetings", bodyKey: "landing.modMeetingsBody" },
  { key: "portfolio", icon: "bars", titleKey: "landing.modPortfolio", bodyKey: "landing.modPortfolioBody" },
  { key: "structural", icon: "hierarchy", titleKey: "landing.modStructural", bodyKey: "landing.modStructuralBody" },
  { key: "service", icon: "link", titleKey: "landing.modService", bodyKey: "landing.modServiceBody" },
  // Marked, not hidden. Stage 9 is schema and gates only (handoff decision D8),
  // so a card that read like the others would promise a screen nobody can open.
  { key: "credit", icon: "card", titleKey: "landing.modCredit", bodyKey: "landing.modCreditBody", soon: true },
  { key: "approvals", icon: "stamp", titleKey: "landing.modApprovals", bodyKey: "landing.modApprovalsBody" },
  { key: "grievances", icon: "megaphone", titleKey: "landing.modGrievances", bodyKey: "landing.modGrievancesBody" },
  { key: "reporting", icon: "chart", titleKey: "landing.modReporting", bodyKey: "landing.modReportingBody" },
];

/**
 * The roles as `ACCESS_MATRIX` actually declares them, not as the mock lists
 * them.
 *
 * Three corrections, each of which would otherwise send somebody to a woreda
 * office asking for something that cannot be issued. The mock's "CF or DA" is
 * not a role in this build — `DEFINITIONS.md` §3 is explicit that CF/DA are
 * existing PSNP field staff, distinct from WLT facilitators. Its "Programme
 * manager" is described as watching phase progression and portfolio quality,
 * and `PROGRAMME_MANAGER` carries `group_scope: NONE`, so it can see none of
 * that; the WLT federal officer is the role that can. And its heading says
 * "Five roles" above six cards.
 */
interface RoleCard {
  key: string;
  nameKey: StringKey;
  scopeKey: StringKey;
  bodyKey: StringKey;
  landsKey: StringKey;
}

const ROLES: RoleCard[] = [
  { key: "facilitator", nameKey: "landing.roleFacilitator", scopeKey: "landing.roleFacilitatorScope", bodyKey: "landing.roleFacilitatorBody", landsKey: "landing.roleFacilitatorLands" },
  { key: "woreda", nameKey: "landing.roleWoreda", scopeKey: "landing.roleWoredaScope", bodyKey: "landing.roleWoredaBody", landsKey: "landing.roleWoredaLands" },
  { key: "region", nameKey: "landing.roleRegion", scopeKey: "landing.roleRegionScope", bodyKey: "landing.roleRegionBody", landsKey: "landing.roleRegionLands" },
  { key: "federal", nameKey: "landing.roleFederal", scopeKey: "landing.roleFederalScope", bodyKey: "landing.roleFederalBody", landsKey: "landing.roleFederalLands" },
  { key: "mne", nameKey: "landing.roleMne", scopeKey: "landing.roleMneScope", bodyKey: "landing.roleMneBody", landsKey: "landing.roleMneLands" },
  { key: "admin", nameKey: "landing.roleAdmin", scopeKey: "landing.roleAdminScope", bodyKey: "landing.roleAdminBody", landsKey: "landing.roleAdminLands" },
];

const FIELD_NOTES: { key: string; icon: LandingIconName; titleKey: StringKey; bodyKey: StringKey }[] = [
  { key: "offline", icon: "signal", titleKey: "landing.fieldOfflineTitle", bodyKey: "landing.fieldOfflineBody" },
  { key: "storage", icon: "database", titleKey: "landing.fieldStorageTitle", bodyKey: "landing.fieldStorageBody" },
  { key: "literacy", icon: "script", titleKey: "landing.fieldLiteracyTitle", bodyKey: "landing.fieldLiteracyBody" },
];

interface RoadmapEntry {
  key: string;
  tagKey: StringKey;
  titleKey: StringKey;
  bodyKey: StringKey;
  now?: boolean;
}

const ROADMAP: RoadmapEntry[] = [
  { key: "now", tagKey: "landing.roadmapNow", titleKey: "landing.roadmapNowTitle", bodyKey: "landing.roadmapNowBody", now: true },
  { key: "next", tagKey: "landing.roadmapNext", titleKey: "landing.roadmapNextTitle", bodyKey: "landing.roadmapNextBody" },
  { key: "later", tagKey: "landing.roadmapLater", titleKey: "landing.roadmapLaterTitle", bodyKey: "landing.roadmapLaterBody" },
];

/** Twelve, read off the tone table so it cannot drift from `LinkageStatus`. */
const LINKAGE_STATES = Object.keys(LINKAGE_TONE).length;

export default function LandingPage() {
  const { t } = useLang();
  const [parameters, setParameters] = useState<Parameters>({});

  useEffect(() => {
    let live = true;
    // No token, and none needed. A failure leaves the thresholds as em dashes
    // rather than as zeroes, and the rest of the page still reads.
    api
      .get("/wlt/public-parameters/")
      .then((response) => {
        if (live) setParameters(response.data.parameters ?? {});
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  const stats = statStrip(parameters, LINKAGE_STATES);
  const phases = phaseRail(parameters, t);

  return (
    <div className="landing">
      <a className="landing__skip" href="#signin">
        {t("landing.skip")}
      </a>

      <header className="landing__top">
        <div className="landing__wrap landing__topin">
          <a className="landing__brand" href="#top">
            <LogoMark size={34} />
            <span>
              <span className="landing__brandname">{t("app.name")}</span>
              <span className="landing__brandsub">{t("landing.brandSub")}</span>
            </span>
          </a>
          <div className="landing__topright">
            <LanguageSwitch tone="dark" size="comfortable" />
            <a className="landing__topcta" href="#signin">
              {t("landing.signInCta")}
            </a>
          </div>
        </div>
      </header>

      <main id="top">
        <section className="landing__hero">
          <div className="landing__wrap landing__heroin">
            <div className="landing__herocopy">
              <p className="landing__eyebrow">{t("landing.heroEyebrow")}</p>
              <h1>{t("landing.heroTitle")}</h1>
              <p className="landing__lede">{t("landing.heroLede")}</p>
              <ul className="landing__facts">
                <li>
                  <LandingIcon name="signal" />
                  {t("landing.heroFactOffline")}
                </li>
                <li>
                  <LandingIcon name="shield" />
                  {t("landing.heroFactAudit")}
                </li>
                <li>
                  <LandingIcon name="script" />
                  {t("landing.heroFactLangs")}
                </li>
              </ul>
            </div>
            <SignInCard />
          </div>
        </section>

        <section className="landing__strip" aria-label={t("landing.statsLabel")}>
          <div className="landing__wrap landing__stripin">
            {stats.map((stat) => (
              <div key={stat.key} className="landing__stat">
                <p className="landing__statv tabular">{stat.value}</p>
                <p className="landing__statl">{t(stat.labelKey)}</p>
              </div>
            ))}
          </div>
          <p className="landing__wrap landing__statsource">{t("landing.statsSource")}</p>
        </section>

        <section className="landing__band">
          <div className="landing__wrap">
            <div className="landing__bandhead">
              <p className="landing__eyebrow">{t("landing.phasesEyebrow")}</p>
              <h2>{t("landing.phasesTitle")}</h2>
              <p>{t("landing.phasesBody")}</p>
            </div>
            <ol className="landing__rail">
              {phases.map((step, index) => (
                <li key={step.key} className="landing__step">
                  <p className="landing__stepno tabular" aria-hidden>
                    {index + 1}
                  </p>
                  <h3>{t(step.titleKey)}</h3>
                  <p>{t(step.bodyKey)}</p>
                  <ul className="landing__pills">
                    {step.conditions.map((condition) => (
                      <li key={condition.text} className="landing__pill" data-tone={condition.tone ?? "plain"}>
                        {condition.text}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="landing__band landing__band--alt">
          <div className="landing__wrap">
            <div className="landing__bandhead">
              <p className="landing__eyebrow">{t("landing.modulesEyebrow")}</p>
              <h2>{t("landing.modulesTitle")}</h2>
              <p>{t("landing.modulesBody")}</p>
            </div>
            <div className="landing__modules">
              {MODULES.map((module) => (
                <article key={module.key} className="landing__mod" data-core={module.core ? "yes" : undefined}>
                  <span className="landing__modico">
                    <LandingIcon name={module.icon} />
                  </span>
                  <h3>
                    {t(module.titleKey)}
                    {module.soon && <span className="landing__soon">{t("landing.modSoon")}</span>}
                  </h3>
                  <p>{t(module.bodyKey)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="landing__band">
          <div className="landing__wrap">
            <div className="landing__bandhead">
              <p className="landing__eyebrow">{t("landing.rolesEyebrow")}</p>
              <h2>{t("landing.rolesTitle")}</h2>
              <p>{t("landing.rolesBody")}</p>
            </div>
            <div className="landing__roles">
              {ROLES.map((role) => (
                <article key={role.key} className="landing__role">
                  <h3>{t(role.nameKey)}</h3>
                  <p className="landing__rolescope">
                    <span className="sr-only">{t("landing.roleScope")}: </span>
                    {t(role.scopeKey)}
                  </p>
                  <p>{t(role.bodyKey)}</p>
                  <p className="landing__rolelands">
                    <b>{t("landing.roleLands")}</b> {t(role.landsKey)}
                  </p>
                </article>
              ))}
            </div>
            <p className="landing__note">{t("landing.rolesNote")}</p>
          </div>
        </section>

        <section className="landing__band landing__band--alt">
          <div className="landing__wrap landing__field">
            <div>
              <p className="landing__eyebrow">{t("landing.fieldEyebrow")}</p>
              <h2>{t("landing.fieldTitle")}</h2>
              <ul className="landing__fieldlist">
                {FIELD_NOTES.map((note) => (
                  <li key={note.key}>
                    <LandingIcon name={note.icon} size={22} />
                    <div>
                      <h3>{t(note.titleKey)}</h3>
                      <p>{t(note.bodyKey)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="landing__figure">
              <p className="landing__figuret">{t("landing.syncTitle")}</p>
              {/* No times, no counts. The mock's trace was illustrative data on
                  a public page; the shape of the day is the part that is true. */}
              <ol className="landing__sync">
                <li data-state="offline">{t("landing.syncStep1")}</li>
                <li data-state="offline">{t("landing.syncStep2")}</li>
                <li data-state="offline">{t("landing.syncStep3")}</li>
                <li data-state="synced">{t("landing.syncStep4")}</li>
              </ol>
              <p className="landing__figuren">{t("landing.syncNote")}</p>
            </div>
          </div>
        </section>

        <section className="landing__band landing__roadmap">
          <div className="landing__wrap landing__roadmapin">
            <div>
              <p className="landing__eyebrow">{t("landing.roadmapEyebrow")}</p>
              <h2>{t("landing.roadmapTitle")}</h2>
              <p className="landing__roadmapp">{t("landing.roadmapBodyOne")}</p>
              <p className="landing__roadmapp">{t("landing.roadmapBodyTwo")}</p>
            </div>
            <ol className="landing__phases">
              {ROADMAP.map((entry) => (
                <li key={entry.key} className="landing__phase" data-now={entry.now ? "yes" : undefined}>
                  <span className="landing__phasetag">{t(entry.tagKey)}</span>
                  <h3>{t(entry.titleKey)}</h3>
                  <p>{t(entry.bodyKey)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>

      <footer className="landing__foot">
        <div className="landing__wrap">
          <div className="landing__footgrid">
            <div className="landing__footbrand">
              <LogoMark size={30} />
              <p>{t("landing.footBlurb")}</p>
            </div>
            <div>
              <h4>{t("landing.footAccess")}</h4>
              <ul>
                <li>{t("landing.footRequest")}</li>
                <li>
                  <a href="#signin">{t("landing.signInCta")}</a>
                </li>
              </ul>
            </div>
            <div>
              <h4>{t("landing.footSupport")}</h4>
              <ul>
                <li>
                  <a href="/manual.html" target="_blank" rel="noreferrer">
                    {t("landing.footManual")}
                    <span className="sr-only"> {t("shell.opensNewTab")}</span>
                  </a>
                </li>
                <li>
                  <a href="/healthz/">{t("landing.footStatus")}</a>
                </li>
              </ul>
            </div>
          </div>
          <div className="landing__footbottom">
            <span>{t("app.name")}</span>
            <span>{t("landing.footRelease")}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
