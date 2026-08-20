# WLT Group Module: developer handoff

**Project:** Ethiopia PSNP 6, Women's Livelihoods Transformation (WLT) pilot
**Deliverable:** a `wlt` module extending the existing youth employment case management platform to handle Self Help Groups
**Stack:** Django + PostgreSQL, same database and auth as the core platform
**Status:** specification. No application code written yet. The SQL in `sql/` is verified.

---

## Read in this order (about 90 minutes)

| # | File | What it gives you | Time |
|---|---|---|---|
| 1 | `START_HERE.md` | this page | 5 min |
| 2 | `DECISIONS.md` | the five decisions already taken, with the rejected alternatives and why | 10 min |
| 3 | `README.md` | module boundary, domain model, the eight linkage workflows | 40 min |
| 4 | `DEFINITIONS.md` | every indicator formula. None of these are in the source handbook, so do not invent your own | 10 min |
| 5 | `sql/` | run it, see 32 assertions pass, then read the DDL | 15 min |
| 6 | `django/MIGRATION_REFERRAL_SUBJECT.md` | the one change to live core code. Read before touching anything | 10 min |
| 7 | `BACKLOG.md` | epics and stories with acceptance criteria | reference |
| 8 | `OPEN_QUESTIONS.md` | ten decisions still with FSCO. Three block the schema | 5 min |

`reference/` holds the source handbook and the three analysis documents this spec was built from. Read them if you want the programme reasoning behind a rule.

---

## Verify the schema in 2 minutes

```bash
createdb wlt_scratch
cd sql
for f in 000_core_stubs.sql 001_wlt_schema.sql 002_constraints_indexes.sql \
         003_policy_seed.sql 004_reporting_views.sql 900_test_seed_and_assertions.sql; do
  psql -d wlt_scratch -v ON_ERROR_STOP=1 -f "$f" || exit 1
done
```

Or just `./run_tests.sh`. Expected last line: `ALL ASSERTIONS PASSED`. Tested on PostgreSQL 16.

`000_core_stubs.sql` is **not** for the real database. It stands in for core platform tables so this package runs standalone, and it documents the contract the module expects from core. Replace each stub with the real table before build and confirm the columns match.

---

## What this module does

Women register individually in the existing registry, then get grouped into SHGs of 15 to 25. Each group meets weekly, saves a fixed amount, lends internally from the pooled fund, and progresses through four maturity phases. Mature groups federate into Cluster Level Associations, and from there connect outward to banks, cooperatives, buyers and services.

Two ideas carry most of the design:

**1. A group is the subject, not a person.** The core platform answers "what is happening to this person". This module answers "what is happening to this group". Hence a separate app.

**2. "Linkage" is two different things.** *Structural* linkage is vertical and exclusive: an SHG belongs to one CLA, a CLA to one federation. It carries governance and delegates. *Service* linkage is external and concurrent: a bank account, a buyer agreement, a credit facility. It carries obligations. They get separate models because they have nothing in common except the word.

Service linkage rides the existing referral engine. A linkage is a referral with a group as the subject instead of a person. That is why stage 0 makes the referral subject polymorphic.

---

## Scope for the pre-pilot

5,000 women, 250 groups, five regions: Somali, Amhara, Afar, Central Ethiopia, Dire Dawa.

**Build stages 0 to 7.** Phase 4 (woreda federations) needs 80 to 120 groups inside one woreda, and the largest regional allocation is 80 groups across a whole region. It cannot be reached in this pilot. Build the schema, defer the UI.

---

## Five things that will bite if you skip them

1. **Offline is the requirement, not a feature.** Afar and Somali were chosen for weak infrastructure. A meeting must record end to end with no signal. In a comparable Uganda pilot, power supply was the single biggest reason groups abandoned digitisation, and groups averaged 1 to 2 smartphones each.

2. **Membership, office and bylaws are dated ranges, not flags.** Attendance and compliance compute against the roster as it stood on the meeting date. A group that raises its contribution in month 8 still needs months 1 to 7 measured against the old figure.

3. **Thresholds live in `wlt.policy_parameter`, never in code.** The source handbook says it is a living document and states some values two or three different ways. Hardcoding 80% or 8 groups means a code change every time FSCO revises one.

4. **Paper stays primary during the pilot.** Members sign the physical register. The digital record runs in parallel and reconciles. Do not build a flow that assumes paper is gone.

5. **A facilitator who can see a group roster must not thereby see those women's youth-side case files.** The join is one line of ORM. Test both directions.
