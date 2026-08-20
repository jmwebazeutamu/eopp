-- =============================================================================
-- 002_constraints_indexes.sql
-- Deferred FKs (cross-schema), the invariants that matter, and query indexes.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Cross-schema FKs for the polymorphic referral subject. Added here because
-- wlt.group / wlt.cla / wlt.federation do not exist when 000 runs.
-- This is what a GenericForeignKey cannot give you: real referential integrity.
-- ---------------------------------------------------------------------------
ALTER TABLE referrals.referral
    ADD CONSTRAINT referral_subject_group_fk
        FOREIGN KEY (subject_group_id) REFERENCES wlt.group(id),
    ADD CONSTRAINT referral_subject_cla_fk
        FOREIGN KEY (subject_cla_id) REFERENCES wlt.cla(id),
    ADD CONSTRAINT referral_subject_federation_fk
        FOREIGN KEY (subject_federation_id) REFERENCES wlt.federation(id);

-- Subject type must be permitted for the referral type.
-- This is the safeguarding control: a protection referral type lists 'person'
-- only, so a GBV referral cannot be created against a group.
CREATE OR REPLACE FUNCTION referrals.check_subject_type_allowed()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    allowed  text[];
    subj     text;
BEGIN
    -- NOTE: subject_type is a GENERATED STORED column, so it is not populated
    -- in NEW during a BEFORE trigger. Derive it here instead of reading it.
    subj := CASE
        WHEN NEW.subject_person_id     IS NOT NULL THEN 'person'
        WHEN NEW.subject_group_id      IS NOT NULL THEN 'group'
        WHEN NEW.subject_cla_id        IS NOT NULL THEN 'cla'
        WHEN NEW.subject_federation_id IS NOT NULL THEN 'federation'
    END;

    SELECT allowed_subject_types INTO allowed
      FROM referrals.referral_type WHERE code = NEW.type_code;
    IF allowed IS NULL THEN
        RAISE EXCEPTION 'unknown referral type %', NEW.type_code;
    END IF;
    IF subj IS NULL OR NOT (subj = ANY(allowed)) THEN
        RAISE EXCEPTION 'referral type % does not permit subject type %',
            NEW.type_code, coalesce(subj, 'none');
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER referral_subject_type_allowed
    BEFORE INSERT OR UPDATE ON referrals.referral
    FOR EACH ROW EXECUTE FUNCTION referrals.check_subject_type_allowed();

-- ---------------------------------------------------------------------------
-- INVARIANT 1. One open group membership per person.
-- A woman cannot be in two active SHGs. Enforced in the database, because the
-- hybrid enrolment route makes double-assignment a realistic weekly event.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX group_membership_one_open_per_person
    ON wlt.group_membership (person_id) WHERE exited_on IS NULL;

-- INVARIANT 2. One holder per office per group at a time.
CREATE UNIQUE INDEX office_holder_one_open_per_role
    ON wlt.office_holder (group_id, role) WHERE to_date IS NULL;

-- INVARIANT 3. One open parent per child. A group belongs to at most one CLA.
CREATE UNIQUE INDEX structural_one_open_parent_per_child
    ON wlt.structural_membership (child_type, child_id) WHERE exited_on IS NULL;

-- INVARIANT 4. One bylaw version in force per group.
CREATE UNIQUE INDEX bylaw_one_in_force_per_group
    ON wlt.bylaw_version (group_id) WHERE effective_to IS NULL;

CREATE UNIQUE INDEX bylaw_version_no_unique
    ON wlt.bylaw_version (group_id, version_no);

-- INVARIANT 5. Meeting numbers are unique and sequential per group.
CREATE UNIQUE INDEX meeting_no_unique_per_group
    ON wlt.meeting (group_id, meeting_no);

-- INVARIANT 6. At most two active delegates per group per CLA.
CREATE OR REPLACE FUNCTION wlt.check_delegate_cap()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM wlt.delegate
     WHERE cla_id = NEW.cla_id AND group_id = NEW.group_id AND to_date IS NULL;
    IF n > 2 THEN
        RAISE EXCEPTION 'group % already has 2 active delegates in CLA %',
            NEW.group_id, NEW.cla_id;
    END IF;
    RETURN NEW;
END $$;

-- Deliberately NOT deferred. A deferred constraint trigger only fires at
-- commit, which means the service layer gets no feedback until the whole
-- transaction fails. Immediate feedback is what the facilitator UI needs.
CREATE TRIGGER delegate_cap_two
    AFTER INSERT OR UPDATE ON wlt.delegate
    FOR EACH ROW EXECUTE FUNCTION wlt.check_delegate_cap();

