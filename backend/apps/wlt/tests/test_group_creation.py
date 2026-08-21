"""Drafting a group over the API — the route that did not exist.

`formation.open_draft` was written, tested and unreachable: `GroupViewSet`
saved the serializer directly, so the one rule the community itself sets — a
meeting that refused endorsement opens no group (A30) — was enforced in the
service and bypassed by every HTTP caller. The mobilisation event had no route
at all, so an endorsed one could only be produced in the admin or a shell.

What is pinned here is that the endorsement gate now holds over HTTP, that the
kebele cannot disagree with the meeting it was drafted from, and that recording
a refusal is a normal thing to do rather than an error.
"""

import pytest

from apps.wlt.models import Group, GroupStatus, MobilisationEvent

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/wlt/mobilisation-events/"
GROUPS = "/api/v1/wlt/groups/"


@pytest.fixture
def endorsed(db, wlt_locations, facilitator):
    return MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"],
        held_on="2026-01-20",
        facilitator=facilitator,
        endorsement_obtained=True,
    )


@pytest.fixture
def refused(db, wlt_locations, facilitator):
    return MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"],
        held_on="2026-01-21",
        facilitator=facilitator,
        endorsement_obtained=False,
        endorsement_note="Elders asked for a second meeting after harvest.",
    )


# ---------------------------------------------------------------------------
# The community meeting
# ---------------------------------------------------------------------------


