# Youth Employment Case Management and Referral Platform: Development Specification

Companion document to the World Bank Ethiopia Concept Note (v6, August 2026) and Technical Specification (v2, August 2026).
Draft v1, August 2026.

## How to Use This Document

This is the authoritative specification for building the platform. If you are a coding agent or engineer starting from this file, follow these rules:

1. Build in the sprint order in [Sprint Plan and Development Roadmap](#10-sprint-plan-and-development-roadmap). Do not skip ahead to a later sprint's entities before an earlier sprint's foundations exist.
2. Treat [Entity Field Definitions](#4-entity-field-definitions) as the source of truth for the database schema. Field type notes below tell you how to translate each conceptual type into a Django model field.
3. Treat [Referral State Machine and Business Rules](#6-referral-state-machine-and-business-rules) as the source of truth for business logic. Unit test every transition in the table before considering a sprint done.
4. The tech stack in [Section 2](#2-technology-stack) is fixed. Do not substitute a different framework, database, or hosting approach without asking first.
5. Do not silently resolve anything listed in [Open Questions for Phase 1 Sign-Off](#11-open-questions-for-phase-1-sign-off). Flag it and ask, or implement the stated working default and leave a `# TODO(open-question)` comment pointing at this file.
6. Keep the referral state machine as explicit application code (services/domain layer), not database triggers or stored procedures, so it stays auditable and testable.

---

## 1. Purpose and Scope

This document turns the design in the Concept Note into a data model and referral engine specification a development team (human or AI-assisted) can build against directly. It covers the entity list, field definitions, referral taxonomy, state machine, technology stack, and a sprint-by-sprint development plan for the custom-built platform.

Scope covers the full platform: the youth and case record, all twelve functional modules from Concept Note Table 1, and the referral and linkage engine that connects them. The referral engine gets the most detail because it is the module active across the full case lifecycle, and the one every other module feeds into.

Out of scope: UI wireframes, detailed security architecture, and a fully specified offline synchronisation protocol. See [Section 11](#11-open-questions-for-phase-1-sign-off) for where these depend on decisions still to be made.

---

## 2. Technology Stack

Custom-built application, containerised with Docker, backed by PostgreSQL. Not a platform configured from an existing open-source case management base (Primero, DHIS2 Tracker, and CommCare were considered and ruled out).

| Layer | Recommendation | Why |
|---|---|---|
| Backend | Django + Django REST Framework (Python) | The ORM fits the self-referencing referral model in [4.6](#46-referral-the-core-entity) directly. The built-in admin doubles as the taxonomy configuration tool called for in [Section 9](#9-non-functional-and-implementation-notes). |
| Database | PostgreSQL | Runs the relational model directly; use row-level constraints to protect referral state integrity. |
| Local dev platform | Multipass (Ubuntu VM) running Docker Compose | Every engineer develops inside an identical Linux environment regardless of host OS. Mirrors staging and production containers closely. |
| Background jobs | Celery + Redis | Drives stall detection, onward and replacement referral prompts, and 30/60/90-day retention reminders. |
| API | REST via DRF, OpenAPI schema (drf-spectacular) | Versioned, documented endpoints. Supports delta sync (`updated_since` parameters) for the mobile app. |
| Auth | JWT (`djangorestframework-simplejwt`) for the pilot | Low operational overhead at pilot scale (~20 users across 2-3 woredas). Self-hosted Keycloak is the scale-up path. |
| Web frontend | React + TypeScript, Ant Design components | Case manager screen, referral stack timeline, supervisor and programme manager dashboards. |
| Mobile / offline | Flutter, local SQLite (Drift), background sync | Field devices need true offline-first behaviour for intake, follow-up, and referral updates in low-connectivity woredas. |
| Reverse proxy / TLS | Traefik | Auto-discovers Docker services, handles Let's Encrypt certificates with minimal Compose configuration. |
| Object storage | MinIO (self-hosted, Dockerized) | Photos, consent forms, business plan documents stay in-country (data sovereignty). |
| Reporting / BI | Metabase (Dockerized, read-only connection to Postgres) | Covers all nine dashboards in [Section 8](#8-dashboard-and-reporting-data-requirements) without custom dashboard development. |
| CI/CD | GitHub Actions (or self-hosted GitLab CI) | Builds images, pushes to a private registry, deploys via Compose. |
| Orchestration | Docker Compose for the pilot | 500-1,000 youth and ~20 concurrent users do not need Kubernetes. Revisit only at national scale-up. |
| Backups | Scheduled `pg_dump` to MinIO or offsite storage, tested restore | Required for a government-owned system. |

### 2.1 Local Development Environment

Every engineer develops inside a Multipass-provisioned Ubuntu VM, running the same Docker Compose stack as staging and production. A cloud-init configuration and onboarding script for the Multipass VM is a Sprint 0 deliverable.

```bash
# indicative Sprint 0 bootstrap, adjust to your actual repo layout
multipass launch --name yep-dev --cpus 4 --memory 8G --disk 40G 22.04
multipass mount . yep-dev:/home/ubuntu/youth-employment-platform
multipass exec yep-dev -- bash -c "cd youth-employment-platform/infra && docker compose up -d"
```

### 2.2 Suggested Repository Structure

```
youth-employment-platform/
├── backend/                 # Django + DRF
│   ├── config/               # settings, urls, celery.py
│   ├── apps/
│   │   ├── users/             # User, Role, auth (Sprint 0-2)
│   │   ├── youth/             # Youth entity (Sprint 1)
│   │   ├── cases/             # Case, Profiling, Pathway Assignment (Sprint 1-2)
│   │   ├── partners/          # Partner/Provider Organisation (Sprint 2)
│   │   ├── referrals/         # Referral entity, state machine, taxonomy (Sprint 3-4) - the core app
│   │   ├── alerts/            # Alert/Task, Celery beat jobs (Sprint 4)
│   │   ├── training/          # Training Enrolment (Sprint 5)
│   │   ├── placements/        # Placement (Sprint 5)
│   │   ├── enterprises/       # Enterprise (Sprint 6)
│   │   ├── followups/         # Follow-Up/Contact Log (Sprint 6)
│   │   └── grievances/        # Grievance (Sprint 6)
│   ├── requirements/
│   └── Dockerfile
├── web/                      # React + TypeScript (Ant Design)
├── mobile/                   # Flutter (Sprint 8-9)
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── traefik/
│   └── multipass/             # cloud-init, VM bootstrap scripts
├── docs/
│   └── YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md   # this file
└── .github/workflows/
```

Adjust as needed. This layout maps directly to the sprint sequence in [Section 10](#10-sprint-plan-and-development-roadmap): one Django app per entity group, built in the order the sprints introduce them.

### 2.3 Design Note

The referral state machine ([6.2](#62-transitions)) lives in the Django application as explicit domain logic (for example, a `referrals/services.py` module or a small state machine library), unit tested against every transition. Not database triggers, not stored procedures. This keeps the business rules auditable and easier to hand over to a government IT team at scale-up.

---

## 3. Core Entity Model

Fourteen entities carry the platform's data. Full field definitions for each entity follow in [Section 4](#4-entity-field-definitions).

| Entity | Relationship |
|---|---|
| Youth (Participant) | One record per registered youth. Root of the case. |
| Case | One-to-one with Youth. Wraps case status, assigned case manager, and current pathway. |
| Profiling and Eligibility Record | One-to-one with Case (may be revised; latest record is current). |
| Pathway Assignment | One-to-many with Case. History of pathway decisions; one marked current. |
| Training Enrolment | One-to-many with Case. Covers Life Skills/Employability and TVET, distinguished by `training_type`. |
| Referral | One-to-many with Case. **The central entity.** Self-referencing via `parent_referral_id` to build the referral chain, and `parallel_group_id` to group concurrent referrals. |
| Placement | One-to-many with Case. Usually created from a completed Referral (`source_referral_id`). |
| Enterprise | One-to-many with Case. Usually created from a completed Referral (`source_referral_id`). |
| Follow-Up / Contact Log | One-to-many with Case, optionally linked to a specific Referral. |
| Grievance | One-to-many with Case, optionally linked to a specific Referral. |
| Partner / Provider Organisation | One-to-many with Referral (a partner receives many referrals) and with Training Enrolment (a partner runs many trainings). |
| User (Actor) | One-to-many with Case (as case manager) and with Referral (as initiator). Linked to a Partner record for referral-partner-staff accounts. |
| Alert / Task | One-to-many with Case, generated by system rules ([Section 6](#6-referral-state-machine-and-business-rules)). |
| Reference Lists (lookups) | Referral Category, Referral Trigger, Referral Status, Outcome Type, Failure Reason Code (see [Section 5](#5-referral-taxonomy-reference-data)). |

---

## 4. Entity Field Definitions

**Type column translation guide** (conceptual type → Django field):
`System ID` → `UUIDField(primary_key=True, default=uuid4, editable=False)` · `Text` → `CharField`/`TextField` as length requires · `Enum` → `CharField(choices=...)` backed by a `TextChoices` class · `Date` → `DateField` · `Timestamp` → `DateTimeField` · `Reference (X)` → `ForeignKey(X, on_delete=...)` · `Reference (self)` → `ForeignKey("self", null=True, on_delete=SET_NULL)` · `Boolean` → `BooleanField` · `Number` → `IntegerField` or `DecimalField` as precision requires · `Multi-select` → `ManyToManyField` or `ArrayField(CharField)` (Postgres-specific).

### 4.1 Youth (Participant)

Source module: Youth Intake and Registration.

| Field | Type | Required | Notes |
|---|---|---|---|
| `youth_id` | System ID | Yes | Primary key. Generated at registration. |
| `full_name` | Text | Yes | |
| `sex` | Enum | Yes | Male / Female / Other, per Ethiopian data standards. |
| `date_of_birth` | Date | Yes | Used to confirm youth age band eligibility. |
| `phone_number` | Text | No | Youth or next-of-kin contact. |
| `national_or_kebele_id` | Text | No | Local identification, where available. |
| `region` / `zone` / `woreda` / `kebele` | Text | Yes | Location hierarchy for caseload assignment and reporting. |
| `household_id` | Reference | No | Links to PSNP household registration record. |
| `psnp_status` | Enum | No | Enrolled / Graduated / Not PSNP. |
| `education_level` | Enum | No | Feeds profiling score. |
| `disability_status` | Enum | No | For vulnerability screening and priority flagging. |
| `consent_given` / `consent_date` | Boolean / Date | Yes | Data protection requirement; see [Section 9](#9-non-functional-and-implementation-notes). |
| `registration_date` | Date | Yes | System generated. |
| `registering_worker_id` | Reference (User) | Yes | Outreach worker or facilitator who registered the youth. |

### 4.2 Case

Wraps the youth's operational status. This is the entity a case manager opens first.

| Field | Type | Required | Notes |
|---|---|---|---|
| `case_id` | System ID | Yes | Primary key. |
| `youth_id` | Reference (Youth) | Yes | One-to-one. |
| `case_status` | Enum | Yes | Active / Stalled / Referral Pending / Placed / Exited. |
| `case_manager_id` | Reference (User) | Yes | Currently assigned case manager. |
| `woreda` | Text | Yes | Denormalised from Youth for caseload filtering. |
| `opened_date` | Date | Yes | |
| `closed_date` / `exit_reason` | Date / Text | No | Set at case exit. |
| `last_activity_date` | Date | Yes | System updated on any case event. Drives the stall alert ([Section 6](#6-referral-state-machine-and-business-rules)). |
| `current_pathway_assignment_id` | Reference (Pathway Assignment) | No | Points to the pathway record marked current. |
| `next_action` / `next_action_owner_id` | Text / Reference (User) | No | Answers Core Design Principle questions 10 and 11. |

### 4.3 Profiling and Eligibility Record

| Field | Type | Required | Notes |
|---|---|---|---|
| `profiling_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `work_history_summary` | Text | No | |
| `skills_list` | Multi-select | No | |
| `vulnerability_index_score` | Number | No | Methodology to be defined with M&E during Phase 1 (open question). |
| `eligibility_flags` | Multi-select | Yes | Wage employment / self-employment / apprenticeship / training. |
| `priority_flag` | Boolean | No | Marks high-vulnerability cases for priority handling. |
| `assessed_date` / `assessor_id` | Date / Reference (User) | Yes | |

### 4.4 Pathway Assignment

| Field | Type | Required | Notes |
|---|---|---|---|
| `pathway_assignment_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `assessed_interests` / `capacities` / `barriers` | Text | No | Free text or structured, per assessment tool design. |
| `selected_pathway` | Enum | Yes | Wage Employment / Self-Employment / Apprenticeship / Training. |
| `assessment_date` / `assessor_id` | Date / Reference (User) | Yes | |
| `is_current` | Boolean | Yes | Only one record per case set true. |
| `superseded_by_id` / `revision_reason` | Reference (self) / Text | No | Set when a pathway is revised after case review. |

### 4.5 Training Enrolment

Covers both Life Skills and Employability Training and Technical and Vocational Training, distinguished by `training_type`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `training_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `training_type` | Enum | Yes | Life Skills/Employability / TVET. |
| `trade_or_skill_area` | Text | No | TVET only. |
| `training_provider_id` | Reference (Partner) | Yes | |
| `enrolment_date` / `start_date` / `end_date` | Date | Yes | |
| `attendance_rate` | Number (%) | No | |
| `completion_status` | Enum | Yes | Enrolled / Completed / Dropped Out / Failed Assessment. |
| `assessment_result` / `certificate_status` | Text / Enum | No | |
| `dropout_flag` / `dropout_date` / `dropout_reason` | Boolean / Date / Text | No | |
| `source_referral_id` | Reference (Referral) | No | The referral that placed the youth into this training. |
| `triggers_onward_referral` | Boolean | System-set | Set true on completion; drives the onward-referral prompt. |

### 4.6 Referral (the core entity)

Every referral, of every category and every trigger, is one row in this table. The chain fields (`parent_referral_id`, `replacement_referral_id`) and `parallel_group_id` are what let the system reconstruct the full referral stack.

| Field | Type | Required | Notes |
|---|---|---|---|
| `referral_id` | System ID | Yes | Primary key. |
| `case_id` | Reference (Case) | Yes | |
| `referral_category` | Enum | Yes | See [5.1](#51-referral-category). |
| `referral_trigger` | Enum | Yes (system-set for Onward/Replacement) | Manual / Onward / Replacement (see [5.2](#52-referral-trigger)). |
| `is_parallel` / `parallel_group_id` | Boolean / System ID | System-set | Groups referrals concurrently active for the same case. See [6.3](#63-parallel-referral-rule). |
| `parent_referral_id` | Reference (self) | No | Set for Onward and Replacement referrals; links to the referral that preceded it. |
| `replacement_referral_id` | Reference (self) | No | Set once this referral has been replaced; forward link. |
| `receiving_partner_id` | Reference (Partner) | Yes | |
| `receiving_contact_name` | Text | No | |
| `initiated_date` / `initiated_by_id` | Date / Reference (User) | Yes | |
| `confirmation_status` | Enum | Yes | Pending Confirmation / Confirmed / Declined. |
| `confirmed_date` / `confirmed_by` | Date / Text | No | Partner-side confirmation. |
| `status` | Enum | Yes | Pending / Active / Completed / Failed / Replaced / Cancelled (see [Section 6](#6-referral-state-machine-and-business-rules)). |
| `outcome_type` | Enum | No (set on completion) | See [5.3](#53-outcome-type). |
| `outcome_date` / `outcome_verified_by_id` / `outcome_verification_method` | Date / Reference (User) / Text | No | Verification via follow-up visit. |
| `failure_reason_code` | Enum (lookup) | No (set on failure) | See [5.4](#54-failure-reason-code-starter-list). |
| `failure_date` | Date | No | |
| `notes` | Text | No | |

### 4.7 Placement

| Field | Type | Required | Notes |
|---|---|---|---|
| `placement_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `source_referral_id` | Reference (Referral) | No | Set when placement resulted from a referral. |
| `employer_name` / `sector` | Text | Yes | |
| `placement_type` | Enum | Yes | Job / Apprenticeship. |
| `placement_date` / `wage_amount` / `contract_type` / `contract_duration` | Date / Number / Enum / Text | Yes | |
| `retention_check_30` / `_60` / `_90` | Status + Date + Reference (User), x3 | Yes | One record per checkpoint. |
| `exit_date` / `exit_reason` | Date / Text | No | |

### 4.8 Enterprise

| Field | Type | Required | Notes |
|---|---|---|---|
| `enterprise_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `source_referral_id` | Reference (Referral) | No | |
| `business_plan_status` | Enum | Yes | |
| `grant_or_loan_amount` / `disbursement_date` | Number / Date | No | |
| `mentorship_sessions_count` | Number | No | |
| `business_registration_status` / `number` | Enum / Text | No | |
| `market_linkage_status` | Enum | No | |
| `milestones` (sub-table) | `milestone_name`, `target_date`, `completion_date`, `status` | No | One-to-many child records. |

### 4.9 Follow-Up / Contact Log

| Field | Type | Required | Notes |
|---|---|---|---|
| `followup_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `related_referral_id` | Reference (Referral) | No | Set when the follow-up verifies a specific referral outcome. |
| `attempt_date` / `contact_method` | Date / Enum | Yes | |
| `contact_outcome` | Enum | Yes | Reached-Engaged / Reached-Not Engaged / No Response / Unreachable. |
| `re_engagement_status` / `pathway_revision_flag` | Enum / Boolean | No | Links to Pathway Assignment revision. |
| `conducted_by_id` | Reference (User) | Yes | |

### 4.10 Grievance

| Field | Type | Required | Notes |
|---|---|---|---|
| `grievance_id` | System ID | Yes | |
| `case_id` | Reference (Case) | No | Nullable. A grievance can be raised without a linked case. |
| `related_referral_id` | Reference (Referral) | No | Set when the complaint concerns a specific referral. |
| `complaint_type` / `raised_by` | Enum / Enum | Yes | Raised by: Youth / Employer / Trainer / Partner. |
| `date_raised` / `assigned_staff_id` | Date / Reference (User) | Yes | |
| `resolution_status` | Enum | Yes | Open / In Progress / Resolved / Closed. |
| `resolution_date` / `resolution_notes` | Date / Text | No | |
| `referral_quality_feedback_flag` | Boolean | No | Marks complaints specifically about referral quality or timeliness. |

### 4.11 Partner / Provider Organisation

| Field | Type | Required | Notes |
|---|---|---|---|
| `partner_id` | System ID | Yes | |
| `partner_name` | Text | Yes | |
| `partner_type` | Enum | Yes | TVET Institution / Employer / Enterprise Development Agency / Savings Group / Health Service / Psychosocial Service / Legal Aid / Finance Institution / Other. |
| `woreda_coverage` | Multi-select | Yes | |
| `contact_name` / `phone` / `email` | Text | Yes | |
| `active_status` | Boolean | Yes | |
| `mou_status` / `mou_date` | Enum / Date | No | Tracks the referral-relationship mapping. |
| `performance_notes` | Text | No | Qualitative input alongside the quantitative referral performance dashboard. |

### 4.12 User (Actor)

| Field | Type | Required | Notes |
|---|---|---|---|
| `user_id` | System ID | Yes | |
| `full_name` | Text | Yes | |
| `role` | Enum | Yes | One of the ten roles in [Section 7](#7-role-based-access-model). |
| `woreda_assignment` | Multi-select | Yes | |
| `partner_id` | Reference (Partner) | No | Set for referral-partner-staff accounts; scopes their referral visibility. |
| `account_status` / `last_login` | Enum / Timestamp | System | |

### 4.13 Alert / Task

| Field | Type | Required | Notes |
|---|---|---|---|
| `alert_id` | System ID | Yes | |
| `case_id` | Reference (Case) | Yes | |
| `alert_type` | Enum | Yes | Stall Alert / Referral Confirmation Overdue / Follow-Up Due / Onward Referral Prompt / Replacement Referral Prompt / Retention Check Due. |
| `triggered_date` / `threshold_days` | Date / Number | Yes | `threshold_days` is configurable per `alert_type`. |
| `assigned_to_id` | Reference (User) | Yes | |
| `status` | Enum | Yes | Open / Actioned / Dismissed. |
| `actioned_date` / `actioned_by_id` | Date / Reference (User) | No | |

---

## 5. Referral Taxonomy (Reference Data)

The concept note describes referrals using five labels: sequential, parallel, onward, failed, and replacement. Two of these describe how a referral was created (onward, replacement, and by default manual), one describes its concurrency with other referrals (parallel), and two describe an end state (failed, and implicitly completed). Modelling all five as a single `referral_type` field would let a referral hold contradictory values at once, for example onward and parallel together. [4.6](#46-referral-the-core-entity) splits this into three fields, `referral_trigger`, `is_parallel`/`parallel_group_id`, and `status`, which combine freely and still support every workflow the concept note describes. This split needs sign-off in the Phase 1 business process design workshops.

### 5.1 Referral Category

| Value | Description |
|---|---|
| Training | Referral into Life Skills/Employability or TVET training. |
| Employment / Placement | Referral toward a wage job. |
| Apprenticeship | Referral toward an apprenticeship placement. |
| Enterprise | Referral toward enterprise start-up support. |
| Finance Access | Referral to a savings group, microfinance, or credit provider. |
| Market Linkage | Referral connecting a youth-run enterprise to buyers or supply chains. |
| Complementary Service | Health, psychosocial support, legal aid, nutrition, or social assistance top-up. |
| Coaching | Referral to a coaching or mentoring service. |
| Other | Catch-all; requires a free-text note. |

### 5.2 Referral Trigger

| Value | Created By | Description |
|---|---|---|
| Manual | Case manager | Initiated from an assessment, pathway assignment, or case review finding. |
| Onward | System-prompted, case manager confirms | Prompted automatically when a prior referral in the case reaches Completed status. The case manager reviews and confirms before the new referral is created, to manage data entry burden. |
| Replacement | System-prompted, case manager confirms | Prompted automatically when a prior referral reaches Failed status. Same confirm-before-create pattern as Onward. |

### 5.3 Outcome Type

| Value | Applies To Referral Category |
|---|---|
| Service Uptake | Complementary Service, Coaching |
| Training Completion | Training |
| Job Placement | Employment / Placement |
| Apprenticeship Start | Apprenticeship |
| Enterprise Enrolment | Enterprise |
| Finance Access | Finance Access |
| Market Linkage Established | Market Linkage |
| Other | Any; requires a free-text note |

### 5.4 Failure Reason Code (starter list)

These codes need local validation with frontline staff during Phase 1. They are a starting point, not a final list.

| Code | Meaning |
|---|---|
| `YOUTH_NO_SHOW` | Youth did not present to the receiving partner. |
| `PARTNER_CAPACITY` | Receiving partner had no capacity (training slot, job vacancy, loan fund) at the time. |
| `ELIGIBILITY_MISMATCH` | Youth did not meet the receiving partner's eligibility criteria. |
| `CONSENT_WITHDRAWN` | Youth withdrew consent or declined the referral. |
| `PARTNER_NON_RESPONSIVE` | Receiving partner did not confirm or respond within the expected window. |
| `DOCUMENTATION_INCOMPLETE` | Required documentation was missing or incomplete. |
| `OTHER` | Requires a free-text note. |

---

## 6. Referral State Machine and Business Rules

### 6.1 Status Values

| Status | Meaning |
|---|---|
| Pending Confirmation | Referral initiated, awaiting the receiving partner's confirmation. |
| Active | Confirmed and in progress. |
| Completed | Service received and outcome recorded. |
| Failed | Did not proceed to a positive outcome; `failure_reason_code` is required. |
| Replaced | Terminal state once a Replacement referral has been created against it. |
| Cancelled | Withdrawn by the case manager before confirmation, distinct from a partner-side decline. |

### 6.2 Transitions

| From | To | Trigger | System Action |
|---|---|---|---|
| (none) | Pending Confirmation | Case manager initiates a referral (manually, or by confirming an Onward/Replacement prompt). | Referral record created; alert set for partner confirmation. |
| Pending Confirmation | Active | Receiving partner confirms. | Referral stack updated; if another referral is already Active for this case, assign shared `parallel_group_id` ([6.3](#63-parallel-referral-rule)). |
| Pending Confirmation | Failed | Receiving partner declines. | `failure_reason_code` required; Replacement prompt generated. |
| Pending Confirmation | Cancelled | Case manager withdraws before confirmation. | No replacement prompt. |
| Active | Completed | Outcome recorded and verified (via follow-up visit). | `outcome_type` and `outcome_date` set; Onward prompt generated; `parallel_group_id` slot freed. |
| Active | Failed | Non-attendance, dropout, or other failure identified. | `failure_reason_code` required; Replacement prompt generated; `parallel_group_id` slot freed. |
| Failed | Replaced | Case manager confirms the Replacement prompt. | New referral created with `referral_trigger = Replacement` and `parent_referral_id` pointing here; `replacement_referral_id` set on this record. |
| Completed | (none) | Case manager confirms the Onward prompt. | New referral created with `referral_trigger = Onward` and `parent_referral_id` pointing here. |

**Implementation note:** write this as an explicit state machine (a `Referral.transition_to(new_status, **kwargs)` method or equivalent) that validates the from/to pair against this table and raises on an invalid transition. Unit test every row.

### 6.3 Parallel Referral Rule

A case may hold at most two Active referrals sharing a `parallel_group_id` at any time, per the concept note's "two active at once" design. Complementary Service referrals (health, psychosocial, legal, nutrition, social assistance) are explicitly allowed to run alongside any other active referral.

**Working default (needs Phase 1 confirmation):** Complementary Service referrals sit **outside** the two-referral cap, as a third concurrent stream, rather than counting toward it. Implement it this way, but leave a comment flagging it as a policy decision pending sign-off (see [Open Questions](#11-open-questions-for-phase-1-sign-off)).

### 6.4 Referral Stack Reconstruction

The full referral stack is not a stored object. It is a query: all Referral records for a `case_id`, ordered by `initiated_date`, with `parent_referral_id` and `replacement_referral_id` used to draw the chain, and `parallel_group_id` used to mark concurrent pairs. Keep the referral history query-driven rather than duplicated into a separate table, so the stack is always current.

---

## 7. Role-Based Access Model

Ten user types. Field-level permissions (who can edit versus only view each entity) are a configuration detail built on this record-level scoping.

| Role | Case Record Access | Referral Access | Key Actions |
|---|---|---|---|
| Outreach worker / community facilitator | Create; view own woreda | View only | Intake and registration. |
| Youth case manager | Full, own caseload | Full, own caseload | Case progression, referral initiation, confirms Onward/Replacement prompts. |
| Trainer / training officer | View, linked cases only | View, linked referrals only | Enrolment, attendance, completion records. |
| Employer liaison staff | View, linked cases only | View/update, linked referrals only | Placement and retention records. |
| Enterprise development officer | View, linked cases only | View/update, linked referrals only | Business plan review, disbursement, mentorship. |
| Referral partner staff | View, linked cases only | View/update, own institution's referrals only | Referral receipt confirmation, service recording, outcome feedback. |
| Woreda / programme supervisor | View, own woreda | View, own woreda | Caseload and pipeline oversight, case review decisions. |
| Programme manager | View, all | View, all | Dashboard monitoring, outcome reporting, partner performance decisions. |
| M&E staff | View, all | View, all | Data quality checks, outcome verification. |
| System administrator | Configuration only, no case content by default | Configuration only | User management, taxonomy configuration. |

---

## 8. Dashboard and Reporting Data Requirements

Each dashboard maps to a defined query against the entities above. Build these in Metabase against a read-only Postgres role (Sprint 7).

| Dashboard | Source Entities | Aggregation |
|---|---|---|
| Case status distribution | Case | Count of cases by `case_status`, filterable by woreda and case manager. |
| Referral pipeline by stage and type | Referral | Count by `status` × `referral_category`. |
| Parallel referral loads | Referral | Count of cases with 2+ concurrently Active referrals sharing a `parallel_group_id`. |
| Outcome type breakdown | Referral | Count of Completed referrals by `outcome_type`. |
| Failed referral rate by partner | Referral, Partner | Failed ÷ (Failed + Completed), grouped by `receiving_partner_id`, with `failure_reason_code` breakdown. |
| Referral completion rate by partner | Referral, Partner | Completed ÷ total closed referrals, grouped by `receiving_partner_id`. |
| Placement retention | Placement | Retention status at the 30/60/90-day checkpoints, by sector and by `source_referral_id` presence (referral-sourced vs direct). |
| Caseload by case manager / woreda | Case | Count of active cases per `case_manager_id`, flagged when above a configurable caseload ceiling. |
| Stalled case alerts | Case, Alert | Cases with `last_activity_date` older than the configured stall threshold. |

---

## 9. Non-Functional and Implementation Notes

- **Offline data entry:** field staff need to register youth, log follow-ups, and update referral status without connectivity, then sync. Handled by the Flutter mobile app ([Section 2](#2-technology-stack)). Conflict resolution rules for near-simultaneous offline edits to the same case are built in Sprint 9.
- **Data privacy:** consent fields sit on the Youth record ([4.1](#41-youth-participant)). Role scoping in [Section 7](#7-role-based-access-model) enforces caseload and partner restrictions. Legal review against Ethiopian data protection law is an open item (see [Section 11](#11-open-questions-for-phase-1-sign-off)).
- **Taxonomy governance:** `referral_category`, `outcome_type`, and `failure_reason_code` are configuration data, not code. The system administrator role should own changes to these lists post go-live, with changes logged for audit.
- **Audit trail:** case review decisions must record date, actor, and rationale. This applies to any status or pathway change, not only case reviews, and should be a platform-wide requirement, not limited to the Alert/Task entity. Consider `django-simple-history` or an equivalent audit-log package rather than a hand-rolled solution.

---

## 10. Sprint Plan and Development Roadmap

Assumed team: two backend engineers, one web frontend engineer, one mobile engineer, one QA/DevOps engineer working part time, coordinated by a product manager or business analyst. Adjust the sprint count if the actual team is smaller or larger; the sequencing and dependencies below hold regardless of team size.

Eleven two-week sprints, 22 weeks (about five months), take the platform from an empty repository to pilot-ready.

### Sprint 0 (Weeks 1-2): Foundations and Environment

- Monorepo scaffold: `backend/`, `web/`, `mobile/`, `infra/`.
- Multipass VM plus Docker Compose dev environment (Postgres, Redis, MinIO, Traefik).
- CI/CD pipeline: build, test, push images.
- Django project skeleton, DRF, JWT auth.
- User and Role models, RBAC scaffolding ([Section 7](#7-role-based-access-model)).

### Sprint 1 (Weeks 3-4): Youth and Case Core

- Youth entity ([4.1](#41-youth-participant)), including consent capture.
- Case entity ([4.2](#42-case)): status, case manager assignment, woreda scoping.
- Location and reference data.
- Case list and detail screens for case managers.
- Django admin wired for reference data.

### Sprint 2 (Weeks 5-6): Profiling, Pathway, Partners, Users

- Profiling and Eligibility Record ([4.3](#43-profiling-and-eligibility-record)).
- Pathway Assignment, including revision history ([4.4](#44-pathway-assignment)).
- Partner/Provider Organisation ([4.11](#411-partner--provider-organisation)), MOU status.
- Full RBAC enforcement per [Section 7](#7-role-based-access-model), including partner-institution scoping.
- User management UI for administrators.

### Sprint 3 (Weeks 7-8): Referral Engine Core

- Referral entity ([4.6](#46-referral-the-core-entity)).
- Referral taxonomy as configurable lookups ([Section 5](#5-referral-taxonomy-reference-data)).
- State machine, every transition unit tested ([6.2](#62-transitions)).
- Parallel group logic and two-referral cap ([6.3](#63-parallel-referral-rule)).
- Referral stack query ([6.4](#64-referral-stack-reconstruction)).
- Case manager UI: initiate, confirm/decline, stack timeline.

### Sprint 4 (Weeks 9-10): Automation and Alerts

- Onward referral auto-prompt on Completed status.
- Replacement referral auto-prompt on Failed status.
- Alert/Task entity ([4.13](#413-alert--task)): stall, confirmation overdue, follow-up due, retention due.
- Celery beat scheduled jobs.
- "Next action" surfaced on the case screen (the eleven questions from the concept note).

### Sprint 5 (Weeks 11-12): Training and Placement

- Training Enrolment ([4.5](#45-training-enrolment)), linked to Referral.
- Placement ([4.7](#47-placement)), including 30/60/90-day retention checkpoints and reminders.
- Screens for trainers and employer liaison staff.

### Sprint 6 (Weeks 13-14): Enterprise, Follow-Up, Grievance

- Enterprise ([4.8](#48-enterprise)), including milestones sub-table.
- Follow-Up/Contact Log ([4.9](#49-follow-up--contact-log)), referral outcome verification.
- Grievance ([4.10](#410-grievance)).
- Screens for enterprise development officers and M&E staff.

### Sprint 7 (Weeks 15-16): Dashboards and Reporting

- Metabase deployment, read-only database role.
- Build all nine dashboards from [Section 8](#8-dashboard-and-reporting-data-requirements).
- Programme manager and M&E dashboard access.

### Sprint 8 (Weeks 17-18): Mobile App I

- Flutter scaffold, local SQLite (Drift) schema.
- Offline intake and registration flow.
- Sync engine: push/pull against the API, `updated_since` delta sync.

### Sprint 9 (Weeks 19-20): Mobile App II

- Offline follow-up logging and referral status updates.
- Conflict resolution for offline edits (open item, see [Section 11](#11-open-questions-for-phase-1-sign-off)).
- Field testing on actual tablets.

### Sprint 10 (Weeks 21-22): Hardening and Pilot Readiness

- End-to-end testing across all modules.
- Load testing at pilot scale (500-1,000 youth, roughly 20 users).
- Security review: auth, RBAC boundaries, referral partner data scoping.
- UAT with a small group of case managers and referral partners.
- Backup and restore drill, deployment runbook.

### 10.1 Definition of Done

A sprint's deliverables are not complete until:

- Automated tests cover the referral state transitions and RBAC boundaries touched in that sprint.
- Code is reviewed by at least one other engineer (or a second agent pass) before merge.
- The feature is deployed and demonstrated in the staging environment (Docker Compose, matching production).
- Any new configuration data (referral categories, outcome types, failure codes) is entered through the admin interface, not hardcoded.

---

## 11. Open Questions for Phase 1 Sign-Off

These decisions affect the data model above and should be settled in the Phase 1 business process design workshops before Sprint 0 begins. Where a working default is stated elsewhere in this document, build against it and flag it in code rather than blocking on the answer.

- Confirm the `referral_trigger` / `is_parallel` / `status` split in [Section 5](#5-referral-taxonomy-reference-data) as the working model, or propose an alternative that still supports every workflow in the concept note.
- Confirm if Complementary Service referrals count toward the two-referral parallel cap ([6.3](#63-parallel-referral-rule)) or sit outside it.
- Validate and finalise the `failure_reason_code` list ([5.4](#54-failure-reason-code-starter-list)) with frontline case managers and referral partners.
- Define the `vulnerability_index_score` methodology for the Profiling and Eligibility Record with M&E.
- Set the caseload ceiling and stall-alert `threshold_days` defaults ([4.13](#413-alert--task)) with programme management.
- Confirm the Flutter app's offline conflict-resolution rules with the technical lead before Sprint 9.
- Confirm data retention and consent-withdrawal handling against Ethiopian data protection requirements.
- Confirm the team composition assumed in [Section 10](#10-sprint-plan-and-development-roadmap) (five engineers) against the actual team, and adjust the sprint count accordingly.

---

## 12. Suggested Next Steps

Validate this model against the Phase 1 business process design workshops so the referral taxonomy in [Section 5](#5-referral-taxonomy-reference-data) is signed off with the same group that owns the pilot work plan. This document turns directly into a development backlog: one epic per entity in [Section 4](#4-entity-field-definitions), one per state transition in [6.2](#62-transitions), and one per dashboard in [Section 8](#8-dashboard-and-reporting-data-requirements).

Kick off Sprint 0 as soon as the taxonomy and parallel-cap decisions in [Section 11](#11-open-questions-for-phase-1-sign-off) are confirmed, since they shape the Referral entity built in Sprint 3. A clickable prototype of the case manager screen is a useful parallel-track task if frontline feedback is wanted before Sprint 3 locks the referral UI.
