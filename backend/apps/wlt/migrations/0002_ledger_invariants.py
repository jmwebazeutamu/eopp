"""Database-level invariants for the ledger, the till and the phase record.

The platform's convention is that business rules are explicit application code
and never database triggers (CLAUDE.md, spec §2.3). That rule is about the
referral *state machine*, and it still holds: `Referral.transition_to` and
`ServiceLinkage.transition_to` are Python, and nothing here decides a status.

What is here is integrity: an append-only ledger, a till that must reconcile
before a meeting can close, a phase decision that cannot be rewritten, a member
who cannot walk away from a loan, and a group that cannot seat three delegates.
These are at the database because the service layer is not the only writer — the
admin, a data fix, a management command and the offline sync reconciler all
reach these tables, and an append-only ledger that only one path respects is not
append-only. Members sign the paper register; the digital record has to be
defensible against it.

Each rule is mirrored in `apps.wlt.services`, which is where the readable error
comes from. The trigger is the backstop, and its message is deliberately
specific too — a facilitator seeing "till does not reconcile: counted 5000.00
vs computed 5200.00" can find 200 birr; one seeing "constraint violated" cannot.

Assertions A4, A5, A6, A11, A23, A26 of the handoff's SQL suite.
"""

from django.db import migrations

BLOCK_MUTATION = """
CREATE OR REPLACE FUNCTION wlt_block_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; post a reversal or a new event instead', TG_TABLE_NAME;
END $$;

CREATE TRIGGER wlt_ledger_no_update BEFORE UPDATE ON wlt_ledgerentry
    FOR EACH ROW EXECUTE FUNCTION wlt_block_mutation();
CREATE TRIGGER wlt_ledger_no_delete BEFORE DELETE ON wlt_ledgerentry
    FOR EACH ROW EXECUTE FUNCTION wlt_block_mutation();
CREATE TRIGGER wlt_phase_event_no_delete BEFORE DELETE ON wlt_phaseevent
    FOR EACH ROW EXECUTE FUNCTION wlt_block_mutation();

-- A phase *decision* is immutable. A phase *submission* is not yet a decision:
-- it sits in a woreda queue waiting for somebody to take it, and taking it
-- writes the decision onto the same row. So the row locks at the moment it is
-- decided, not at the moment it is created.
--
-- The alternative was a second table for submissions, which would have split
-- "what was submitted" from "what was decided on it" across two rows that could
-- disagree. One row, locked once, cannot.
CREATE OR REPLACE FUNCTION wlt_block_decided_phase_event()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.decided_at IS NOT NULL THEN
        RAISE EXCEPTION 'a phase decision cannot be rewritten; record a new transition instead';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER wlt_phase_event_decision_immutable BEFORE UPDATE ON wlt_phaseevent
    FOR EACH ROW EXECUTE FUNCTION wlt_block_decided_phase_event();
"""

BLOCK_MUTATION_REVERSE = """
DROP TRIGGER IF EXISTS wlt_ledger_no_update ON wlt_ledgerentry;
DROP TRIGGER IF EXISTS wlt_ledger_no_delete ON wlt_ledgerentry;
DROP TRIGGER IF EXISTS wlt_phase_event_no_delete ON wlt_phaseevent;
-- The name this trigger carried in the first cut of this migration, dropped so
-- a rollback from either version leaves the table clean.
DROP TRIGGER IF EXISTS wlt_phase_event_immutable ON wlt_phaseevent;
DROP TRIGGER IF EXISTS wlt_phase_event_decision_immutable ON wlt_phaseevent;
DROP FUNCTION IF EXISTS wlt_block_decided_phase_event();
DROP FUNCTION IF EXISTS wlt_block_mutation();
"""

