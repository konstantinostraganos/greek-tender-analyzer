"""Step 0: decide with an LLM whether a PDF is a full tender document.

Keyword rules were measured first (scripts/evaluate_document_check.py,
scripts/phrase_table.py) and could not separate full tenders from summaries and
extensions, because those documents talk about the same tender with the same
words. Telling them apart needs reading comprehension, so an LLM is asked.
"""

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

LABELS = ("full_tender", "summary", "eu_notice", "decision", "extension", "other")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

# The free Groq plan allows 8,000 tokens per minute, prompt and answer together,
# so the excerpt is capped well below that. Greek needs more tokens per character
# than English; the real usage is reported back so this value can be revisited.
MAX_EXCERPT_CHARS = 8000

# Above this share of unreliable pages the text says nothing trustworthy about the
# document, so no request is spent and the document is reported as undecided.
MAX_UNRELIABLE_SHARE = 0.5

# Every EU standard form (TED / eNotices) numbers its fields this way. In the sample it
# appeared in 2/2 EU notices and 0/20 full tenders (scripts/phrase_table.py), and the LLM
# misread both notices as tenders, so this case is settled by rule before any request.
EU_FORM_MARKER = "ii.1.1)"

# How much the gpt-oss models think before answering. "medium" was measured too: it fixed
# none of the misread summaries and used noticeably more of the daily token limit.
REASONING_EFFORT = "low"

# Bumped whenever the prompt changes, so cached answers to an older prompt are not reused.
PROMPT_VERSION = 2

SYSTEM_PROMPT = """\
You classify Greek public procurement documents published in the KHMDHS registry.
The key question: could a company prepare a complete bid using this document alone?

Labels:
- full_tender: a self-contained call for tenders that states the participation terms \
(how, by when and under which conditions to submit an offer). This includes short \
invitations to submit an offer ("πρόσκληση υποβολής προσφοράς"), re-issued tenders and \
closed invitations addressed to named companies. Length does not matter: a two-page \
invitation that contains its terms is a full_tender.
- summary: a short notice that announces a tender but points to another document for the \
full terms (for example "το συνολικό κείμενο της διακήρυξης αναρτάται ..."). Mentioning \
the deadline, the budget or the guarantee does not make it a full_tender.
- eu_notice: an EU standard form (TED / eNotices) with numbered sections such as \
"Τμήμα I" or "II.1.1)".
- decision: an administrative decision (for example approving or awarding) that does not \
itself contain the participation terms. A legal preamble ("Έχοντας υπόψη") alone does not \
make a document a decision.
- extension: a notice that changes an existing tender, typically extending the submission \
deadline, and otherwise refers to the original tender.
- other: anything else, for example a call-off under a framework agreement.

The excerpt is the beginning of the document, possibly cut off. Pages are marked \
"[Page N]" with physical page numbers. The text was extracted from a PDF and may contain \
extraction noise.

Before choosing the label, look for two things and copy the exact sentence if found:
1. refers_elsewhere_quote: a sentence saying that the full tender text or the full \
participation terms are in another document (for example "Το συνολικό κείμενο της \
διακήρυξης αναρτάται ..." or "σύμφωνα με τους όρους της διακήρυξης"). These do NOT count: \
a sentence saying that a summary of THIS document will be published elsewhere \
("Περίληψη της παρούσας ..."), references to laws or decisions, and references to annexes \
of this same document.
2. framework_quote: a sentence showing that this document is a call-off: an invitation to \
the parties of an already concluded framework agreement ("συμφωνία-πλαίσιο") to bid for one \
specific contract ("εκτελεστική σύμβαση"). A tender whose purpose is to conclude a new \
framework agreement ("για τη σύναψη συμφωνίας-πλαισίου") is not a call-off.

Then decide: if refers_elsewhere_quote is found, the document is not self-contained and \
must not be labelled full_tender. If framework_quote is found, label it other.

Answer with a JSON object only:
{"refers_elsewhere_quote": the exact sentence copied from the excerpt, or null,
 "framework_quote": the exact sentence copied from the excerpt, or null,
 "label": one of the labels above,
 "evidence_page": physical page number of the content that decided the label, or null,
 "reason": one short sentence in English}"""

# PDF tables of contents produce long dot leaders that cost tokens and carry no meaning.
DOT_LEADER = re.compile(r"\.{4,}")
SPACE_RUN = re.compile(r"[ \t]+")
BLANK_LINES = re.compile(r"\n\s*\n+")


