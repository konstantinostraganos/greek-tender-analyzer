# Document-type labeling guidelines

Labels in `document_types.csv` are manual and judged from the document
content only, not from registry metadata or automatic checks.

## The question

Could a company prepare a bid from this document alone?
In other words: does it contain the participation terms, and is it
self-contained?

## Labels

| Label | Use when | Suitable for extraction |
|---|---|---|
| `full_tender` | Self-contained document with participation terms (deadline, how to submit, required documents, guarantees or criteria). Size does not matter. | yes |
| `summary` | Short notice that refers elsewhere for the full terms ("the full text of the tender is published at..."), even if it states a deadline, value or guarantee. | no |
| `extension` | Notice extending the submission deadline. | no |
| `eu_notice` | EU standard contract notice form (sections like II.1.1). | no |
| `decision` | Decision or administrative act without participation terms. | no |
| `other` | Anything else; explain in `notes`. | no |

## Decisions on edge cases

- **Small invitations** (*πρόσκληση υποβολής προσφορών*) of a few pages are
  `full_tender` if self-contained. Example: `24PROC014904128`.
- **Re-issued tenders** (*επαναπροκήρυξη*) are `full_tender`.
  Example: `24PROC014929298`.
- **Referring to annexes or laws** (ESPD annex, law 4412/2016) does not make a
  document a `summary`; only a reference to the tender text itself does.
  Example of `summary`: `24PROC014472491`.
- **Closed invitations to a single named company** are `full_tender` when
  self-contained: the label describes what the document contains, not who
  may bid. Example: `24PROC014619156`.
- **Documents with unreadable extracted text** are labeled from the PDF as
  displayed; say so in `notes`.

## Columns

- `evidence_page`: first physical page (as shown in the PDF viewer) where the
  participation terms clearly appear; for long tenders usually the table of contents.
- `notes`: short reason, without commas; write `unsure` when in doubt, to review later.

- **"Invitation to express interest"** (*πρόσκληση εκδήλωσης ενδιαφέροντος*)
  is `full_tender` when it asks for bids with a deadline and terms.
  Example: `24PROC014197049`.
- **Legal preambles** ("Έχοντας υπόψη...") appear in almost every public
  document and do not indicate `decision`; only the absence of
  participation terms does.