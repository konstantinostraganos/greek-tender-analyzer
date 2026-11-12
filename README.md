# Greek Tender Analyzer

A tool that reads the PDF of a Greek public procurement tender notice
(*διακήρυξη*) and produces a structured participation summary: key
requirements such as deadline, estimated value, lots, bid guarantee,
turnover, experience and ISO certifications, each with page number and
exact quoted source text.

The tool supports a human reviewer; it does not decide whether a company
should bid and does not replace legal review.

**Status:**
- Phase 1 complete: reliable per-page text extraction.
- Step 0 complete on the development set: deciding whether a PDF is a full tender.
- Field extraction in progress: ground-truth labels for the first three fields.

## Phase 1 results

All measurements below come from a fixed sample of 30 documents
(1,270 pages) and can be reproduced with the scripts in `scripts/`.

### Choosing a PDF library

Four libraries were compared on the same 30 PDFs using default settings,
first with automatic per-page quality metrics, then by inspecting the eight
pages where they disagreed most against the original PDF.

| Library | Time (30 docs) | Observed problems |
|---|---|---|
| pypdf | 128 s | Splits words (`τη ν`), glues bullets to words (`oAzure`) |
| **PyMuPDF** | **9 s** | None on the inspected pages; also reads signature stamps |
| pdfplumber | 301 s | Reversed text on a rotated table, interleaved columns |
| pypdfium2 | 15 s | Fragments words on a rotated table |

**Chosen: PyMuPDF.** It is licensed under AGPL-3.0, which is why this
project uses the same license. pypdfium2 is the fallback; all PDF access
is isolated in `src/tender_analyzer/pages.py`, so switching affects one file.

### Problems found in real documents

| Problem | Extent in sample | Handling |
|---|---|---|
| **Broken font maps**: text displays correctly but extracts as `ΔΛΛΗΝΙΚΗ ΓΗΜΟΚΡΑΣΙΑ` | 3 of 30 documents; affects every library and even browser copy-paste | Detected, page marked unreliable |
| **Scanned pages**: content is an image with no text layer | 17 pages in 2 documents | Detected, page marked unreliable |
| **Look-alike characters**: MICRO SIGN for μ, Latin `t`, `o`, `x` inside Greek words | 944 mixed-alphabet words, about 1 in 4 pages | Targeted normalization: 944 → 96, remainder mostly legitimate (`οC`, `μm`, `pH`) |
| **Registry stamp** on every page | 1,270 lines | Removed from search text: 1,270 → 0 |
| **Odd characters** found by a scan of symbols next to Greek letters: INCREMENT `∆` for `Δ`, a combining mark used as `π`, soft hyphens inside words | 8 documents use `∆`; one document loses every `π` | Mapped or removed; distinct suspect characters 29 → 26, the rest legitimate or harmless |
| Printed page numbers differ from PDF page order | e.g. PDF page 53 is printed "52" | Physical page numbers are used, so links open the right page |

An earlier feasibility study attributed the corrupted Greek to pypdf.
Comparing four libraries showed the problem is inside the PDFs themselves.

### Reliability detector

A page is marked unreliable if any of these holds:

1. it contains a code point unassigned in the Greek Unicode block (e.g. U+03A2);
2. at least 50% of its words with a lowercase sigma place it impossibly
   (`ς` inside a word, `σ` at the end);
3. it has fewer than 50 letters and images cover at least 25% of it.

Thresholds were set from the data, in the middle of empty gaps: normal pages
never exceeded a 4% sigma-error ratio while broken pages were almost always
above 90%; low-text pages had either 0% image coverage (blank or signature
pages) or 52–66% (scans).

**Result on the sample:** 150 pages flagged in the 4 affected documents,
**0 pages flagged in the other 26.**

Unreliable pages are kept, not dropped, so page numbers stay correct and
later stages can report which pages could not be read instead of treating
missing information as absent.

### Known limitations

- A second corruption pattern (σ → ζ) is caught only through uppercase text;
  a page with only lowercase text of that kind would pass. Recorded as an
  expected-failure test.
- One document drops the initial `Ε` of words (`ΛΛΗΝΙΚΗ`) without any detectable
  signal; it is not repaired.
- False negatives of the detector were not measured systematically: a document
  whose `π` was missing passed as reliable and was only fixed by normalization.
- The sample covers January–June 2024 only; newer documents may behave differently.
- Function-word frequency was tested as a signal and rejected: tables and
  lists have few function words and produced false alarms.

## Step 0: is this PDF the full tender?

The registry attachment is not always the tender itself. Extracting fields from
a summary would report requirements as "not mentioned" when they are only in
another document, which misleads the reader. Step 0 therefore decides first
whether the PDF can be analysed.

### Ground truth

All 30 documents were labeled by hand from their content, with written
guidelines (`data/labels/GUIDELINES.md`). The question: *could a company prepare
a bid from this document alone?*

| Label | Count |
|---|---|
| `full_tender` | 23 |
| `summary` | 2 |
| `eu_notice` (TED / eNotices form) | 2 |
| `decision`, `extension`, `other` | 1 each |

The feasibility study had judged 14 documents usable; the manual labels found 23
full tenders, and the two agreed on only 15 of 30 documents.

