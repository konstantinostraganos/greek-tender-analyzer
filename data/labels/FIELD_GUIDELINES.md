# Field labeling guidelines

Values in `fields.csv` are manual, read from the PDF itself, and are the ground
truth that every extraction method is scored against. They are written without
looking at any model output, so that a model is never graded against its own
answers.

## Scope

- Documents: the full tenders in `document_types.csv` whose text is readable
  (20 in the 2024 sample). They form the development set; the test set will be
  newer documents labeled the same way.
- Fields (first version): `deadline`, `estimated_value`, `bid_guarantee`.

## Columns

One row per document and field.

| Column | Content |
|---|---|
| `adam` | Pre-filled. |
| `field` | Pre-filled. |
| `status` | One of the status codes below. |
| `value` | The value in the format given for each field; empty when there is none. |
| `page` | Physical page (as in the PDF viewer, not the printed number) where the value is stated first. Empty when there is none. |
| `notes` | Anything unusual, `unsure` when in doubt. No commas. |
| `quote` | The sentence that states the value, copied from the PDF, **always inside double quotes** (`"..."`) because it may contain commas. Empty when there is none. |

## Status codes

Codes are used instead of the Greek labels so that typing accents cannot
create mismatches; the application shows the Greek label.

| Code | Shown as | Use when |
|---|---|---|
| `stated` | Αναφέρεται | An informational field (deadline, value) is given. |
| `required` | Απαιτείται | A requirement (guarantee) applies. |
| `explicitly_not_required` | Ρητά δεν απαιτείται | The document says the requirement does not apply. |
| `optional` | Προαιρετικό | The document makes it optional. |
| `refers_elsewhere` | Παραπέμπει αλλού | The document points to another document for it. |
| `not_mentioned` | Δεν αναφέρεται | The document says nothing about it. This is a valid answer, not a failure. |

## Fields

### `deadline`

- Only the final date for **submitting offers** (*καταληκτική ημερομηνία
  υποβολής προσφορών*); not the opening date and not the start of submission.
- `value`: `YYYY-MM-DD HH:MM`, e.g. `2024-04-11 13:00`. Without a time, only
  `YYYY-MM-DD` and `no time` in `notes`.
- A relative deadline ("within 5 days from ...") is copied as text in `value`
  and `relative deadline` goes in `notes`.
- Status: `stated`, `refers_elsewhere` or `not_mentioned`.

### `estimated_value`

- The amount **without VAT** for the **whole contract** (all lots together).
- `value`: plain number with a dot for decimals, e.g. `145000.00`
  (the PDF's `145.000,00 €` becomes `145000.00`).
- Options (*δικαίωμα προαίρεσης*): if the document states a total that includes
  them, use that total; if it gives only the parts, use the base value and write
  the option amount in `notes`. Record what the document says; do not add.
- If only an amount with VAT is given, use it and write `with VAT` in `notes`.
- If the value is per year or per lot only, use what is stated and say so in
  `notes`.
- Status: `stated`, `refers_elsewhere` or `not_mentioned`.

### `bid_guarantee`

- The guarantee for **taking part** (*εγγύηση συμμετοχής*), not the performance
  guarantee (*εγγύηση καλής εκτέλεσης*).
- `value`: percentage and/or amount as stated, e.g. `1% / 1450.00`;
  per lot: `2% per lot`.
- Status: `required`, `explicitly_not_required` (the document says it is not
  needed), `refers_elsewhere` or `not_mentioned` (common in small invitations).
