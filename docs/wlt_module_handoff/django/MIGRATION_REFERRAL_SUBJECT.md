# Migration runbook: polymorphic referral subject

**This is the only change in the whole plan that touches live core code.** The youth side is in use. A bad referral migration is visible to case workers within minutes.

Read all of it before running stage 1.

---

## What changes

`referrals.Referral` currently points at a person. After this migration it points at a person, group, CLA or federation.

**Pattern: typed nullable FK columns plus an exactly-one check constraint, and a generated `subject_type` column.**

```python
class Referral(models.Model):
    subject_person     = models.ForeignKey('core.Person',     null=True, blank=True, on_delete=PROTECT, related_name='+')
    subject_group      = models.ForeignKey('wlt.Group',       null=True, blank=True, on_delete=PROTECT, related_name='+')
    subject_cla        = models.ForeignKey('wlt.CLA',         null=True, blank=True, on_delete=PROTECT, related_name='+')
    subject_federation = models.ForeignKey('wlt.Federation',  null=True, blank=True, on_delete=PROTECT, related_name='+')
    # subject_type is a Postgres GENERATED column; declare it read-only in Django
    subject_type       = models.TextField(editable=False)

    SUBJECT_FIELDS = ('subject_person', 'subject_group', 'subject_cla', 'subject_federation')

    @property
    def subject(self):
        for f in self.SUBJECT_FIELDS:
            v = getattr(self, f)
            if v is not None:
                return v
        return None

    class Meta:
        constraints = [
            models.CheckConstraint(
                name='referral_exactly_one_subject',
                check=(...)   # mirror the SQL: num_nonnulls(...) = 1
            )
        ]
```

**Why not `GenericForeignKey`.** The reporting layer runs on materialized views. A GFK cannot be joined in SQL without a contenttypes lookup per row, so every WLT reporting view degrades or needs hand-written unnesting. A GFK also gives no referential integrity: a deleted group leaves dangling referrals. Full reasoning in `DECISIONS.md` D4.

`wlt` depends on `core` and `referrals`. **`core` must never import from `wlt`.** The FKs above live on the referral model, which is in `referrals`, so `referrals` gains a dependency on `wlt`. If that direction is unacceptable in your layout, move the referral app's subject FKs behind a swappable-model setting, or accept the dependency and note it. Do not solve it with a reverse import.

---

## Eight stages

Each stage is a separate deploy. **Do not compress 5 to 8 into one release.**

| # | Action | Verify before proceeding | Rollback |
|---|---|---|---|
| 1 | Add the four nullable FK columns and the generated `subject_type`. No check constraint yet | Migration applies on a production-sized copy inside the maintenance window | Drop the columns |
| 2 | Backfill `subject_person_id` from the existing `person_id`, batched | `count(*) WHERE subject_person_id IS NULL AND person_id IS NOT NULL` returns 0 | Null out the new column |
| 3 | Dual-write: application writes both `person_id` and `subject_person_id` | New referrals appear correctly in both columns for a full day | Stop dual-writing |
| 4 | Parity verification | Row counts match. Spot-check 100 random referrals across statuses and types | Continue dual-writing |
| 5 | Switch reads to the new columns. Add the check constraint as `NOT VALID`, then `VALIDATE CONSTRAINT` in a separate statement | Youth-side referral list, detail and timeline all render. No errors in logs for 48 hours | Switch reads back to `person_id` |
| 6 | Update the timeline component to resolve subject by type | Youth path renders identically. Group-subject referral renders with a group header | Revert the component |
| 7 | Update reporting views to carry a subject-type dimension | Existing youth reports produce identical numbers to the pre-migration run | Revert the views |
| 8 | Drop `person_id`, after a full release cycle with no issues | | Keep the column. There is no urgency to drop it |

`VALIDATE CONSTRAINT` takes a `SHARE UPDATE EXCLUSIVE` lock rather than an `ACCESS EXCLUSIVE` one, which is why it is split from the `NOT VALID` add. On a large referral table this matters.

---

## Regression suite before stage 5

Write these first. They are the safety net.

| Test | Asserts |
|---|---|
| Existing referral list for a case worker | Same rows, same order, same count as pre-migration |
| Referral detail page | All fields render, no missing subject |
| Referral stack timeline | Renders correctly. You already fixed a rendering bug here once, per `REFERRAL_TIMELINE_RENDERING_FIX_PROMPT.md`. Cover that case explicitly |
| Create a person referral through the UI | Lands in `subject_person_id`, `subject_type = 'person'` |
| Youth-side reports | Byte-identical output to a pre-migration run |
| Permissions: case worker | Sees person-subject referrals in scope, and no group-subject referrals |
| Permissions: WLT facilitator | Sees group-subject referrals in scope, and **no youth-side case referrals for the same women** |

That last row is the highest-risk item in the whole plan. Referral visibility now resolves through two different scoping paths, and a leak between modules would appear here first. Test both directions, not just one.

---

## Subject type restrictions

Add alongside the migration, in the same stage as step 5:

```sql
ALTER TABLE referrals.referral_type
    ADD COLUMN allowed_subject_types text[] NOT NULL DEFAULT ARRAY['person'];
```

Backfill every existing type to `ARRAY['person']`, which preserves current behaviour exactly. Then widen the types that should accept groups.

A trigger enforces it. **Note the implementation detail:** `subject_type` is a `GENERATED STORED` column, so it is **not populated in `NEW` during a `BEFORE` trigger**. The trigger derives the type from the FK columns instead. See `sql/002_constraints_indexes.sql`, `referrals.check_subject_type_allowed()`. Getting this wrong makes the safeguarding check silently pass everything, which is exactly the failure you least want.

This is what turns the GBV rule into a constraint: a protection referral type lists `person` only and can never be created against a group, so a disclosure cannot end up on a group timeline.

---

## Provider directory

Two additions while you are in this code:

- `provider_geography`, so a provider is only proposable where it actually operates. A bank present in Amhara is often absent in Afar.
- `rusacco` as a first-class `provider_type`. RUSACCOs are the incumbent rural financial structure in Ethiopia. Lumping them under "other" hides the open question of whether WLT federations compete with them or join them.

---

## What this migration does not do

It does not make the referral engine group-aware in the application layer. Screens, permissions and the linkage lifecycle are stage 7. This migration only makes the data model capable of holding a non-person subject, and proves the youth side is unaffected.