### Keyword rules: measured and rejected

The feasibility study's rule (three marker phrases such as *εγγύηση συμμετοχής*)
accepted 11 of 23 full tenders. Twelve were missed: three because their text is
corrupted, nine readable ones, mostly short invitations, because they never use
those phrases.

A table of candidate phrases per label (`scripts/phrase_table.py`) showed why
better phrases do not help: summaries and extensions describe the same tender
with the same words (*υποβολής προσφορ* appears in 19/20 full tenders and in
every other document type), and obvious negative markers are traps
(*περίληψη* appears in 11/20 full tenders, as "a summary of this notice will be
published"). Only the EU form marker `II.1.1)` separated cleanly (2/2 forms, 0/20
tenders).

### Hybrid checker

`src/tender_analyzer/document_check.py`, evaluated by
`scripts/evaluate_document_check.py`:

1. Mostly unreliable text → **undecided**, no request is sent.
2. `II.1.1)` on a readable page → `eu_notice`, by rule.
3. Otherwise an LLM (`openai/gpt-oss-120b` on the Groq free tier) reads the
   first 8,000 characters with page markers and returns JSON. Before choosing a
   label it must copy the sentence, if any, saying that the full terms are in
   another document, and the code checks that the quoted sentence really occurs
   in the text.

| | Spike rule | LLM | + EU form rule | **Final** |
|---|---|---|---|---|
| Full tenders accepted | 11/23 | 20/23 | 20/23 | **19/23** |
| Other documents rejected | 4/7 | 2/7 | 4/7 | **6/7** |
| Wrongly accepted (misleading) | 3 | 5 | 3 | **1** |
| Undecided (corrupted text) | – | 3 | 3 | 3 |

The plain LLM accepted almost everything that mentions a deadline and a
guarantee, including both EU forms despite an explicit instruction. Asking it to
quote the sentence that points elsewhere fixed one of the two summaries and the
framework call-off, at the cost of one missed full tender.
Raising the model's reasoning effort from `low` to `medium` was also measured: it
fixed nothing and used noticeably more of the daily token budget.

**Remaining errors on the development set:**
- `24PROC014206833`, a summary whose terms "are stated in tender no. …", is still
  accepted. Its wording was deliberately not added to the prompt, to avoid
  tuning on a single document.
- `24PROC014197049`, a full tender saying that *this* document is posted on
  Diavgeia, is rejected as a summary. The quote check flagged its answer: the
  model shortened the sentence.

**How much to trust these numbers:** the 30 documents were used to design the
checker, so these are development-set results. To limit overfitting, the number
of prompt changes was capped and the final version was committed before its
run. A test set of newer, unseen documents will give the honest figure.

**Cost:** 2,500–5,200 prompt tokens per document. The free tier's 200,000 tokens
per day allow about one full evaluation per day, so every answer is cached by
the exact text sent, the prompt version and the model settings.

### Design decision from the error analysis

A summary can still contain some fields (deadline, value, guarantee). Instead of
only rejecting it, the tool will mark it as a summary, show the fields it does
state, and report the rest as *Παραπέμπει αλλού* (refers elsewhere) rather than
*Δεν αναφέρεται* (not mentioned).

## Project structure

```
src/tender_analyzer/   application code
  pages.py             PDF -> pages (the only module using the PDF library)
  normalize.py         targeted text normalization
  text_signals.py      measurable text-quality signals
  reliability.py       per-page reliability verdict
  document_check.py    Step 0: is the PDF a full tender (rule + LLM)
scripts/               data preparation and experiments behind every decision
data/labels/           manual ground truth and the guidelines used to write it
tests/                 unit tests for normalization, text signals and reliability
```

## Setup

Requires Python 3.13 (developed on Windows 10).

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-experiments.txt
pip install -e .
pytest
```

The LLM checker needs a free Groq API key in a `.env` file in the project root
(the file is ignored by git):

```
GROQ_API_KEY=your_key_here
```

`requirements.txt` lists only what the application needs;
`requirements-experiments.txt` adds the libraries used by the comparison scripts.

## Data

Documents come from the KHMDHS OpenData API (Greek central electronic
registry of public contracts), licensed CC BY 4.0. Each notice is
identified by its ADAM, the registry's unique posting ID.

| Path | In git | Contents |
|---|---|---|
| `data/sample_manifest.csv` | yes | The fixed sample: one row per document with registry metadata |
| `data/labels/` | yes | Manual document-type and field labels with their guidelines |
| `data/raw/` | no | Source PDFs and registry exports; re-downloadable by ADAM |
| `data/processed/` | no | Extracted text, measurements and cached LLM answers; regenerable |

The sample was drawn at random (fixed seed) from open-procedure service
and supply notices published 1 January – 28 June 2024, by
`scripts/feasibility_spike.py`. To recreate the PDFs:

```cmd
python scripts\download_pdfs.py
```

The attachment endpoint rate-limits well below the documented 350 requests
per minute; rerunning the script fetches only the files that failed.

## License
Copyright (C) 2026 Konstantinos Traganos

GNU AGPL-3.0, see [LICENSE](LICENSE). The project depends on PyMuPDF,
which is also distributed under the AGPL.
