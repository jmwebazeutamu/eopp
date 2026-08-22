"""Formation, the phase machine and enrolment — stages 1, 2 and 6.

The split between a hard block and a soft warning is the most likely way to make
this module unusable in the field, so most of this file is about that: what
refuses outright, what warns and can be overridden with a reason, and what gets
written down when somebody overrides one.
"""

from datetime import date

import pytest

from apps.wlt.models import (
    Group,
    GroupStatus,
    MeetingCadence,
    OfficeRole,
    Phase,
    ServiceChargeBasis,
    ValidationOverride,
    VerificationStatus,
)
from apps.wlt.services import enrolment as enrolment_service
from apps.wlt.services import formation as formation_service
from apps.wlt.services import phase as phase_service
from apps.wlt.services.formation import FormationError
from apps.wlt.services.phase import PhaseError

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Hard blocks
# ---------------------------------------------------------------------------


def test_a_pending_woman_cannot_be_added_to_a_group(wlt_draft, make_wlt_member):
    """D5's control on the exception route. Without it the exception path
    becomes the main path."""
    pending = make_wlt_member("Unverified Woman", verification_status=VerificationStatus.PENDING, verified_on=None)
    with pytest.raises(FormationError):
        formation_service.add_member(wlt_draft, pending)


def test_a_woman_without_the_els_package_is_not_programme_eligible(wlt_draft, make_wlt_member):
    ineligible = make_wlt_member("No ELS", els_completed_on=None)
    with pytest.raises(FormationError):
        formation_service.add_member(wlt_draft, ineligible)


def test_a_group_below_the_minimum_cannot_be_constituted(db, wlt_policy, wlt_locations, facilitator, make_wlt_member):
    group = formation_service.open_draft(name="Too Small SHG", kebele=wlt_locations["kebele"], facilitator=facilitator)
    for index in range(10):
        formation_service.add_member(group, make_wlt_member(f"Small {index}"))

    findings = formation_service.validate_roster(group)
    blocking = {finding.code for finding in formation_service.blocking_findings(findings)}
    assert "below_minimum_size" in blocking

    with pytest.raises(FormationError):
        formation_service.constitute(group, actor=facilitator)


def test_a_group_without_a_treasurer_cannot_be_constituted(db, wlt_policy, wlt_locations, facilitator, make_wlt_member):
    group = formation_service.open_draft(
        name="No Treasurer SHG", kebele=wlt_locations["kebele"], facilitator=facilitator
    )
    members = [make_wlt_member(f"Officer {index}") for index in range(20)]
    for person in members:
        formation_service.add_member(group, person)
    formation_service.record_bylaws(
        group,
        meeting_cadence=MeetingCadence.WEEKLY,
        contribution_etb=20,
        service_charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        service_charge_rate="0.05",
    )
    formation_service.elect_officer(group, person=members[0], role=OfficeRole.CHAIR)
    formation_service.elect_officer(group, person=members[1], role=OfficeRole.SECRETARY)

    with pytest.raises(FormationError) as caught:
        formation_service.constitute(group, actor=facilitator)
    assert "treasurer" in " ".join(caught.value.messages).lower()


# ---------------------------------------------------------------------------
# Soft warnings — overridable, and recorded
# ---------------------------------------------------------------------------


@pytest.fixture
def sixteen_member_draft(db, wlt_policy, wlt_locations, facilitator, make_wlt_member):
    """Inside the hard range (15-25), outside the preferred one (18-22)."""
    group = formation_service.open_draft(name="Sixteen SHG", kebele=wlt_locations["kebele"], facilitator=facilitator)
    members = [make_wlt_member(f"Sixteen {index}") for index in range(16)]
    for person in members:
        formation_service.add_member(group, person)
    formation_service.record_bylaws(
        group,
        meeting_cadence=MeetingCadence.WEEKLY,
        contribution_etb=20,
        service_charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        service_charge_rate="0.05",
    )
    for role, person in zip((OfficeRole.CHAIR, OfficeRole.SECRETARY, OfficeRole.TREASURER), members, strict=False):
        formation_service.elect_officer(group, person=person, role=role)
    return group


def test_a_roster_outside_the_preferred_range_warns_and_does_not_block(sixteen_member_draft):
    findings = formation_service.validate_roster(sixteen_member_draft)
    warnings = {finding.code for finding in findings if not finding.blocking}
    assert "size_outside_preferred_range" in warnings
    assert not formation_service.blocking_findings(findings)


