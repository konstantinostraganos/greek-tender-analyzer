# Greek Tender Analyzer

A tool that reads the PDF of a Greek public procurement tender notice
(*διακήρυξη*) and produces a structured participation summary: key
requirements such as deadline, estimated value, lots, bid guarantee,
turnover, experience and ISO certifications, each with page number and
exact quoted source text.

The tool supports a human reviewer; it does not decide whether a company
should bid and does not replace legal review.

**Status:** Phase 1 complete — reliable per-page text extraction.
Requirement extraction is not implemented yet.

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
- The sample covers January–June 2024 only; newer documents may behave differently.
- Function-word frequency was tested as a signal and rejected: tables and
  lists have few function words and produced false alarms.

## Project structure

```
src/tender_analyzer/   application code
  pages.py             PDF -> pages (the only module using the PDF library)
  normalize.py         targeted text normalization
  text_signals.py      measurable text-quality signals
  reliability.py       per-page reliability verdict
scripts/               data preparation and experiments behind every decision
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

`requirements.txt` lists only what the application needs;
`requirements-experiments.txt` adds the libraries used by the comparison scripts.

## Data

Documents come from the KHMDHS OpenData API (Greek central electronic
registry of public contracts), licensed CC BY 4.0. Each notice is
identified by its ADAM, the registry's unique posting ID.

| Path | In git | Contents |
|---|---|---|
| `data/sample_manifest.csv` | yes | The fixed sample: one row per document with registry metadata |
| `data/raw/` | no | Source PDFs and registry exports; re-downloadable by ADAM |
| `data/processed/` | no | Extracted text and measurements; regenerable |

The sample was drawn at random (fixed seed) from open-procedure service
and supply notices published 1 January – 28 June 2024, by
`scripts/feasibility_spike.py`. To recreate the PDFs:

```cmd
python scripts\download_pdfs.py
```

The attachment endpoint rate-limits well below the documented 350 requests
per minute; rerunning the script fetches only the files that failed.

## License

GNU AGPL-3.0, see [LICENSE](LICENSE). The project depends on PyMuPDF,
which is also distributed under the AGPL.