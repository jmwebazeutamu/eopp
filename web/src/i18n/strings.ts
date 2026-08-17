/**
 * UI string table.
 *
 * The handoff is trilingual — English, Amharic (Ge'ez) and Afaan Oromo (Latin)
 * — and makes the point that a half-translated row is a bug, because the
 * `Next action` column is what staff scan. So the structure is here from the
 * start and every visible string goes through `t()`; only the English table is
 * populated. `am` and `om` are a translation task, not a code task: they need a
 * translator, and inventing Amharic programme copy would be worse than a
 * visible fallback.
 *
 * Adding a language means adding its table and its entry in LANGUAGES — no
 * screen changes.
 */

export const STRINGS = {
  // Shell
  "app.name": "PSNP Youth Employment and Referral Platform",
  "app.subtitle": "Case Management",
  "nav.dashboard": "Dashboard",
  "nav.cases": "Cases",
  "nav.referrals": "Referrals",
  "nav.alerts": "Alerts",
  "nav.registry": "Youth registry",
  "nav.partners": "Partners",
  "nav.users": "Users",
  "nav.signOut": "Sign out",
  "shell.woreda": "Woreda",
  "shell.caseload": "{count} cases",

  // Programme dashboard
  "dash.title": "Programme dashboard",
  "dash.subtitle": "{period} · {scope}",
  "dash.placements": "Placements this quarter",
  "dash.ofTarget": "of {target} target · {percent}%",
  "dash.noTarget": "No quarterly target set",
  "dash.retained": "Retained at 6 months",
  "dash.genderSplit": "Gender split of placements",
  "dash.women": "{percent}% women",
  "dash.men": "{percent}% men",
  "dash.registrationBaseline": "Registration is {percent}% women.",
  "dash.noPlacementsYet": "No placements recorded yet.",
  "dash.funnel": "Registration to placement",
  "dash.lag": "Confirmation lag by partner",
  "dash.lagIntro": "Days from referral sent to partner decision.",
  "dash.lagStandard": "Programme standard is {days}.",
  "dash.lagNone": "No partner has responded to a referral yet.",
  "dash.days": "{days} days",
  "dash.day": "1 day",
  "dash.woredas": "Woreda comparison",
  "dash.woredaMeta": "{registered} registered · {placed} placed",
  "dash.woredaNone": "No youth registered in scope.",
  "dash.openAlerts": "Open alerts",
  "dash.stalledCases": "{count} stalled cases",
  "dash.alertsNone": "No open alerts.",
  "dash.notYet": "Not measurable yet",
  "dash.empty": "No youth registered yet. The funnel fills as intake begins.",

  // Cases list
  "cases.title": "Caseload",
  "cases.subtitle": "{count} results · {name}",
  "cases.search": "Search by name, phone or ID",
  "cases.all": "All",
  "cases.col.name": "Name",
  "cases.col.status": "Status",
  "cases.col.woreda": "Woreda",
  "cases.col.manager": "Case manager",
  "cases.col.activity": "Last activity",
  "cases.col.next": "Next action",
  "cases.nextAction": "Next action",
  "cases.lastActivity": "Last activity",
  "cases.none": "No cases match these filters.",
  "cases.new": "New case",

  // Case detail
  "case.eyebrow": "Case {ref} · {woreda} woreda",
  "case.pathway": "Pathway: {pathway}",
  "case.noPathway": "No pathway assigned yet",
  "case.pathwayHeading": "Pathway",
  "case.revisePathway": "Revise",
  "case.revisionHistory": "Revision history",
  "case.assessedBy": "Assessed {date} by {name}",
  "case.superseded": "Superseded: {reason}",
  "case.current": "Current",
  "case.nextAction": "Next action",
  "case.noNextAction": "No next action recorded.",
  "case.setNextAction": "Set next action",
  "case.identity": "Youth identity",
  "case.profiling": "Profiling & eligibility",
  "case.age": "Age",
  "case.sex": "Sex",
  "case.dob": "Date of birth",
  "case.kebele": "Kebele",
  "case.phone": "Phone",
  "case.reveal": "Reveal",
  "case.hide": "Hide",
  "case.consent": "Consent recorded {date}",
  "case.noConsent": "No consent date recorded",
  "case.verified": "Verified",
  "case.selfReported": "Self-reported",
  "case.notRequired": "Not required",
  "case.noProfiling": "No profiling record yet.",
  "case.slots": "Parallel referral slots",
  "case.slotsInUse": "{used} of {limit} parallel referrals in use",
  "case.slot": "Slot {n}",
  "case.slotFree": "Free",
  "case.exempt": "Exempt",
  "case.exemptNote": "Complementary Service referrals are exempt — they never use a slot",
  "case.newReferral": "New referral",
  "case.newReferralBlocked": "New referral (blocked)",
  "case.limitReached": "Parallel limit reached — close or withdraw a referral first",
  "case.timeline": "Referral timeline {year}",
  "case.history": "Referral history",
  "case.noReferrals": "No referrals yet",
  "case.back": "Back to cases",
  "case.edit": "Edit case",
  "case.noSlot": "No slot used",
  "case.usesSlot": "Uses a slot",
  "case.waiting": "waiting {days} days",

  // Referral actions
  "referral.confirmed": "Partner confirmed",
  "referral.declined": "Partner declined",
  "referral.withdraw": "Withdraw referral",
  "referral.complete": "Record outcome",
  "referral.fail": "Record failure",
  "referral.onward": "Onward referral",
  "referral.replace": "Replacement referral",

  // Referrals queue
  "queue.title": "Referrals queue",
  "queue.subtitle": "Decision inbox · {woredas}",
  "queue.needsDecision": "Needs a decision",
  "queue.awaiting": "Awaiting confirmation",
  "queue.active": "Active",
  "queue.empty": "Nothing waiting on a decision.",
  "queue.col.youth": "Youth",
  "queue.col.referral": "Referral",
  "queue.col.waiting": "Waiting",
  "queue.col.decision": "Decision",

  // Alerts
  "alerts.title": "Alerts",
  "alerts.subtitle": "Tap a counter to filter. {count} open across {woredas} woredas.",
  "alerts.showAll": "Show all alerts",
  "alerts.emptyTitle": "No alerts of this type",
  "alerts.emptyBody": "Nothing here needs attention right now. Alerts are raised by scheduled checks, not by anything you did.",
  "alerts.today": "today",
  "alerts.days": "{days} days",
  "alerts.action": "Mark actioned",
  "alerts.dismiss": "Dismiss",

  // Youth registry
  "registry.title": "Youth registry",
  "registry.subtitle": "{registered} registered · {withCase} with an open case. Phone numbers hidden by default.",
  "registry.openCase": "Open case",
  "registry.noCase": "No case",
  "registry.consent": "Consent",
  "registry.col.id": "ID",
  "registry.edit": "Edit record",
  "registry.goToCase": "Open case",
  "registry.region": "Region · zone",
  "registry.household": "Household ID",
  "registry.psnp": "PSNP status",
  "registry.education": "Education",
  "registry.disability": "Disability",
  "registry.noConsentRecorded": "No consent recorded.",
  "registry.registeredBy": "Registered {date} by {name}",
  "registry.outsideAgeBand": "Outside age band",
  "registry.col.case": "Case",
  "registry.register": "Register youth",

  // Bulk intake from a woreda register
  "registry.import": "Import from Excel",
  "import.title": "Import youth from Excel",
  "import.intro": "Upload a woreda register as .xlsx. Every row is checked before anything is saved.",
  "import.template": "Download the template",
  "import.templateHint": "The template carries the column names and allowed values on a second sheet.",
  "import.choose": "Choose a file",
  "import.change": "Choose a different file",
  "import.consentNote":
    "Consent must already be recorded for every youth in the file. Rows without it cannot be imported (spec §9).",
  "import.checking": "Checking the file…",
  "import.saving": "Saving…",
  "import.countNew": "{count} to import",
  "import.countDuplicate": "{count} already on file",
  "import.countError": "{count} cannot be imported",
  "import.outcome.new": "New",
  "import.outcome.duplicate": "Already on file",
  "import.outcome.error": "Cannot import",
  "import.row": "Row {row}",
  "import.commit": "Import {count} youth",
  "import.blocked": "Fix the rows below in the spreadsheet, then upload it again. Nothing has been saved.",
  "import.allDuplicates": "Every row is already on file. There is nothing to import.",
  "import.done": "{count} youth imported.",
  "import.doneNone": "Nothing was imported.",
  "import.skipped": "{count} rows were already on file and were skipped.",
  "import.checkAge": "{count} imported youth fall outside the age band and need eligibility confirmed.",
  "import.unnamed": "(no name)",

  // Partners
  "partners.title": "Partners and providers",
  "partners.coverage": "Coverage",
  "partners.contact": "Contact",
  "partners.liveReferrals": "Live referrals",
  "partners.accepting": "Accepting referrals",
  "partners.paused": "Paused",
  "partners.add": "Add partner",
  "partners.edit": "Edit partner",
  "partners.email": "Email",
  "partners.notes": "Performance notes",
  "partners.noCoverage": "No woredas recorded.",

  // Users
  "users.title": "Users",
  "users.scope": "Scope",
  "users.add": "Add user",
  "users.edit": "Edit account",
  "users.username": "Username",
  "users.caseload": "Open caseload",
  "users.lastSeen": "Last signed in",
  "users.neverSignedIn": "Never signed in",
  "users.allWoredas": "All woredas",
  "users.joined": "Account created {date}",
  "users.suspended": "Suspended",

  // Generic
  "common.loading": "Loading…",
  "common.cancel": "Cancel",
  "common.save": "Save",
  "common.none": "—",
} as const;

export type StringKey = keyof typeof STRINGS;

export type Translations = Partial<Record<StringKey, string>>;

/** Amharic and Afaan Oromo tables land here when translation is delivered. */
export const AM: Translations = {};
export const OM: Translations = {};
