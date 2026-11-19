"""Run LLM field extraction on the labelled tenders and save the answers for scoring.

Writes data/processed/predictions/llm.csv in the same layout as the labels, to be
scored with: python scripts\\evaluate_fields.py llm
With --second-look, fields the model did not find are asked again with the next
pages, and the answers go to llm_v2.csv instead.

The free tier allows about 200,000 tokens a day and a full run needs more, so the
run stops cleanly at the daily limit; running it again the next day reuses every
cached answer and only asks for the missing ones.
"""

import csv
import sys

from openai import RateLimitError

from tender_analyzer.document_check import DEFAULT_MODEL, make_client
from tender_analyzer.field_extraction import (
    ALLOWED_STATUS,
    extract_field,
    extract_field_with_second_look,
)
from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from check_fields import FIELDS_PATH
from evaluate_document_check import PDF_DIR, PROJECT_ROOT
from evaluate_fields import PREDICTIONS_DIR

SECOND_LOOK_FLAG = "--second-look"
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "llm_cache" / "fields" / DEFAULT_MODEL.replace("/", "_")
COLUMNS = ["adam", "field", "status", "value", "page", "notes", "quote"]


def main():
    with FIELDS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        # Only the list of documents is read from the labels, never the answers.
        adams = list(dict.fromkeys(row["adam"] for row in csv.DictReader(handle)))

    # The second look is written to its own file so it can be compared with the first run.
    arguments = sys.argv[1:]
    second_look = SECOND_LOOK_FLAG in arguments
    extract = extract_field_with_second_look if second_look else extract_field
    out_path = PREDICTIONS_DIR / ("llm_v2.csv" if second_look else "llm.csv")

    # Optional ADAMs restrict the run, to try the prompt on a few documents first.
    only = [argument for argument in arguments if argument != SECOND_LOOK_FLAG]
    if only:
        unknown = set(only) - set(adams)
        if unknown:
            print(f"Unknown ADAMs: {', '.join(sorted(unknown))}")
            sys.exit(1)
        adams = [adam for adam in adams if adam in only]

    client = make_client()
    rows, tokens, stopped = [], 0, False
    for adam in adams:
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        for field in ALLOWED_STATUS:
            try:
                answer = extract(pages, field, client, cache_dir=CACHE_DIR)
            except RateLimitError as error:
                # Usually the daily token limit; everything answered so far is cached.
                print(f"\nStopped by the rate limit: {str(error)[:160]}")
                stopped = True
                break
            used = 0 if answer.cached else answer.prompt_tokens + answer.completion_tokens
            tokens += used
            source = "cached" if answer.cached else f"{used} tokens"
            if answer.second_look:
                source += ", from second look"
            print(f"  {adam} {field:<16} {answer.status or 'INVALID':<14} "
                  f"pages {answer.retrieved_pages}  ({source}) {answer.error}")
            rows.append([adam, field, answer.status or "", answer.value,
                         answer.page or "", f"retrieved {answer.retrieved_pages}", answer.quote])
        if stopped:
            break

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    done = len({row[0] for row in rows})
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}: {len(rows)} answers for {done} documents, "
          f"{tokens} new tokens")
    if stopped:
        print("Run the same command again later; cached answers are reused.")


if __name__ == "__main__":
    main()