class TestMobilisationEvent:
    def test_a_facilitator_can_record_a_meeting(self, as_user, facilitator, wlt_locations):
        response = as_user(facilitator).post(
            EVENTS,
            {
                "kebele": wlt_locations["kebele"].code,
                "held_on": "2026-02-02",
                "endorsement_obtained": True,
                "attendees_potential": 24,
                "attendees_elders": 6,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["endorsement_obtained"] is True
        assert response.data["groups_drafted"] == 0

    def test_the_facilitator_is_stamped_from_the_request_not_the_payload(
        self, as_user, facilitator, other_facilitator, wlt_locations
    ):
        """§4.1's `registering_worker` rule: who convened it is not a claim.

        A client that could name somebody else could desynchronise the record
        from who was actually in the room.
        """
        response = as_user(facilitator).post(
            EVENTS,
            {
                "kebele": wlt_locations["kebele"].code,
                "held_on": "2026-02-02",
                "endorsement_obtained": True,
                "facilitator": str(other_facilitator.pk),
            },
            format="json",
        )
        assert response.status_code == 201
        assert str(response.data["facilitator"]) == str(facilitator.pk)

    def test_a_refusal_is_recorded_not_rejected(self, as_user, facilitator, wlt_locations):
        """A30: the row that explains a kebele with no groups in it."""
        response = as_user(facilitator).post(
            EVENTS,
            {
                "kebele": wlt_locations["kebele"].code,
                "held_on": "2026-02-03",
                "endorsement_obtained": False,
                "endorsement_note": "The community declined; the kebele wants a different site.",
            },
            format="json",
        )
        assert response.status_code == 201

    def test_a_refusal_must_say_why(self, as_user, facilitator, wlt_locations):
        """A refusal with no reason is a blank, not programme learning."""
        response = as_user(facilitator).post(
            EVENTS,
            {
                "kebele": wlt_locations["kebele"].code,
                "held_on": "2026-02-03",
                "endorsement_obtained": False,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "endorsement_note" in response.data

    def test_a_meeting_is_held_in_a_kebele(self, as_user, facilitator, wlt_locations):
        response = as_user(facilitator).post(
            EVENTS,
            {
                "kebele": wlt_locations["woreda"].code,
                "held_on": "2026-02-04",
                "endorsement_obtained": True,
            },
            format="json",
        )
        assert response.status_code == 400
        assert "kebele" in response.data

    def test_an_officer_may_read_but_not_record(self, as_user, woreda_officer, endorsed, wlt_locations):
        """Same boundary as every other group record: read and approve, not record."""
        assert as_user(woreda_officer).get(EVENTS).status_code == 200
        refused_write = as_user(woreda_officer).post(
            EVENTS,
            {"kebele": wlt_locations["kebele"].code, "held_on": "2026-02-05", "endorsement_obtained": True},
            format="json",
        )
        assert refused_write.status_code == 403

    def test_a_case_manager_cannot_see_meetings_at_all(self, as_user, case_manager, endorsed):
        """The module boundary holds on the new route too."""
        assert as_user(case_manager).get(EVENTS).status_code == 403

    def test_nothing_deletes_a_meeting(self, as_user, facilitator, endorsed):
        """A refusal only explains an empty kebele for as long as the row lives."""
        assert as_user(facilitator).delete(f"{EVENTS}{endorsed.pk}/").status_code == 405

    def test_endorsed_only_narrows_to_what_a_group_can_be_drafted_from(
        self, as_user, facilitator, endorsed, refused
    ):
        """The form asks for this set, so the server names it.

        A form that offered a refused meeting would collect a submission the
        service is bound to reject.
        """
        every = as_user(facilitator).get(EVENTS)
        assert {row["id"] for row in every.data["results"]} == {str(endorsed.pk), str(refused.pk)}

        usable = as_user(facilitator).get(f"{EVENTS}?endorsed_only=true")
        assert {row["id"] for row in usable.data["results"]} == {str(endorsed.pk)}


# ---------------------------------------------------------------------------
# Drafting the group
# ---------------------------------------------------------------------------


class TestDraftAGroup:
    def test_a_group_is_drafted_from_an_endorsed_meeting(self, as_user, facilitator, endorsed, wlt_locations):
        response = as_user(facilitator).post(
            GROUPS, {"name": "Dessie Zuria Women's SHG", "mobilisation_event": str(endorsed.pk)}, format="json"
        )
        assert response.status_code == 201
        assert response.data["status"] == GroupStatus.DRAFT
        # Derived, not sent.
        assert response.data["kebele"] == wlt_locations["kebele"].pk

        group = Group.objects.get(pk=response.data["id"])
        assert group.mobilisation_event == endorsed
        assert group.facilitator == facilitator
        assert group.drafted_on is not None

    def test_a_refused_meeting_drafts_nothing(self, as_user, facilitator, refused):
        """The gate that did not run over HTTP before this change."""
        response = as_user(facilitator).post(
            GROUPS, {"name": "Should not exist", "mobilisation_event": str(refused.pk)}, format="json"
        )
        assert response.status_code == 400
        assert not Group.objects.filter(name="Should not exist").exists()

    def test_a_group_cannot_be_drafted_without_a_meeting(self, as_user, facilitator, wlt_locations):
        """Omitting the event skips the endorsement check exactly as effectively
        as an unendorsed one would, so it is refused rather than defaulted."""
        response = as_user(facilitator).post(
            GROUPS, {"name": "No meeting", "kebele": wlt_locations["kebele"].code}, format="json"
        )
        assert response.status_code == 400
        assert "mobilisation_event" in response.data
        assert not Group.objects.filter(name="No meeting").exists()

    def test_a_typed_kebele_cannot_disagree_with_the_meeting(
        self, as_user, facilitator, endorsed, wlt_locations
    ):
        """Read-only, like `Case.woreda`. A group that scoped to one place and
        reported in another would be a scoping fault nobody could see."""
        response = as_user(facilitator).post(
            GROUPS,
            {
                "name": "Elsewhere SHG",
                "mobilisation_event": str(endorsed.pk),
                "kebele": str(wlt_locations["other_kebele"].pk),
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["kebele"] == wlt_locations["kebele"].pk

    def test_the_draft_is_visible_to_the_facilitator_who_made_it(self, as_user, facilitator, endorsed):
        created = as_user(facilitator).post(
            GROUPS, {"name": "Mine", "mobilisation_event": str(endorsed.pk)}, format="json"
        )
        listed = as_user(facilitator).get(GROUPS)
        assert created.data["id"] in {row["id"] for row in listed.data["results"]}

    def test_a_group_cannot_be_moved_to_another_meeting(self, as_user, facilitator, endorsed, wlt_locations):
        """The kebele derives from it, so re-pointing it would silently move
        the group between places."""
        created = as_user(facilitator).post(
            GROUPS, {"name": "Fixed", "mobilisation_event": str(endorsed.pk)}, format="json"
        )
        elsewhere = MobilisationEvent.objects.create(
            kebele=wlt_locations["other_kebele"],
            held_on="2026-03-01",
            facilitator=facilitator,
            endorsement_obtained=True,
        )
        moved = as_user(facilitator).patch(
            f"{GROUPS}{created.data['id']}/", {"mobilisation_event": str(elsewhere.pk)}, format="json"
        )
        assert moved.status_code == 400

    def test_one_meeting_can_endorse_more_than_one_group(self, as_user, facilitator, endorsed):
        """Twenty-five women may split into two groups of thirteen and twelve."""
        first = as_user(facilitator).post(
            GROUPS, {"name": "SHG A", "mobilisation_event": str(endorsed.pk)}, format="json"
        )
        second = as_user(facilitator).post(
            GROUPS, {"name": "SHG B", "mobilisation_event": str(endorsed.pk)}, format="json"
        )
        assert first.status_code == 201
        assert second.status_code == 201

        event = as_user(facilitator).get(f"{EVENTS}{endorsed.pk}/")
        assert event.data["groups_drafted"] == 2

    def test_status_cannot_be_set_on_create(self, as_user, facilitator, endorsed):
        """A group starts as a draft. Constituting and activating run gates."""
        response = as_user(facilitator).post(
            GROUPS,
            {"name": "Jump the queue", "mobilisation_event": str(endorsed.pk), "status": GroupStatus.ACTIVE},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["status"] == GroupStatus.DRAFT