# The cash position a closing meeting must match. Sign conventions:
#   in   savings, fines, the social fund, both halves of a repayment
#   out  a disbursement, and cash taken to the bank
#   in   cash drawn back out of the bank
#   n/a  a write-off moves the loan book, not the box
# An adjustment carries its own sign, which is why `amount_etb` may be negative
# and why the only value it may not take is zero.
RECONCILE = """
CREATE OR REPLACE FUNCTION wlt_check_meeting_reconciles()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE computed numeric;
BEGIN
    IF NEW.status <> 'CLOSED' THEN RETURN NEW; END IF;

    SELECT coalesce(NEW.opening_cash_etb, 0) + coalesce(sum(
        CASE
            WHEN entry_type IN ('SAVINGS','FINE','SOCIAL_FUND',
                                'LOAN_PRINCIPAL_REPAYMENT','LOAN_CHARGE_REPAYMENT') THEN amount_etb
            WHEN entry_type IN ('LOAN_DISBURSEMENT','BANK_DEPOSIT') THEN -amount_etb
            WHEN entry_type IN ('BANK_WITHDRAWAL','ADJUSTMENT') THEN amount_etb
            ELSE 0
        END), 0)
      INTO computed
      FROM wlt_ledgerentry
     WHERE meeting_id = NEW.id AND account = 'CASH';

    IF NEW.counted_cash_etb IS DISTINCT FROM computed THEN
        RAISE EXCEPTION 'till does not reconcile: counted % vs computed %',
            NEW.counted_cash_etb, computed;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER wlt_meeting_close_requires_reconciliation
    BEFORE UPDATE ON wlt_meeting
    FOR EACH ROW EXECUTE FUNCTION wlt_check_meeting_reconciles();
"""

RECONCILE_REVERSE = """
DROP TRIGGER IF EXISTS wlt_meeting_close_requires_reconciliation ON wlt_meeting;
DROP FUNCTION IF EXISTS wlt_check_meeting_reconciles();
"""

# A member cannot exit while she owes the group money. Force settlement, an
# approved write-off, or a transfer of the obligation first — otherwise the debt
# leaves the roster with her and the group's fund silently shrinks.
EXIT_NO_LOAN = """
CREATE OR REPLACE FUNCTION wlt_check_exit_no_outstanding_loan()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE outstanding numeric;
BEGIN
    IF NEW.exited_on IS NULL THEN RETURN NEW; END IF;

    SELECT coalesce(sum(l.principal_etb - coalesce(paid.principal, 0)), 0)
      INTO outstanding
      FROM wlt_loan l
      LEFT JOIN LATERAL (
          SELECT sum(r.principal_etb) AS principal FROM wlt_repayment r WHERE r.loan_id = l.id
      ) paid ON true
     WHERE l.person_id = NEW.person_id
       AND l.group_id  = NEW.group_id
       AND l.status IN ('DISBURSED','APPROVED');

    IF outstanding > 0 THEN
        RAISE EXCEPTION 'member has ETB % outstanding; settle, write off, or transfer before exit', outstanding;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER wlt_membership_exit_requires_settled_loans
    BEFORE UPDATE ON wlt_groupmembership
    FOR EACH ROW EXECUTE FUNCTION wlt_check_exit_no_outstanding_loan();
"""

EXIT_NO_LOAN_REVERSE = """
DROP TRIGGER IF EXISTS wlt_membership_exit_requires_settled_loans ON wlt_groupmembership;
DROP FUNCTION IF EXISTS wlt_check_exit_no_outstanding_loan();
"""

# Two delegates per group per CLA. Deliberately not a deferred constraint
# trigger: a deferred one fires at commit, so the service layer would get no
# feedback until the whole transaction failed, and immediate feedback is what
# the delegate-election screen needs.
DELEGATE_CAP = """
CREATE OR REPLACE FUNCTION wlt_check_delegate_cap()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM wlt_delegate
     WHERE cla_id = NEW.cla_id AND group_id = NEW.group_id AND to_date IS NULL;
    IF n > 2 THEN
        RAISE EXCEPTION 'this group already has 2 active delegates in that CLA';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER wlt_delegate_cap_two
    AFTER INSERT OR UPDATE ON wlt_delegate
    FOR EACH ROW EXECUTE FUNCTION wlt_check_delegate_cap();
"""

DELEGATE_CAP_REVERSE = """
DROP TRIGGER IF EXISTS wlt_delegate_cap_two ON wlt_delegate;
DROP FUNCTION IF EXISTS wlt_check_delegate_cap();
"""


class Migration(migrations.Migration):

    dependencies = [("wlt", "0001_initial")]

    operations = [
        migrations.RunSQL(BLOCK_MUTATION, BLOCK_MUTATION_REVERSE),
        migrations.RunSQL(RECONCILE, RECONCILE_REVERSE),
        migrations.RunSQL(EXIT_NO_LOAN, EXIT_NO_LOAN_REVERSE),
        migrations.RunSQL(DELEGATE_CAP, DELEGATE_CAP_REVERSE),
    ]