def test_constituting_over_an_unaddressed_warning_is_refused(sixteen_member_draft, facilitator):
    """It is not a block, but it is not silent either: somebody has to say why."""
    with pytest.raises(FormationError) as caught:
        formation_service.constitute(sixteen_member_draft, actor=facilitator)
    assert "Record a reason" in " ".join(caught.value.messages)


def test_an_override_is_written_down_with_its_reason(sixteen_member_draft, facilitator):
    formation_service.constitute(
        sixteen_member_draft,
        actor=facilitator,
        overrides={"size_outside_preferred_range": "Only sixteen women in this kebele completed ELS."},
    )
    sixteen_member_draft.refresh_from_db()

    assert sixteen_member_draft.status == GroupStatus.CONSTITUTED
    override = ValidationOverride.objects.get(group=sixteen_member_draft)
    assert override.rule_code == "size_outside_preferred_range"
    assert "sixteen women" in override.reason
    assert override.overridden_by == facilitator


# ---------------------------------------------------------------------------
# Activation and attrition
# ---------------------------------------------------------------------------


def test_a_group_cannot_activate_before_its_first_savings_meeting(wlt_draft, facilitator):
    with pytest.raises(FormationError) as caught:
        formation_service.activate(wlt_draft, actor=facilitator)
    assert "savings meeting" in " ".join(caught.value.messages)


def test_activation_enters_phase_one(wlt_group):
    assert wlt_group.status == GroupStatus.ACTIVE
    assert wlt_group.current_phase == Phase.P1
    assert wlt_group.phase_entered_on == wlt_group.activated_on


def test_an_expired_draft_is_abandoned_and_its_members_return_to_the_pool(
    db, wlt_policy, wlt_locations, facilitator, make_wlt_member
):
    """Retained, not deleted. A kebele that produced no groups is programme
    learning, and it is invisible if only successes are stored."""
    group = formation_service.open_draft(
        name="Stale Draft", kebele=wlt_locations["kebele"], facilitator=facilitator, on_date=date(2026, 1, 1)
    )
    person = make_wlt_member("Stale Member")
    formation_service.add_member(group, person, on_date=date(2026, 1, 1))

    expired = formation_service.expire_stale_drafts(as_of=date(2026, 4, 1))
    group.refresh_from_db()

    assert expired == 1
    assert group.status == GroupStatus.ABANDONED
    assert Group.objects.filter(pk=group.pk).exists()
    # She can join another group tomorrow.
    assert not person.wlt_memberships.filter(exited_on__isnull=True).exists()


def test_a_refused_endorsement_cannot_open_a_draft(db, wlt_policy, wlt_locations, facilitator):
    from apps.wlt.models import MobilisationEvent

    refused = MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"],
        held_on=date(2026, 1, 5),
        facilitator=facilitator,
        endorsement_obtained=False,
    )
    with pytest.raises(FormationError):
        formation_service.open_draft(
            name="Unendorsed SHG",
            kebele=wlt_locations["kebele"],
            facilitator=facilitator,
            mobilisation_event=refused,
        )


# ---------------------------------------------------------------------------
# The allocation ceiling
# ---------------------------------------------------------------------------


def test_activation_past_the_regional_ceiling_needs_a_recorded_override(wlt_draft, facilitator, wlt_locations):
    from apps.wlt.models import EnrolmentAllocation

    EnrolmentAllocation.objects.filter(location=wlt_locations["region"]).update(target_members=5)
    from .conftest import FIRST_MEETING, run_meeting

    run_meeting(
        wlt_draft,
        list(wlt_draft.current_members.values_list("person", flat=True))
        and [membership.person for membership in wlt_draft.memberships.select_related("person")],
        held_on=FIRST_MEETING,
        actor=facilitator,
    )

    with pytest.raises(FormationError) as caught:
        formation_service.activate(wlt_draft, on_date=FIRST_MEETING, actor=facilitator)
    assert "allocation" in " ".join(caught.value.messages).lower()

    formation_service.activate(
        wlt_draft,
        on_date=FIRST_MEETING,
        actor=facilitator,
        allocation_override_reason="Region confirmed the extra group in writing.",
    )
    wlt_draft.refresh_from_db()
    assert wlt_draft.status == GroupStatus.ACTIVE
    assert ValidationOverride.objects.filter(group=wlt_draft, rule_code="allocation_ceiling").exists()


# ---------------------------------------------------------------------------
# The phase machine
# ---------------------------------------------------------------------------


def test_readiness_shows_the_actual_value_next_to_the_threshold(wlt_group):
    """The rule the readiness card exists for. A red dot changes nothing."""
    result = phase_service.readiness(wlt_group)
    attendance = next(c for c in result.conditions if c.code == "attendance")
    assert attendance.threshold == 80
    assert attendance.actual is not None


