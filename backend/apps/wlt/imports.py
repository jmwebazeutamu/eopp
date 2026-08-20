"""The PSNP ELS extract as a spreadsheet — the other half of hybrid enrolment.

`enrolment.import_batch` has always known how to bring an extract in. What it
never had was a way to receive one: no endpoint, no parser, no template. So
decision D5's "import the ELS caseload as the candidate pool" — the route it
calls the *main* one, with the facilitator exception deliberately narrow — was
reachable only from a shell.

This module owns the spreadsheet and nothing else: which cell is which field,
and what an Excel value means. Every rule about identity, matching and
verification stays in `enrolment`, because that is where the import and the
facilitator route have to agree.

Two differences from the woreda register at `apps.youth.imports`, both from the
handoff rather than from taste:

- **Not all or nothing.** The youth-side register refuses a whole file on one
  bad row, because a half-imported register leaves nobody able to say which
  half. An ELS extract is thousands of rows from a system nobody here controls,
  and refusing it because forty rows need a woreda officer would mean importing
  nothing. The forty are queued and named. `import_batch` states this too.
- **A fuzzy match is queued, never merged.** Rule 2: merging two different women
  is worse than carrying a duplicate, because one of them loses her savings
  history and neither can be told which.
"""

from apps.youth.imports import ImportColumn, build_template, coerce_row, read_rows
from apps.youth.models import PsnpStatus

from .models import DigitalLiteracy, LiteracyLevel

# Field names are `enrolment.import_row`'s keys, not the model's — the row dict
# is that function's input, and it reads `phone` and `national_id` rather than
# the Youth field names. Renaming them here would break the contract silently.
COLUMNS: list[ImportColumn] = [
    ImportColumn("full_name", "Full name", required=True, note="As written on the ELS register."),
    ImportColumn("date_of_birth", "Date of birth", required=True, kind="date", note="YYYY-MM-DD, or an Excel date."),
    ImportColumn(
        "els_completed_on",
        "ELS package completed",
        required=True,
        kind="date",
        note=(
            "Required. It is one of the four eligibility conditions, and it is also "
            "the consent date the record is held on when the extract carries no other."
        ),
    ),
    ImportColumn(
        "psnp_client_id",
        "PSNP client ID",
        note="The identity key. A row without one needs a woreda officer to resolve the match.",
    ),
    ImportColumn("els_grant_received_on", "ELS grant received", kind="date", note="The second eligibility condition."),
    ImportColumn("els_grant_amount_etb", "ELS grant amount (ETB)"),
    ImportColumn("phone", "Phone"),
    ImportColumn("national_id", "National or kebele ID"),
    ImportColumn("household_id", "PSNP household ID"),
    ImportColumn("psnp_status", "PSNP status", kind="choice", choices=PsnpStatus),
    ImportColumn("primary_iga", "Primary income activity"),
    ImportColumn("literacy_level", "Literacy", kind="choice", choices=LiteracyLevel),
    ImportColumn("digital_literacy", "Digital literacy", kind="choice", choices=DigitalLiteracy),
    ImportColumn(
        "has_device",
        "Has a phone",
        kind="bool",
        note="YES or NO. A group needs at least one member with a device, so this is a formation gate, not a detail.",
    ),
    ImportColumn("household_head", "Household head", kind="bool", note="YES or NO."),
    ImportColumn(
        "consent_date",
        "Consent date",
        kind="date",
        note="Optional. The ELS completion date is used when this is blank.",
    ),
]


def read_extract(stream):
    """`[(sheet_row, {field: raw_cell})]` from an ELS workbook."""
    return read_rows(stream, COLUMNS)


def build_extract_template() -> bytes:
    """The blank extract, built from the same `COLUMNS` the parser reads."""
    return build_template(COLUMNS, title="ELS extract")


def to_rows(parsed):
    """`(rows, rejected)` — raw cells turned into the dicts `import_row` reads.

    Two conversions, and skipping either puts a wrong value in the database
    rather than an error on the screen. `read_rows` returns *raw* cells, so an
    empty optional cell arrives as `None` and a date as whatever Excel stored;
    a blank must then be dropped rather than passed as `""`, because `Youth`'s
    text columns are `NOT NULL` while its date columns reject an empty string.

    A row with an unreadable cell is **rejected here, not imported**. Letting it
    through with the bad cell dropped would silently register a woman with no
    birth date, which is worse than the row not landing: nothing downstream
    would ever say she was incomplete. It is named against its sheet row, which
    is what makes this file not-all-or-nothing rather than merely lenient.
    """
    rows, rejected = [], []
    for row_number, raw in parsed:
        payload, cell_errors = coerce_row(raw, COLUMNS)
        if cell_errors:
            rejected.append({"row": row_number, "errors": cell_errors})
            continue
        rows.append({key: value for key, value in payload.items() if value != "" and value is not None})
    return rows, rejected
