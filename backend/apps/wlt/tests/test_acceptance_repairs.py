import pytest

from apps.partners.models import PartnerType
from apps.wlt.models import Group, LinkageStatus, MobilisationEvent, Phase
from apps.wlt.services import linkage as linkage_service
from apps.wlt.services import formation as formation_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def endorsed_meeting(wlt_locations, facilitator):
    return MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"], held_on="2026-08-20", facilitator=facilitator,
        endorsement_obtained=True,
    )


@pytest.mark.parametrize("actor_fixture", ["system_admin", "woreda_officer"])
def test_admin_and_woreda_officer_can_draft_with_an_explicit_facilitator(
    request, as_user, actor_fixture, facilitator, endorsed_meeting
):
    actor = request.getfixturevalue(actor_fixture)
    response = as_user(actor).post(
        "/api/v1/wlt/groups/",
        {"name": f"{actor_fixture} group", "mobilisation_event": str(endorsed_meeting.pk), "facilitator": str(facilitator.pk)},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["facilitator"] == facilitator.pk


def test_facilitator_picker_is_scoped_to_the_chosen_kebele(as_user, system_admin, facilitator, wlt_locations):
    facilitator.wlt_scope_location = wlt_locations["woreda"]
    facilitator.save(update_fields=["wlt_scope_location"])
    response = as_user(system_admin).get(
        f"/api/v1/users/wlt-facilitators/?kebele={wlt_locations['kebele'].pk}"
    )
    assert response.status_code == 200
    assert str(facilitator.pk) in {str(row["id"]) for row in response.data}


def test_bulk_roster_add_uses_the_same_member_rules(as_user, facilitator, endorsed_meeting, make_wlt_member):
    group = formation_service.open_draft(
        name="Bulk roster", kebele=endorsed_meeting.kebele, facilitator=facilitator,
        mobilisation_event=endorsed_meeting,
    )
    people = [make_wlt_member("Bulk One"), make_wlt_member("Bulk Two")]
    response = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{group.pk}/members/",
        {"people": [str(person.pk) for person in people]}, format="json",
    )
    assert response.status_code == 201
    assert len(response.data) == 2


def test_resolution_and_obligation_resolution_are_immutable_evidence(wlt_group, make_partner, facilitator):
    Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)
    wlt_group.refresh_from_db()
    bank = make_partner(name="Repair test bank", partner_type=PartnerType.FINANCE_INSTITUTION, woredas=[wlt_group.kebele.parent.name])
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=wlt_group, provider=bank, actor=facilitator
    )
    linkage_service.record_resolution(linkage, reference="MIN-42", actor=facilitator)
    assert linkage.events.filter(reason__contains="MIN-42").exists()

    linkage.status = LinkageStatus.ACTIVE
    linkage.save(update_fields=["status"])
    linkage_service.record_obligation(linkage, kind="payment", reference="PAY-1", actor=facilitator)
    linkage_service.resolve_obligation(
        linkage, reference="PAY-1", resolution="SETTLED", note="Bank receipt checked", actor=facilitator
    )
    register = linkage_service.obligation_register(linkage)
    assert register[0]["outstanding"] is False
    linkage.refresh_from_db()
    assert linkage.terms["outstanding_obligation"] is False