def test_a_group_failing_its_gate_cannot_be_submitted_without_a_reason(wlt_group, facilitator):
    """Twelve weeks in, the 52-week condition cannot be met, and the refusal
    says so rather than failing generically."""
    with pytest.raises(PhaseError) as caught:
        phase_service.submit(wlt_group, actor=facilitator)
    reasons = " ".join(str(message) for message in caught.value.messages)
    assert "need" in reasons


def test_the_submitter_cannot_approve_her_own_submission(wlt_group, facilitator):
    event = phase_service.submit(wlt_group, actor=facilitator, override_reason="Woreda asked for early review.")
    with pytest.raises(PhaseError):
        phase_service.approve(event, actor=facilitator)


def test_an_approval_moves_the_phase_and_freezes_both_snapshots(wlt_group, facilitator, woreda_officer):
    event = phase_service.submit(wlt_group, actor=facilitator, override_reason="Woreda asked for early review.")
    phase_service.approve(event, actor=woreda_officer)
    wlt_group.refresh_from_db()

    assert wlt_group.current_phase == Phase.P2
    assert event.gate_snapshot["conditions"]
    # Submitted on one set of numbers, decided on another. Both are kept.
    assert event.gate_snapshot["at_decision"] is not None


def test_a_decided_transition_cannot_be_decided_twice(wlt_group, facilitator, woreda_officer, second_woreda_officer):
    event = phase_service.submit(wlt_group, actor=facilitator, override_reason="Woreda asked for early review.")
    phase_service.approve(event, actor=woreda_officer)
    with pytest.raises(PhaseError):
        phase_service.approve(event, actor=second_woreda_officer)


def test_only_one_transition_may_be_pending_per_group(wlt_group, facilitator):
    phase_service.submit(wlt_group, actor=facilitator, override_reason="First request.")
    with pytest.raises(PhaseError):
        phase_service.submit(wlt_group, actor=facilitator, override_reason="Second request.")


def test_a_demotion_is_a_normal_transition_with_evidence(wlt_group, woreda_officer):
    """De-graduation is not an error state. It leaves the same record a
    promotion does, and it is not recorded as a two-party approval — nobody
    submitted it."""
    event = phase_service.demote(
        wlt_group, to_phase=Phase.P1, actor=woreda_officer, reason="Attendance collapsed after the harvest."
    )
    wlt_group.refresh_from_db()

    assert wlt_group.current_phase == Phase.P1
    assert event.direction == "DEMOTION"
    assert event.submitted_by is None
    assert event.decided_by == woreda_officer


def test_the_approval_queue_excludes_what_the_officer_submitted_herself(wlt_group, facilitator, woreda_officer):
    phase_service.submit(wlt_group, actor=facilitator, override_reason="Early review.")
    assert phase_service.pending_for(woreda_officer).count() == 1
    assert phase_service.pending_for(facilitator).count() == 0


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


def test_the_import_is_idempotent_on_the_psnp_client_id(db, wlt_locations, facilitator):
    row = {
        "psnp_client_id": "AM-0001",
        "full_name": "Aster Tadesse",
        "date_of_birth": date(1988, 4, 2),
        "birth_year": 1988,
        "els_completed_on": date(2025, 10, 1),
        "els_grant_received_on": date(2025, 11, 1),
        "consent_date": date(2025, 10, 1),
    }
    first = enrolment_service.import_batch(
        [row], batch="els-2026-01", kebele=wlt_locations["kebele"], actor=facilitator
    )
    second = enrolment_service.import_batch(
        [row], batch="els-2026-01", kebele=wlt_locations["kebele"], actor=facilitator
    )

    assert first["outcomes"]["created"] == 1
    assert second["outcomes"]["skipped"] == 1
    assert second["outcomes"]["created"] == 0


def test_a_close_name_match_is_queued_and_never_merged(db, wlt_locations, facilitator, make_wlt_member):
    """Merging two different women is worse than carrying a duplicate: one of
    them loses her savings history and neither can be told which."""
    from apps.wlt.models import ImportMatchCandidate

    make_wlt_member("Aster Tadesse")
    row = {
        "full_name": "Aster Tadese",  # one letter apart
        "date_of_birth": date(1990, 1, 1),
        "birth_year": 1990,
        "els_completed_on": date(2025, 10, 1),
        "consent_date": date(2025, 10, 1),
    }
    result = enrolment_service.import_batch(
        [row], batch="els-2026-02", kebele=wlt_locations["kebele"], actor=facilitator
    )

    assert result["outcomes"]["queued"] == 1
    assert result["outcomes"]["created"] == 0
    assert ImportMatchCandidate.objects.filter(resolution="PENDING").count() == 1


