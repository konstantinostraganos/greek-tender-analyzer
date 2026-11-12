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
- **Re-issued tenders** (*επαναπροκήρυξη*, *επαναληπτικός διαγωνισμός*) are
  `full_tender`. Example: `24PROC014929298`.
- **"Invitation to express interest"** (*πρόσκληση εκδήλωσης ενδιαφέροντος*)
  is `full_tender` when it asks for bids with a deadline and terms.
  Example: `24PROC014197049`.
- **Referring to annexes or laws** (ESPD annex, law 4412/2016) does not make a
  document a `summary`; only a reference to the tender text itself does.
  Examples of `summary`: `24PROC014472491`, `24PROC014206833`.
- **Closed invitations to named companies** are `full_tender` when
  self-contained: the label describes what the document contains, not who
  may bid. Examples: `24PROC014619156`, `24PROC014286978`.
- **Call-offs under a framework agreement** (*εκτελεστική σύμβαση
  συμφωνίας-πλαίσιο*) are `other` when their terms point to the original
  framework tender ("σύμφωνα με την παράγραφο 6.2 της σχετικής διακήρυξης").
  Example: `24PROC014510747`.
- **EU notice forms** (eNotices / TED, form codes like F02, sections
  "Τμήμα I", "II.1.1)") are `eu_notice` even when they list lots and values;
  their selection criteria point to the contract documents.
  Examples: `24PROC014109363`, `24PROC014248706`.
- **Legal preambles** ("Έχοντας υπόψη...") appear in almost every public
  document and do not indicate `decision`; only the absence of
  participation terms does.
- **Documents with unreadable extracted text** are labeled from the PDF as
  displayed; say so in `notes`.
- **If the first pages do not settle the label** (for example, small
  invitations whose first pages are technical specifications), check the
  whole PDF before labeling. Example: `24PROC014385257`.

## Columns

- `evidence_page`: first physical page (as shown in the PDF viewer) where the
  participation terms clearly appear; for long tenders usually the table of contents.
- `notes`: short reason, without commas; write `unsure` when in doubt, to review later.
