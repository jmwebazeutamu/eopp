"""Hybrid enrolment — handoff decision D5, README §3.4, backlog stage 1.

Import the PSNP ELS caseload as the candidate pool; let facilitators add the
women the extract missed, but start those at `PENDING` and keep them out of any
group until a woreda officer verifies them against PSNP records.

Facilitator-only registration was rejected — 5,000 hand-keyed registrations on
phones in Afar, no eligibility verification, high duplicate risk. Import-only was
rejected too: the extract will be incomplete, and a facilitator standing in front
of a woman who is plainly eligible needs a legitimate route.

Four rules, and the second is the one that matters most:

1. PSNP client ID is the primary match key. A missing ID needs manual
   resolution, not a guess.
2. **Never auto-merge on a fuzzy match.** Merging two different women is worse
   than carrying a duplicate: one of them loses her savings history and neither
   can be told which.
3. A facilitator exception starts `PENDING` and cannot join a group until a
   woreda officer verifies her. This is the control that stops the exception
   path becoming the main path.
4. Duplicate detection runs on **group assignment**, not only on import — the
   realistic failure is the same woman entering through both routes in the same
   week.
"""

import difflib

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.youth.models import PsnpStatus, Sex, Youth

from .. import policy
from ..models import (
    BeneficiaryProfile,
    EnrolmentRoute,
    ImportMatchCandidate,
    MatchResolution,
    VerificationStatus,
)

# Above this, a name-and-place match is offered to a woreda officer to confirm.
# It is never applied automatically at any score: the threshold decides what is
# worth a person's attention, not what is true.
FUZZY_REVIEW_THRESHOLD = 0.86


class EnrolmentError(ValidationError):
    """A refused enrolment operation."""