-- INVARIANT 7. A member cannot exit with an outstanding loan.
-- Force settlement, write-off with approval, or transfer first.
CREATE OR REPLACE FUNCTION wlt.check_exit_no_outstanding_loan()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE outstanding numeric;
BEGIN
    IF NEW.exited_on IS NULL THEN RETURN NEW; END IF;
    SELECT coalesce(sum(l.principal_etb),0) - coalesce(sum(r.paid),0) INTO outstanding
      FROM wlt.loan l
      LEFT JOIN LATERAL (
          SELECT sum(principal_etb) AS paid FROM wlt.repayment WHERE loan_id = l.id
      ) r ON true
     WHERE l.person_id = NEW.person_id
       AND l.group_id  = NEW.group_id
       AND l.status IN ('disbursed','approved');
    IF outstanding > 0 THEN
        RAISE EXCEPTION 'member % has ETB % outstanding; settle, write off, or transfer before exit',
            NEW.person_id, outstanding;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER membership_exit_requires_settled_loans
    BEFORE UPDATE ON wlt.group_membership
    FOR EACH ROW EXECUTE FUNCTION wlt.check_exit_no_outstanding_loan();

-- INVARIANT 8. Till must reconcile before a meeting can close.
-- Physical cash counted must equal the computed closing position.
CREATE OR REPLACE FUNCTION wlt.check_meeting_reconciles()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE computed numeric;
BEGIN
    IF NEW.status <> 'closed' THEN RETURN NEW; END IF;
    SELECT coalesce(NEW.opening_cash_etb,0) + coalesce(sum(
        CASE
            WHEN entry_type IN ('savings','fine','social_fund',
                                'loan_principal_repayment','loan_charge_repayment') THEN amount_etb
            WHEN entry_type IN ('loan_disbursement','bank_deposit') THEN -amount_etb
            WHEN entry_type = 'bank_withdrawal' THEN amount_etb
            ELSE 0
        END), 0)
      INTO computed
      FROM wlt.ledger_entry
     WHERE meeting_id = NEW.id AND account = 'cash';

    IF NEW.counted_cash_etb IS DISTINCT FROM computed THEN
        RAISE EXCEPTION 'till does not reconcile: counted % vs computed %',
            NEW.counted_cash_etb, computed;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER meeting_close_requires_reconciliation
    BEFORE UPDATE ON wlt.meeting
    FOR EACH ROW EXECUTE FUNCTION wlt.check_meeting_reconciles();

-- INVARIANT 9. The ledger is append-only. Corrections are reversals, never
-- edits, because members sign the paper register and the digital record has to
-- be defensible against it.
-- INVARIANT 10. Phase decisions are immutable. Later data corrections must not
-- rewrite what was decided, by whom, on what numbers.
CREATE OR REPLACE FUNCTION wlt.block_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; post a reversal or a new event instead',
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
END $$;

CREATE TRIGGER ledger_no_update BEFORE UPDATE ON wlt.ledger_entry
    FOR EACH ROW EXECUTE FUNCTION wlt.block_mutation();
CREATE TRIGGER ledger_no_delete BEFORE DELETE ON wlt.ledger_entry
    FOR EACH ROW EXECUTE FUNCTION wlt.block_mutation();
CREATE TRIGGER phase_event_immutable BEFORE UPDATE OR DELETE ON wlt.phase_event
    FOR EACH ROW EXECUTE FUNCTION wlt.block_mutation();

-- ---------------------------------------------------------------------------
-- Query indexes
-- ---------------------------------------------------------------------------
CREATE INDEX ON wlt.group (kebele_id, status);
CREATE INDEX ON wlt.group (status, current_phase);
CREATE INDEX ON wlt.group_membership (group_id) WHERE exited_on IS NULL;
CREATE INDEX ON wlt.meeting (group_id, held_on DESC);
CREATE INDEX ON wlt.meeting (status) WHERE status = 'open';
CREATE INDEX ON wlt.attendance (person_id);
CREATE INDEX ON wlt.ledger_entry (group_id, created_at DESC);
CREATE INDEX ON wlt.ledger_entry (meeting_id);
CREATE INDEX ON wlt.loan (group_id, status);
CREATE INDEX ON wlt.loan (person_id);
CREATE INDEX ON wlt.repayment (loan_id, paid_on);
CREATE INDEX ON wlt.phase_event (group_id, decided_at DESC);
CREATE INDEX ON wlt.structural_membership (parent_type, parent_id) WHERE exited_on IS NULL;
CREATE INDEX ON wlt.beneficiary_profile (psnp_client_id);
CREATE INDEX ON wlt.beneficiary_profile (verification_status, enrolment_route);
CREATE INDEX ON wlt.risk_flag (subject_type, subject_id) WHERE cleared_on IS NULL;

-- Referral subject lookups: one partial index per subject type.
CREATE INDEX ON referrals.referral (subject_person_id)     WHERE subject_person_id     IS NOT NULL;
CREATE INDEX ON referrals.referral (subject_group_id)      WHERE subject_group_id      IS NOT NULL;
CREATE INDEX ON referrals.referral (subject_cla_id)        WHERE subject_cla_id        IS NOT NULL;
CREATE INDEX ON referrals.referral (subject_federation_id) WHERE subject_federation_id IS NOT NULL;
CREATE INDEX ON referrals.referral (type_code, status);