@dataclass(frozen=True)
class DocumentCheck:
    label: str | None  # None means undecided: unreadable text or an invalid answer
    evidence_page: int | None
    reason: str
    # Sentences the model claims to have found; kept so its decision can be checked.
    refers_elsewhere_quote: str | None = None
    framework_quote: str | None = None
    # False when a quoted sentence is not in the excerpt, i.e. the model invented it.
    quotes_verified: bool = True
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


def make_client():
    load_dotenv()
    # The client already waits and retries on 429, honouring Groq's retry-after header;
    # more retries than the default let a long evaluation run ride out the per-minute limit.
    return OpenAI(base_url=GROQ_BASE_URL, api_key=os.environ["GROQ_API_KEY"], max_retries=8)


def _compact(text):
    text = DOT_LEADER.sub("...", text)
    text = SPACE_RUN.sub(" ", text)
    return BLANK_LINES.sub("\n", text).strip()


def build_excerpt(pages, max_chars=MAX_EXCERPT_CHARS):
    parts, used = [], 0
    for page in pages:
        # Corrupted pages are named but not sent: their letters would mislead the model.
        body = _compact(page.text) if page.reliable else "(unreadable text, omitted)"
        block = f"[Page {page.number}]\n{body}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:  # a tiny fragment of a page adds tokens but no meaning
                parts.append(block[:remaining] + "\n[... excerpt cut off ...]")
            break
        parts.append(block)
        used += len(block) + 1
    return "\n".join(parts)


def _squash(text):
    # Line breaks and spacing differ between what the model copies and the excerpt.
    return " ".join(text.split()).lower()


def _quote(answer, field, excerpt):
    """Return the quoted sentence (or None) and whether it really occurs in the excerpt."""
    quote = answer.get(field)
    if not isinstance(quote, str) or not quote.strip():
        return None, True
    return quote.strip(), _squash(quote) in _squash(excerpt)


def _parse_answer(content, excerpt):
    try:
        answer = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"label": None, "evidence_page": None,
                "reason": f"answer is not JSON: {str(content)[:80]!r}"}
    label = answer.get("label")
    if label not in LABELS:
        return {"label": None, "evidence_page": None, "reason": f"unknown label {label!r}"}
    page = answer.get("evidence_page")
    # Models sometimes return the page as text ("3"); anything non-numeric is dropped.
    page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
    elsewhere, elsewhere_ok = _quote(answer, "refers_elsewhere_quote", excerpt)
    framework, framework_ok = _quote(answer, "framework_quote", excerpt)
    return {
        "label": label,
        "evidence_page": page,
        "reason": str(answer.get("reason", "")),
        "refers_elsewhere_quote": elsewhere,
        "framework_quote": framework,
        "quotes_verified": elsewhere_ok and framework_ok,
    }


def classify_document(pages, client, model=DEFAULT_MODEL, cache_dir=None):
    if not pages:
        return DocumentCheck(None, None, "no pages")
    unreliable_share = sum(1 for page in pages if not page.reliable) / len(pages)
    if unreliable_share > MAX_UNRELIABLE_SHARE:
        return DocumentCheck(None, None, f"{unreliable_share:.0%} of pages unreliable")

    for page in pages:
        if page.reliable and EU_FORM_MARKER in page.text.lower():
            return DocumentCheck("eu_notice", page.number, f"rule: EU form section {EU_FORM_MARKER}")

    excerpt = build_excerpt(pages)

    # Keyed by what is actually sent, so a change in model, prompt or extracted text
    # automatically leads to a fresh request instead of a stale cached answer.
    cache_path = None
    if cache_dir is not None:
        key = hashlib.sha256(f"{model}|{PROMPT_VERSION}|{REASONING_EFFORT}|{excerpt}".encode()).hexdigest()[:16]
        cache_path = Path(cache_dir) / f"{key}.json"
        if cache_path.exists():
            stored = json.loads(cache_path.read_text(encoding="utf-8"))
            return DocumentCheck(**{**stored, "cached": True})

    options = {}
    if model.startswith("openai/gpt-oss"):
        options["reasoning_effort"] = REASONING_EFFORT

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Document excerpt:\n\n{excerpt}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        **options,
    )
    result = DocumentCheck(
        **_parse_answer(response.choices[0].message.content, excerpt),
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
    )

    # Invalid answers are not cached, so the next run asks again instead of repeating them.
    if cache_path is not None and result.label is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding="utf-8")
    return result