def _json_safe_row(row):
    """An extract row as JSON.

    `source_row` keeps the row exactly as it arrived, and "exactly" has to
    survive a `JSONField`: a `date` in the dictionary raises on write, which
    silently turned every queued fuzzy match into a row-level import error.
    """
    safe = {}
    for key, value in row.items():
        safe[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return safe


def _name_similarity(left, right):
    return difflib.SequenceMatcher(None, (left or "").lower().strip(), (right or "").lower().strip()).ratio()


def find_matches(row, kebele=None):
    """Candidate identities for one extract row, best first.

    Ethiopian names are patronymic, transliteration varies between offices, and
    a birth year is often an estimate — so a name match alone is evidence, not
    an identification. That is why this returns candidates and never a decision.
    """
    client_id = (row.get("psnp_client_id") or "").strip()
    if client_id:
        exact = BeneficiaryProfile.objects.filter(psnp_client_id=client_id).select_related("person").first()
        if exact is not None:
            return [(exact.person, 1.0)]

    candidates = Youth.objects.filter(sex=Sex.FEMALE)
    if kebele is not None:
        candidates = candidates.filter(kebele=kebele.name)

    scored = []
    for person in candidates[:500]:
        score = _name_similarity(person.full_name, row.get("full_name"))
        birth_year = row.get("birth_year")
        if birth_year and person.date_of_birth:
            # A year apart is normal in a register; five is a different woman.
            gap = abs(person.date_of_birth.year - int(birth_year))
            score -= min(gap, 5) * 0.04
        if score >= FUZZY_REVIEW_THRESHOLD:
            scored.append((person, round(score, 3)))
    return sorted(scored, key=lambda pair: pair[1], reverse=True)


@transaction.atomic
def import_row(row, *, batch, kebele, actor=None, registering_worker=None):
    """Bring one extract row into the registry.

    Returns `(profile_or_none, outcome)` where outcome is one of `linked`,
    `queued`, `created` or `skipped`. Idempotent on the PSNP client id, so
    running the same extract twice creates nothing new.
    """
    client_id = (row.get("psnp_client_id") or "").strip()

    if client_id:
        existing = BeneficiaryProfile.objects.filter(psnp_client_id=client_id).first()
        if existing is not None:
            return existing, "skipped"

    matches = find_matches(row, kebele=kebele)

    if matches and matches[0][1] >= 1.0:
        person, _score = matches[0]
        profile = _attach_profile(person, row, batch=batch, route=EnrolmentRoute.IMPORT, verified=True)
        return profile, "linked"

    if matches:
        # High confidence is a reason to ask, not a reason to merge.
        person, score = matches[0]
        ImportMatchCandidate.objects.create(
            import_batch=batch, source_row=_json_safe_row(row), matched_person=person, confidence=score
        )
        return None, "queued"

    person = Youth.objects.create(
        full_name=row["full_name"],
        sex=Sex.FEMALE,
        date_of_birth=row["date_of_birth"],
        phone_number=row.get("phone", ""),
        national_or_kebele_id=row.get("national_id", ""),
        region=kebele.parent.parent.parent.name,
        zone=kebele.parent.parent.name,
        woreda=kebele.parent.name,
        kebele=kebele.name,
        household_id=row.get("household_id", ""),
        psnp_status=PsnpStatus.ENROLLED,
        # §9 of the youth spec makes consent the basis for holding the record at
        # all, and `Youth.clean` refuses a registration without it. The extract
        # is a PSNP caseload the woman is already enrolled in and consented to;
        # the date carried here is the ELS completion date, which is when she
        # gave it. A row with no such date is refused rather than assumed.
        consent_given=True,
        consent_date=row.get("consent_date") or row.get("els_completed_on"),
        registering_worker=registering_worker or actor,
    )
    profile = _attach_profile(person, row, batch=batch, route=EnrolmentRoute.IMPORT, verified=True)
    return profile, "created"


def _attach_profile(person, row, *, batch, route, verified, verified_by=None):
    profile, created = BeneficiaryProfile.objects.get_or_create(
        person=person,
        defaults={
            "enrolment_route": route,
            "verification_status": VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING,
            "verified_on": timezone.localdate() if verified else None,
            "verified_by": verified_by,
        },
    )
    for field in (
        "psnp_client_id",
        "els_completed_on",
        "els_grant_received_on",
        "els_grant_amount_etb",
        "primary_iga",
        "literacy_level",
        "digital_literacy",
        "has_device",
        "household_head",
    ):
        if row.get(field) not in (None, ""):
            setattr(profile, field, row[field])
    profile.save()
    return profile


@transaction.atomic
def import_batch(rows, *, batch, kebele, actor=None):
    """Run a whole extract. Reports what happened to every row.

    Not all-or-nothing, unlike the youth-side spreadsheet import: an ELS extract
    is thousands of rows from a system nobody here controls, and refusing the
    file because forty rows need a woreda officer would mean importing nothing.
    The forty are queued and named instead.
    """
    outcomes = {"linked": 0, "queued": 0, "created": 0, "skipped": 0}
    errors = []
    for index, row in enumerate(rows, start=1):
        try:
            _profile, outcome = import_row(row, batch=batch, kebele=kebele, actor=actor)
            outcomes[outcome] += 1
        except Exception as exc:  # noqa: BLE001 — the row is reported, the run continues
            errors.append({"row": index, "error": str(exc), "data": row})
    return {"batch": batch, "outcomes": outcomes, "errors": errors}


@transaction.atomic
def resolve_match(candidate, *, resolution, actor, reason=""):
    """A woreda officer's decision on a queued fuzzy match.

    A rejected match is **recorded with a reason, not deleted**: "we looked at
    this and they are different women" is a finding, and deleting it means the
    next import queues the same pair again.
    """
    if candidate.resolution != MatchResolution.PENDING:
        raise EnrolmentError(_("This match has already been resolved."))
    if resolution == MatchResolution.REJECTED and not reason.strip():
        raise EnrolmentError({"reason": _("Say why these are different women.")})

    candidate.resolution = resolution
    candidate.resolution_reason = reason
    candidate.resolved_by = actor
    candidate.resolved_at = timezone.now()
    candidate.save(update_fields=["resolution", "resolution_reason", "resolved_by", "resolved_at", "updated_at"])

    if resolution == MatchResolution.CONFIRMED:
        return _attach_profile(
            candidate.matched_person,
            candidate.source_row,
            batch=candidate.import_batch,
            route=EnrolmentRoute.IMPORT,
            verified=True,
            verified_by=actor,
        )
    return None


@transaction.atomic
def add_by_facilitator(*, person, actor, note=""):
    """The exception route. Starts pending, and cannot join a group until verified."""
    if BeneficiaryProfile.objects.filter(person=person).exists():
        raise EnrolmentError(_("This woman already has a WLT profile."))
    return BeneficiaryProfile.objects.create(
        person=person,
        enrolment_route=EnrolmentRoute.FACILITATOR,
        verification_status=VerificationStatus.PENDING,
        verification_note=note,
    )


@transaction.atomic
def register_by_facilitator(*, kebele, actor, note="", profile_fields=None, **person_fields):
    """Register a woman the extract missed, and open her WLT profile in one step.

    The exception route needed a `Youth` row before this existed, and no WLT role
    can create one: `YouthViewSet` is gated on `CanAccessCases` and every WLT
    role has `case_scope: NONE`. So rule 3 above described a path that stopped at
    its first step, and the only real way in was the import.

    Creating the person here does **not** breach the module boundary. Registering
    someone is not reading their case file: this writes `youth.Youth` and nothing
    in `apps.cases`, and the facilitator still gets 403 on every case route. That
    is the same trade `import_row` already makes — it creates `Youth` rows too.

    The place fields are derived from the kebele rather than accepted from the
    caller, for the reason the youth-side importer gives: a hand-typed woreda
    that disagrees with the kebele's parent produces a record that scopes to one
    place and reports in another.
    """
    if person_fields.get("sex") not in (None, Sex.FEMALE):
        # Not a validation nicety. `programme_eligible` filters on FEMALE, so a
        # man registered here would sit in the registry permanently unaddable,
        # with nothing on screen saying why.
        raise EnrolmentError({"sex": _("The WLT programme enrols women.")})

    # Refused on the identity key only. A name match is *evidence* and rule 2
    # forbids turning it into a decision — two women in one kebele really can
    # share a name, and refusing the second is as wrong as merging her. Rule 4
    # puts the duplicate check where it can be answered by a person: group
    # assignment, where `add_member` refuses a second open membership outright.
    client_id = ((profile_fields or {}).get("psnp_client_id") or "").strip()
    if client_id and BeneficiaryProfile.objects.filter(psnp_client_id=client_id).exists():
        raise EnrolmentError({"psnp_client_id": _("A woman with this PSNP client ID is already on the register.")})

    person_fields.setdefault("sex", Sex.FEMALE)
    person_fields.setdefault("psnp_status", PsnpStatus.ENROLLED)
    person = Youth.objects.create(
        region=kebele.parent.parent.parent.name,
        zone=kebele.parent.parent.name,
        woreda=kebele.parent.name,
        kebele=kebele.name,
        registering_worker=actor,
        **person_fields,
    )

    profile = add_by_facilitator(person=person, actor=actor, note=note)
    profile.psnp_kebele = kebele
    profile.psnp_woreda = kebele.parent
    for field, value in (profile_fields or {}).items():
        setattr(profile, field, value)
    profile.save()
    return profile


@transaction.atomic
def verify(profile, *, actor, approved, reason=""):
    """A woreda officer confirms or refuses an exception-route registration."""
    if not approved and not reason.strip():
        raise EnrolmentError({"reason": _("Say why this registration is refused.")})

    profile.verification_status = VerificationStatus.VERIFIED if approved else VerificationStatus.REJECTED
    profile.verified_by = actor
    profile.verified_on = timezone.localdate()
    profile.verification_note = reason
    profile.save(update_fields=["verification_status", "verified_by", "verified_on", "verification_note", "updated_at"])
    return profile


def exception_route_share(location=None):
    """The share of enrolments that came through the facilitator route.

    Past the alert threshold — 10% by default — the extract is the problem and
    should be fixed rather than worked around. Reported per woreda so the answer
    points at an office rather than at the programme.
    """
    profiles = BeneficiaryProfile.objects.all()
    if location is not None:
        profiles = profiles.filter(psnp_woreda=location)
    total = profiles.count()
    if not total:
        return None
    exception = profiles.filter(enrolment_route=EnrolmentRoute.FACILITATOR).count()
    share = round(100 * exception / total)
    return {
        "total": total,
        "exception_route": exception,
        "pct": share,
        "above_threshold": share > policy.resolve_int("enrolment.exception_route_alert_pct", default=10),
    }
