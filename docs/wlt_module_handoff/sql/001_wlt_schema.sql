-- =============================================================================
-- 001_wlt_schema.sql   WLT group module: tables
--
-- Conventions used throughout, and why:
--   * uuid primary keys           offline clients generate ids before sync
--   * text + CHECK, not pg enums  the handbook is a living document; adding a
--                                 value to a CHECK is cheaper than ALTER TYPE
--   * dated ranges, not flags     indicators compute against the roster as it
--                                 stood on the meeting date, not as it stands now
--   * numeric(14,2) for money     never float
--   * no business rules in SQL    gates and phase logic live in wlt/services/
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS wlt;

-- =============================================================================
-- SECTION A. POLICY LAYER
-- Every threshold FSCO can change lives here, effective-dated and geo-scoped.
-- Hardcoding 80%, 8 SHGs or 15-25 members guarantees a code change per revision.
-- =============================================================================

CREATE TABLE wlt.policy_parameter (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key            text NOT NULL,
    scope_geo_id   uuid REFERENCES core.geography(id),   -- null = global
    value          jsonb NOT NULL,
    effective_from date NOT NULL,
    effective_to   date,
    note           text,
    created_by     uuid REFERENCES core.app_user(id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT policy_period_valid CHECK (effective_to IS NULL OR effective_to > effective_from)
);

-- Snapshot of the whole policy set at a decision moment. Phase and linkage
-- decisions reference a version so they stay auditable under the rules that
-- applied at the time, not the rules that apply now.
CREATE TABLE wlt.policy_version (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    parameters  jsonb NOT NULL
);

-- Pre-pilot ceiling: 5,000 across five regions. Enforced, not tracked in a
-- spreadsheet three months late.
CREATE TABLE wlt.enrolment_allocation (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    geography_id   uuid NOT NULL REFERENCES core.geography(id),
    phase_label    text NOT NULL DEFAULT 'pre_pilot',
    target_members integer NOT NULL CHECK (target_members > 0),
    target_groups  integer,
    effective_from date NOT NULL,
    effective_to   date
);

-- =============================================================================
-- SECTION B. REGISTRY EXTENSION   (DECISION D1 + D5)
-- core.person is untouched. WLT-specific attributes hang off it here.
-- =============================================================================

CREATE TABLE wlt.beneficiary_profile (
    person_id           uuid PRIMARY KEY REFERENCES core.person(id) ON DELETE RESTRICT,

    -- join key to the PSNP MIS. Without it there is no eligibility
    -- verification and no reconciliation.
    psnp_client_id      text,
    psnp_woreda_id      uuid REFERENCES core.geography(id),
    psnp_kebele_id      uuid REFERENCES core.geography(id),

    -- ELS pre-conditions. Handbook section 2: members complete the ELS package
    -- before transitioning into WLT.
    els_completed_on    date,
    els_grant_received_on date,
    els_grant_amount_etb numeric(14,2),

    -- handbook 3.3 selection criteria. Not captured = not enforceable.
    primary_iga         text,
    literacy_level      text CHECK (literacy_level IN ('none','basic','functional')),
    digital_literacy    text CHECK (digital_literacy IN ('none','basic')),
    has_device          boolean,
    household_head      boolean,

    enrolment_route     text NOT NULL CHECK (enrolment_route IN ('import','facilitator')),
    verification_status text NOT NULL DEFAULT 'pending'
                          CHECK (verification_status IN ('verified','pending','rejected')),
    verification_note   text,
    verified_by         uuid REFERENCES core.app_user(id),
    verified_on         date,

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT verified_needs_verifier CHECK (
        verification_status <> 'verified' OR verified_on IS NOT NULL
    )
);

-- Fuzzy-match queue from the caseload import. Never auto-merge: merging two
-- different women is worse than carrying a duplicate.
CREATE TABLE wlt.import_match_candidate (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_batch      text NOT NULL,
    source_row        jsonb NOT NULL,
    matched_person_id uuid REFERENCES core.person(id),
    confidence        numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
    resolution        text NOT NULL DEFAULT 'pending'
                        CHECK (resolution IN ('pending','confirmed','rejected','new_person')),
    resolved_by       uuid REFERENCES core.app_user(id),
    resolved_at       timestamptz
);

-- =============================================================================
-- SECTION C. GROUP FORMATION   (DECISION D2)
-- =============================================================================

-- Handbook 3.4 step 1. Recorded even when endorsement is refused: a kebele that
-- produced no groups is programme learning, and it is invisible if only
-- successes are stored.
CREATE TABLE wlt.mobilisation_event (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kebele_id             uuid NOT NULL REFERENCES core.geography(id),
    held_on               date NOT NULL,
    facilitator_id        uuid NOT NULL REFERENCES core.app_user(id),
    attendees_potential   integer CHECK (attendees_potential >= 0),
    attendees_husbands    integer CHECK (attendees_husbands >= 0),
    attendees_elders      integer CHECK (attendees_elders >= 0),
    attendees_leaders     integer CHECK (attendees_leaders >= 0),
    endorsement_obtained  boolean NOT NULL,
    endorsement_note      text,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE wlt.group (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text NOT NULL,
    kebele_id            uuid NOT NULL REFERENCES core.geography(id),
    mobilisation_event_id uuid REFERENCES wlt.mobilisation_event(id),

    -- formation state machine: a group is not real until it has saved money
    status               text NOT NULL DEFAULT 'draft' CHECK (status IN
                           ('draft','constituted','active','at_risk','dormant',
                            'split','merged','dissolved','abandoned')),
    current_phase        text CHECK (current_phase IN ('p1','p2','p3','p4')),

    drafted_on           date NOT NULL DEFAULT current_date,
    constituted_on       date,
    activated_on         date,
    closed_on            date,
    closure_reason       text,

    created_by           uuid REFERENCES core.app_user(id),
    created_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT phase_only_when_active CHECK (
        (current_phase IS NULL) OR (status IN ('active','at_risk','dormant','split','merged','dissolved'))
    ),
    CONSTRAINT activated_needs_constituted CHECK (
        activated_on IS NULL OR constituted_on IS NOT NULL
    )
);

-- Bylaws are versioned. A group raises its contribution in month 8; compliance
-- for months 1-7 must still compute against the old figure.
CREATE TABLE wlt.bylaw_version (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id               uuid NOT NULL REFERENCES wlt.group(id) ON DELETE CASCADE,
    version_no             integer NOT NULL CHECK (version_no > 0),
    effective_from         date NOT NULL,
    effective_to           date,

    meeting_cadence        text NOT NULL CHECK (meeting_cadence IN ('weekly','fortnightly','monthly')),
    meeting_day            text,
    contribution_etb       numeric(14,2) NOT NULL CHECK (contribution_etb > 0),

    -- OPEN QUESTION Q4: basis is undefined in the handbook. Do not default it.
    service_charge_basis   text CHECK (service_charge_basis IN
                             ('flat_per_loan','per_month','declining_balance')),
    service_charge_rate    numeric(6,4) CHECK (service_charge_rate >= 0),
    service_charge_label   text NOT NULL DEFAULT 'service_charge',  -- religious inclusivity, 3.5

    late_penalty_etb       numeric(14,2),
    absence_penalty_etb    numeric(14,2),
    officer_rotation_months integer CHECK (officer_rotation_months > 0),
    loan_quorum_pct        integer CHECK (loan_quorum_pct BETWEEN 1 AND 100),
    max_concurrent_loans   integer CHECK (max_concurrent_loans > 0),
    reserve_buffer_pct     integer CHECK (reserve_buffer_pct BETWEEN 0 AND 100),

    clauses_local_language text,
    recorded_by            uuid REFERENCES core.app_user(id),
    created_at             timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT bylaw_period_valid CHECK (effective_to IS NULL OR effective_to > effective_from)
);

-- Dated range, not a flag.
CREATE TABLE wlt.group_membership (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    uuid NOT NULL REFERENCES wlt.group(id) ON DELETE RESTRICT,
    person_id   uuid NOT NULL REFERENCES core.person(id) ON DELETE RESTRICT,
    joined_on   date NOT NULL,
    exited_on   date,
    exit_reason text CHECK (exit_reason IN
                  ('moved','married_out','died','withdrew','expelled','psnp_exit','group_split')),
    CONSTRAINT membership_period_valid CHECK (exited_on IS NULL OR exited_on >= joined_on),
    CONSTRAINT exit_needs_reason CHECK (exited_on IS NULL OR exit_reason IS NOT NULL)
);

-- Rotating. "Who was treasurer on the date of that disbursement" is a question
-- that gets asked, so never edit in place.
CREATE TABLE wlt.office_holder (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id   uuid NOT NULL REFERENCES wlt.group(id) ON DELETE CASCADE,
    person_id  uuid NOT NULL REFERENCES core.person(id),
    role       text NOT NULL CHECK (role IN ('chair','secretary','treasurer')),
    from_date  date NOT NULL,
    to_date    date,
    CONSTRAINT office_period_valid CHECK (to_date IS NULL OR to_date > from_date)
);

-- Phase 1 evidence item, so it is data rather than a note.
CREATE TABLE wlt.training_event (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id      uuid NOT NULL REFERENCES wlt.group(id) ON DELETE CASCADE,
    module        text NOT NULL CHECK (module IN
                    ('shg_principles','bookkeeping','savings_credit','financial_literacy',
                     'social_empowerment','leadership')),
    held_on       date NOT NULL,
    facilitator_id uuid REFERENCES core.app_user(id)
);

CREATE TABLE wlt.training_attendance (
    training_event_id uuid NOT NULL REFERENCES wlt.training_event(id) ON DELETE CASCADE,
    person_id         uuid NOT NULL REFERENCES core.person(id),
    PRIMARY KEY (training_event_id, person_id)
);

-- Every soft warning a facilitator overrode during formation. Reviewed at
-- woreda level; also tells you which validation rules are wrong for the field.
CREATE TABLE wlt.validation_override (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    uuid NOT NULL REFERENCES wlt.group(id) ON DELETE CASCADE,
    rule_code   text NOT NULL,
    reason      text NOT NULL,
    overridden_by uuid REFERENCES core.app_user(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================
-- SECTION D. MEETINGS AND LEDGER
-- =============================================================================

CREATE TABLE wlt.meeting (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id        uuid NOT NULL REFERENCES wlt.group(id) ON DELETE RESTRICT,
    scheduled_for   date NOT NULL,
    held_on         date,
    meeting_no      integer NOT NULL CHECK (meeting_no > 0),
    bylaw_version_id uuid REFERENCES wlt.bylaw_version(id),

    opening_cash_etb numeric(14,2),
    closing_cash_etb numeric(14,2),
    counted_cash_etb numeric(14,2),      -- what was physically in the box
    social_time_minutes integer CHECK (social_time_minutes >= 0),   -- handbook 3.6, min 15
    social_topic    text,
    social_led_by   uuid REFERENCES core.person(id),

    status          text NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','closed','cancelled')),
    closed_at       timestamptz,
    recorded_by     uuid REFERENCES core.app_user(id),
    device_id       text,                -- offline sync provenance
    synced_at       timestamptz,

    CONSTRAINT closed_needs_counts CHECK (
        status <> 'closed' OR (closing_cash_etb IS NOT NULL AND counted_cash_etb IS NOT NULL)
    )
);

CREATE TABLE wlt.attendance (
    meeting_id uuid NOT NULL REFERENCES wlt.meeting(id) ON DELETE CASCADE,
    person_id  uuid NOT NULL REFERENCES core.person(id),
    status     text NOT NULL CHECK (status IN ('present','absent','absent_excused','late')),
    PRIMARY KEY (meeting_id, person_id)
);

-- Append-only. Corrections are reversals, never edits. See README 5.3.
CREATE TABLE wlt.ledger_entry (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id     uuid NOT NULL REFERENCES wlt.group(id) ON DELETE RESTRICT,
    meeting_id   uuid REFERENCES wlt.meeting(id),
    person_id    uuid REFERENCES core.person(id),      -- null for group-level entries
    entry_type   text NOT NULL CHECK (entry_type IN
                   ('savings','fine','social_fund','loan_disbursement','loan_principal_repayment',
                    'loan_charge_repayment','bank_deposit','bank_withdrawal','write_off','adjustment')),
    account      text NOT NULL DEFAULT 'cash' CHECK (account IN ('cash','bank')),
    amount_etb   numeric(14,2) NOT NULL CHECK (amount_etb <> 0),
    reverses_id  uuid REFERENCES wlt.ledger_entry(id),
    reversal_reason text,
    created_by   uuid REFERENCES core.app_user(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reversal_needs_reason CHECK (reverses_id IS NULL OR reversal_reason IS NOT NULL)
);

CREATE TABLE wlt.loan (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id          uuid NOT NULL REFERENCES wlt.group(id) ON DELETE RESTRICT,
    person_id         uuid NOT NULL REFERENCES core.person(id),
    cycle_batch       integer NOT NULL DEFAULT 1 CHECK (cycle_batch > 0),
    approved_at_meeting_id uuid REFERENCES wlt.meeting(id),
    disbursed_at_meeting_id uuid REFERENCES wlt.meeting(id),
    disbursed_on      date,
    principal_etb     numeric(14,2) NOT NULL CHECK (principal_etb > 0),
    charge_basis      text NOT NULL CHECK (charge_basis IN
                        ('flat_per_loan','per_month','declining_balance')),
    charge_rate       numeric(6,4) NOT NULL CHECK (charge_rate >= 0),
    purpose           text NOT NULL CHECK (purpose IN ('iga','emergency','household','education','other')),
    purpose_note      text,
    due_on            date NOT NULL,
    status            text NOT NULL DEFAULT 'approved' CHECK (status IN
                        ('requested','approved','disbursed','repaid','written_off','cancelled')),
    written_off_on    date,
    write_off_approved_by uuid REFERENCES core.app_user(id),
    CONSTRAINT due_after_disbursal CHECK (disbursed_on IS NULL OR due_on >= disbursed_on)
);

CREATE TABLE wlt.loan_schedule (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id       uuid NOT NULL REFERENCES wlt.loan(id) ON DELETE CASCADE,
    instalment_no integer NOT NULL CHECK (instalment_no > 0),
    due_on        date NOT NULL,
    principal_due_etb numeric(14,2) NOT NULL CHECK (principal_due_etb >= 0),
    charge_due_etb    numeric(14,2) NOT NULL CHECK (charge_due_etb >= 0),
    UNIQUE (loan_id, instalment_no)
);

CREATE TABLE wlt.repayment (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id        uuid NOT NULL REFERENCES wlt.loan(id) ON DELETE RESTRICT,
    meeting_id     uuid REFERENCES wlt.meeting(id),
    paid_on        date NOT NULL,
    principal_etb  numeric(14,2) NOT NULL DEFAULT 0 CHECK (principal_etb >= 0),
    charge_etb     numeric(14,2) NOT NULL DEFAULT 0 CHECK (charge_etb >= 0),
    CONSTRAINT repayment_nonzero CHECK (principal_etb + charge_etb > 0)
);

-- =============================================================================
-- SECTION E. PHASE MACHINE
-- =============================================================================

CREATE TABLE wlt.phase_event (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id           uuid NOT NULL REFERENCES wlt.group(id) ON DELETE CASCADE,
    from_phase         text CHECK (from_phase IN ('p1','p2','p3','p4')),
    to_phase           text NOT NULL CHECK (to_phase IN ('p1','p2','p3','p4')),
    direction          text NOT NULL DEFAULT 'promotion'
                         CHECK (direction IN ('promotion','demotion')),
    submitted_by       uuid REFERENCES core.app_user(id),
    submitted_at       timestamptz,
    decided_by         uuid REFERENCES core.app_user(id),
    decided_at         timestamptz NOT NULL DEFAULT now(),
    policy_version_id  uuid REFERENCES wlt.policy_version(id),
    -- immutable evidence: every gate condition, threshold and actual value
    gate_snapshot      jsonb NOT NULL,
    override_reason    text,
    formation_event_id uuid,          -- set when the transition came from a CLA formation
    CONSTRAINT no_self_approval CHECK (
        submitted_by IS NULL OR decided_by IS NULL OR submitted_by <> decided_by
    )
);

CREATE TABLE wlt.risk_flag (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type text NOT NULL CHECK (subject_type IN ('group','cla','federation')),
    subject_id   uuid NOT NULL,
    reason_code  text NOT NULL CHECK (reason_code IN
                   ('low_attendance','high_par','missed_meetings','no_treasurer',
                    'external_distress','unbalanced_till')),
    raised_on    date NOT NULL DEFAULT current_date,
    cleared_on   date,
    detail       jsonb
);

-- =============================================================================
-- SECTION F. STRUCTURAL LINKAGE   (DECISION D3)
-- Vertical: SHG into CLA, CLA into federation. Exclusive, governance-bearing.
-- Service linkage is NOT here; it lives in referrals.referral. That is the point.
-- =============================================================================

CREATE TABLE wlt.cla (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL,
    kebele_id        uuid NOT NULL REFERENCES core.geography(id),
    formed_on        date NOT NULL,
    constitution_ref text,
    meeting_cadence  text CHECK (meeting_cadence IN ('monthly','quarterly','biannual')),
    status           text NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','at_risk','dormant','dissolved'))
);

CREATE TABLE wlt.federation (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text NOT NULL,
    woreda_id        uuid NOT NULL REFERENCES core.geography(id),
    formed_on        date NOT NULL,
    constitution_ref text,
    status           text NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','at_risk','dormant','dissolved')),
    -- legal registration is a service linkage (referrals.referral of type
    -- cooperative_registration), NOT an attribute here. It has its own lifecycle
    -- and it can fail or lapse.
    legal_status     text NOT NULL DEFAULT 'unregistered'
                       CHECK (legal_status IN ('unregistered','registration_in_progress','registered'))
);

-- Multi-party event that creates a CLA or federation. The ONLY legal path to a
-- structural_membership row.
CREATE TABLE wlt.formation_event (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type    text NOT NULL CHECK (target_type IN ('cla','federation')),
    target_id      uuid,                -- populated on approval
    geography_id   uuid NOT NULL REFERENCES core.geography(id),
    status         text NOT NULL DEFAULT 'open' CHECK (status IN
                     ('open','submitted','returned','approved','rejected','expired')),
    opened_on      date NOT NULL DEFAULT current_date,
    expires_on     date NOT NULL,
    submitted_by   uuid REFERENCES core.app_user(id),
    submitted_at   timestamptz,
    decided_by     uuid REFERENCES core.app_user(id),
    decided_at     timestamptz,
    gate_snapshot  jsonb,
    return_reason  text,
    CONSTRAINT formation_no_self_approval CHECK (
        submitted_by IS NULL OR decided_by IS NULL OR submitted_by <> decided_by
    )
);

CREATE TABLE wlt.formation_candidate (
    formation_event_id uuid NOT NULL REFERENCES wlt.formation_event(id) ON DELETE CASCADE,
    child_type   text NOT NULL CHECK (child_type IN ('group','cla')),
    child_id     uuid NOT NULL,
    included     boolean NOT NULL DEFAULT true,
    exclusion_reason text,
    PRIMARY KEY (formation_event_id, child_type, child_id),
    CONSTRAINT exclusion_needs_reason CHECK (included OR exclusion_reason IS NOT NULL)
);

CREATE TABLE wlt.structural_membership (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_type        text NOT NULL CHECK (parent_type IN ('cla','federation')),
    parent_id          uuid NOT NULL,
    child_type         text NOT NULL CHECK (child_type IN ('group','cla')),
    child_id           uuid NOT NULL,
    joined_on          date NOT NULL,
    exited_on          date,
    exit_reason        text,
    formation_event_id uuid REFERENCES wlt.formation_event(id),
    CONSTRAINT structural_hierarchy_valid CHECK (
        (parent_type = 'cla'        AND child_type = 'group') OR
        (parent_type = 'federation' AND child_type = 'cla')
    ),
    CONSTRAINT structural_period_valid CHECK (exited_on IS NULL OR exited_on >= joined_on),
    CONSTRAINT structural_exit_needs_reason CHECK (exited_on IS NULL OR exit_reason IS NOT NULL)
);

-- Two per SHG, rotating. Handbook 4, phase 3.
CREATE TABLE wlt.delegate (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cla_id      uuid NOT NULL REFERENCES wlt.cla(id) ON DELETE CASCADE,
    group_id    uuid NOT NULL REFERENCES wlt.group(id),
    person_id   uuid NOT NULL REFERENCES core.person(id),
    elected_at_meeting_id uuid REFERENCES wlt.meeting(id),
    from_date   date NOT NULL,
    to_date     date,
    CONSTRAINT delegate_period_valid CHECK (to_date IS NULL OR to_date > from_date)
);