def test_a_rejected_match_is_recorded_with_a_reason_rather_than_deleted(
    db, wlt_locations, facilitator, woreda_officer, make_wlt_member
):
    from apps.wlt.models import ImportMatchCandidate, MatchResolution

    make_wlt_member("Aster Tadesse")
    enrolment_service.import_batch(
        [
            {
                "full_name": "Aster Tadese",
                "date_of_birth": date(1990, 1, 1),
                "birth_year": 1990,
                "consent_date": date(2025, 10, 1),
            }
        ],
        batch="els-2026-02",
        kebele=wlt_locations["kebele"],
        actor=facilitator,
    )
    candidate = ImportMatchCandidate.objects.get()

    enrolment_service.resolve_match(
        candidate,
        resolution=MatchResolution.REJECTED,
        actor=woreda_officer,
        reason="Different kebele of origin; confirmed with the DA.",
    )
    candidate.refresh_from_db()

    assert candidate.resolution == MatchResolution.REJECTED
    assert "Different kebele" in candidate.resolution_reason


def test_the_exception_route_share_is_reported_per_woreda(db, wlt_locations, make_wlt_member):
    from apps.wlt.models import EnrolmentRoute

    for index in range(9):
        make_wlt_member(f"Imported {index}")
    make_wlt_member("Exception", enrolment_route=EnrolmentRoute.FACILITATOR)

    share = enrolment_service.exception_route_share(location=wlt_locations["woreda"])
    assert share["pct"] == 10
    assert not share["above_threshold"]


# ---------------------------------------------------------------------------
# Looking back at a gate the group has already passed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEarlierGateSets:
    """A promoted group can fall back below the discipline it was promoted on.

    Savings compliance and attendance are continuous, so "does it still meet
    Phase 1?" is a live question for a Phase 2 group — and until the readiness
    card could be pointed at an earlier gate, no screen answered it.
    """

    def _readiness(self, client, group, **params):
        response = client.get(f"/api/v1/wlt/groups/{group.pk}/readiness/", params)
        assert response.status_code == 200
        return response.data

    def test_a_phase_two_group_is_offered_both_gates(self, as_user, facilitator, wlt_group):
        Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)

        data = self._readiness(as_user(facilitator), wlt_group)
        names = [row["name"] for row in data["gate_sets"]]

        assert names == ["forming_to_p1", "p1_to_p2", "p2_to_p3"]
        assert [row["is_next"] for row in data["gate_sets"]] == [False, False, True]

    def test_it_defaults_to_the_next_gate(self, as_user, facilitator, wlt_group):
        Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)

        data = self._readiness(as_user(facilitator), wlt_group)
        assert data["gate_set"] == "p2_to_p3"

    def test_an_earlier_gate_can_be_asked_for(self, as_user, facilitator, wlt_group):
        Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)

        data = self._readiness(as_user(facilitator), wlt_group, gate_set="p1_to_p2")

        assert data["gate_set"] == "p1_to_p2"
        assert data["gate"] is not None
        assert data["gate"]["gate_set"] == "p1_to_p2"
        # Measured now, not frozen at promotion — that is the point of asking.
        assert data["gate"]["computed_at"]

    def test_a_gate_beyond_the_next_one_is_not_offered_or_honoured(self, as_user, facilitator, wlt_group):
        """Its conditions would be measured against a phase the group has not
        entered: real numbers, meaningless comparison."""
        Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P1)

        data = self._readiness(as_user(facilitator), wlt_group, gate_set="p2_to_p3")

        assert [row["name"] for row in data["gate_sets"]] == ["forming_to_p1", "p1_to_p2"]
        assert data["gate_set"] == "p1_to_p2"

    def test_a_junk_gate_set_falls_back_rather_than_erroring(self, as_user, facilitator, wlt_group):
        """The parameter arrives from a URL."""
        data = self._readiness(as_user(facilitator), wlt_group, gate_set="../../etc/passwd")
        assert data["gate_set"] == phase_service.available_gate_sets(wlt_group)[-1]["name"]

    def test_a_forming_group_is_offered_only_its_own_gate(self, as_user, facilitator, wlt_group):
        Group.objects.filter(pk=wlt_group.pk).update(current_phase="")

        data = self._readiness(as_user(facilitator), wlt_group)
        assert [row["name"] for row in data["gate_sets"]] == ["forming_to_p1"]
