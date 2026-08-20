-- =============================================================================
-- 000_core_stubs.sql
-- Minimal stand-ins for CORE platform tables, so this package runs standalone.
--
-- DO NOT APPLY THIS FILE TO THE REAL DATABASE.
-- It exists to (a) document the contract the wlt schema expects from core, and
-- (b) let a developer run 001..900 on a scratch database and see the assertions
-- pass before touching the real system.
--
-- Before build: replace each stub with the real core table and confirm the
-- column names and types below actually match.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS referrals;

-- ---------------------------------------------------------------------------
-- Geography: region > woreda > kebele. Self-referencing, as core already has.
-- ---------------------------------------------------------------------------
CREATE TABLE core.geography (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id    uuid REFERENCES core.geography(id),
    level        text NOT NULL CHECK (level IN ('country','region','zone','woreda','kebele')),
    name         text NOT NULL,
    code         text UNIQUE
);

-- ---------------------------------------------------------------------------
-- Person: the single identity. DECISION D1 - registry stays as is.
-- The wlt module never creates its own person table.
-- ---------------------------------------------------------------------------
CREATE TABLE core.person (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name     text NOT NULL,
    sex           text CHECK (sex IN ('female','male','other')),
    birth_year    integer,
    kebele_id     uuid REFERENCES core.geography(id),
    phone         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text UNIQUE NOT NULL,
    role          text NOT NULL CHECK (role IN
                    ('wlt_facilitator','woreda_fsco','region_fsco','federal_fsco','readonly')),
    scope_geo_id  uuid REFERENCES core.geography(id)
);

-- ---------------------------------------------------------------------------
-- Referral: TARGET STATE after the polymorphic-subject migration.
-- DECISION D4 - service linkage rides this engine.
-- See django/MIGRATION_REFERRAL_SUBJECT.md for how to get here from the
-- current person-only shape without downtime.
-- ---------------------------------------------------------------------------
CREATE TABLE referrals.referral_type (
    code                  text PRIMARY KEY,
    label                 text NOT NULL,
    allowed_subject_types text[] NOT NULL,   -- safeguarding control, see README 6.4
    restricted            boolean NOT NULL DEFAULT false,
    approval_chain        text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE referrals.provider (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL,
    provider_type  text NOT NULL CHECK (provider_type IN
                     ('bank','mfi','rusacco','cooperative','buyer','govt_service','ngo')),
    status         text NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended','blacklisted')),
    contact        text
);

-- A provider is only proposable where it actually operates.
CREATE TABLE referrals.provider_geography (
    provider_id  uuid NOT NULL REFERENCES referrals.provider(id) ON DELETE CASCADE,
    geography_id uuid NOT NULL REFERENCES core.geography(id),
    PRIMARY KEY (provider_id, geography_id)
);

CREATE TABLE referrals.referral (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_code             text NOT NULL REFERENCES referrals.referral_type(code),
    provider_id           uuid REFERENCES referrals.provider(id),

    -- Polymorphic subject: typed nullable FKs + exactly-one check.
    -- Rejected alternative: Django GenericForeignKey. See DECISIONS.md D4.
    subject_person_id     uuid REFERENCES core.person(id),
    subject_group_id      uuid,   -- FK added in 002 (wlt.group not yet created here)
    subject_cla_id        uuid,   -- FK added in 002
    subject_federation_id uuid,   -- FK added in 002

    subject_type text GENERATED ALWAYS AS (
        CASE
            WHEN subject_person_id     IS NOT NULL THEN 'person'
            WHEN subject_group_id      IS NOT NULL THEN 'group'
            WHEN subject_cla_id        IS NOT NULL THEN 'cla'
            WHEN subject_federation_id IS NOT NULL THEN 'federation'
        END
    ) STORED,

    status       text NOT NULL DEFAULT 'proposed' CHECK (status IN
                   ('proposed','screened','blocked','pending_approval','returned',
                    'approved','rejected','lapsed','active','distressed','defaulted','closed')),
    opened_on    date NOT NULL DEFAULT current_date,
    closed_on    date,
    value_etb    numeric(14,2),
    terms        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by   uuid REFERENCES core.app_user(id),
    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT referral_exactly_one_subject CHECK (
        num_nonnulls(subject_person_id, subject_group_id,
                     subject_cla_id, subject_federation_id) = 1
    )
);

-- Timeline events. The existing referral stack timeline component reads these.
CREATE TABLE referrals.referral_event (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id   uuid NOT NULL REFERENCES referrals.referral(id) ON DELETE CASCADE,
    from_status   text,
    to_status     text NOT NULL,
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    actor_id      uuid REFERENCES core.app_user(id),
    reason        text,
    gate_snapshot jsonb          -- immutable evidence: indicator values at decision time
);
