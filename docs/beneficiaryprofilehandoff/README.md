# Beneficiary profile — handoff package

Route: `/wlt/beneficiaries/:id`
Spec: https://claude.ai/code/artifact/79f79c72-223a-489f-9c31-f14d49f9d0ca (read this first)
Design canvas: https://claude.ai/code/artifact/79f79c72-223a-489f-9c31-f14d49f9d0ca

## Contents

```
css/beneficiary-profile.css      new styles, zero new tokens; import after the main stylesheet
react/types.ts                   API types
react/format.ts                  money, date, phone, initials
react/Fact.tsx                   label/value cell; renders "Add" for a null
react/BeneficiaryIdentityHeader.tsx
react/PathwayStageList.tsx       replaces the summary block AND the four check cards
react/SavingsSummaryCard.tsx
react/BeneficiaryProfilePage.tsx route component and layout shell
api/models_delta.py              13 new fields, all nullable
api/serializers.py               grouped response, money as string
api/beneficiary-detail.example.json   fixture for tests and Storybook
```

## Three rules that carry the whole change

1. **A missing value is never blank and never "N/A".** It is a gold Add control
   that opens the edit form on that field. See `Fact.tsx`.
2. **Money is a decimal string end to end.** Never `parseFloat`. See `formatMoney`.
3. **Ship `PathwayStageList` and delete the old blocks in one commit.** Landing it
   alone puts three copies of the same checks on the page.

## Assumptions to check

- Component file paths follow `src/features/beneficiaries/`. Move them to match
  your convention; nothing imports by absolute path.
- `geo.Woreda` and `staff.Staff` are the app names for those models.
- Contact log, enterprise and grievance relations exist and are annotatable.

Six open questions are listed at the end of the spec page. They change the schema,
so answer them before the first migration.
