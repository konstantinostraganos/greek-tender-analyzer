"""Extract one field of a tender with an LLM that reads only the pages retrieved for it.

Retrieval (retrieval.py) picks the few pages most likely to state the field; the
LLM must answer from those pages alone and copy the sentence it relied on, so the
answer can be checked against the document instead of trusted.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field as dataclass_field
from pathlib import Path

from tender_analyzer.document_check import DEFAULT_MODEL, REASONING_EFFORT
from tender_analyzer.retrieval import FIELD_QUERIES, rank_pages

# Three pages hold the labelled answer for 47 of 50 fields (scripts/evaluate_retrieval.py)
# and still fit one request under the free tier's 8,000 tokens per minute.
TOP_K = 3

# Bounds a single request when a retrieved page is unusually long, such as a dense table.
MAX_PAGE_CHARS = 5000

ALLOWED_STATUS = {
    "deadline": ("stated", "refers_elsewhere", "not_mentioned"),
    "estimated_value": ("stated", "refers_elsewhere", "not_mentioned"),
    "bid_guarantee": (
        "required", "explicitly_not_required", "optional", "refers_elsewhere", "not_mentioned",
    ),
}

COMMON_PROMPT = """\
You extract one field from a Greek public procurement tender.
The excerpt holds the pages most likely to mention the field, each marked "[Page N]" with
its physical page number. Answer only from the excerpt: never use outside knowledge or
typical values, and never compute a value the document does not state.

Answer with a JSON object only:
{"status": one of the allowed statuses,
 "value": the value in the format below, or "" when there is none,
 "page": the N of the [Page N] that holds the quote, or null,
 "quote": the sentence or table cell that states the value, copied character for character
          from the excerpt, without shortening it or adding "...", or null}

If the excerpt does not state the field, answer status "not_mentioned", value "",
page null and quote null. Do not guess.

Field: """

# Written from data/labels/FIELD_GUIDELINES.md, the rules the manual labels follow.
FIELD_PROMPTS = {
    "deadline": """\
the final date and time for submitting offers (καταληκτική ημερομηνία υποβολής or
παραλαβής προσφορών). Not the opening date (αποσφράγιση) and not the start of submission.
Allowed statuses: stated, refers_elsewhere, not_mentioned.
Value: "YYYY-MM-DD HH:MM", or "YYYY-MM-DD" when no time is given. If the deadline is
relative, such as "εντός πέντε (5) ημερών", copy that phrase as the value.""",
    "estimated_value": """\
the estimated value of the whole contract without VAT (εκτιμώμενη αξία, προϋπολογισμός,
προϋπολογισθείσα δαπάνη; "χωρίς ΦΠΑ", "πλέον ΦΠΑ", "μη συμπεριλαμβανομένου ΦΠΑ").
- If amounts with and without VAT are given, use the one without VAT; if only an amount
  with VAT is given, use it.
- With several lots, use the stated total of all lots, not the amount of one lot.
- With options (δικαίωμα προαίρεσης), use a stated total that includes them; if only the
  base amount and the option amount are given separately, use the base amount.
- Amounts named as legal thresholds, and percentages of the value in selection criteria,
  are not the value.
Allowed statuses: stated, refers_elsewhere, not_mentioned.
Value: a plain number with a dot for decimals and no thousands separator, e.g. 15616.13.""",
    "bid_guarantee": """\
the guarantee required to take part in the procedure (εγγύηση συμμετοχής, εγγυητική
επιστολή συμμετοχής). It is not the performance guarantee (εγγύηση καλής εκτέλεσης), not
the advance payment guarantee, and not a product warranty (such as a 12-month warranty on
spare parts).
Allowed statuses: required, explicitly_not_required (the document says no participation
guarantee is needed), optional, refers_elsewhere, not_mentioned.
Value: the percentage and/or amount as stated, e.g. "2% / 312.32", "1014.21", "2%",
"2% per lot"; amounts as plain numbers with a dot for decimals. Leave the value empty
when the guarantee is required without an amount or percentage.""",
}

SPACE_RUN = re.compile(r"[ \t]+")
BLANK_LINES = re.compile(r"\n\s*\n+")
DOT_LEADER = re.compile(r"\.{4,}")


@dataclass(frozen=True)
class FieldAnswer:
    field: str
    status: str | None  # None when the model's answer could not be used
    value: str
    page: int | None
    quote: str
    retrieved_pages: list = dataclass_field(default_factory=list)
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


def _compact(text):
    # Whitespace and contents-page dot leaders carry no meaning but cost tokens.
    text = DOT_LEADER.sub("...", text)
    return BLANK_LINES.sub("\n", SPACE_RUN.sub(" ", text)).strip()


def build_excerpt(pages, page_numbers):
    by_number = {page.number: page for page in pages}
    # Reading order, not rank order, so the model sees the document as it is laid out.
    blocks = [
        f"[Page {n}]\n{_compact(by_number[n].text)[:MAX_PAGE_CHARS]}" for n in sorted(page_numbers)
    ]
    return "\n\n".join(blocks)


def _parse(field, content, retrieved):
    try:
        answer = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"status": None, "value": "", "page": None, "quote": "",
                "error": f"answer is not JSON: {str(content)[:80]!r}"}
    status = answer.get("status")
    if status not in ALLOWED_STATUS[field]:
        return {"status": None, "value": "", "page": None, "quote": "",
                "error": f"status {status!r} not allowed for {field}"}
    page = answer.get("page")
    page = int(page) if str(page).isdigit() else None
    if page is not None and page not in retrieved:
        # A page the model was never shown cannot be its source.
        page = None
    return {
        "status": status,
        "value": str(answer.get("value") or "").strip(),
        "page": page,
        "quote": str(answer.get("quote") or "").strip(),
        "error": "",
    }


def extract_field(pages, field, client, model=DEFAULT_MODEL, cache_dir=None):
    retrieved = rank_pages(pages, FIELD_QUERIES[field])[:TOP_K]
    if not retrieved:
        return FieldAnswer(field, None, "", None, "", [], error="no readable pages")

    system_prompt = COMMON_PROMPT + FIELD_PROMPTS[field]
    user_message = f"Excerpt:\n\n{build_excerpt(pages, retrieved)}"

    # Keyed by everything that shapes the answer, the full prompt text included, so
    # editing the prompt can never return an answer cached for the old wording.
    cache_path = None
    if cache_dir is not None:
        key_source = f"{model}|{REASONING_EFFORT}|{system_prompt}|{user_message}"
        key = hashlib.sha256(key_source.encode()).hexdigest()[:16]
        cache_path = Path(cache_dir) / f"{key}.json"
        if cache_path.exists():
            stored = json.loads(cache_path.read_text(encoding="utf-8"))
            return FieldAnswer(**{**stored, "cached": True})

    options = {"reasoning_effort": REASONING_EFFORT} if model.startswith("openai/gpt-oss") else {}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        **options,
    )
    parsed = _parse(field, response.choices[0].message.content, retrieved)
    answer = FieldAnswer(
        field=field,
        retrieved_pages=retrieved,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        **parsed,
    )

    # Unusable answers are not cached, so the next run asks again.
    if cache_path is not None and answer.status is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(asdict(answer), ensure_ascii=False), encoding="utf-8")
    return answer
