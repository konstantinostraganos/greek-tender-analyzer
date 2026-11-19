# TODO

Agreed next steps. Items are removed once done.

## Presentable version
- [ ] CLI command: any PDF -> participation sheet (Step 0 + 3 fields + confidence indicators)
- [ ] README: field results (rules vs LLM v1 vs v2), retrieval recall, stemming negative result,
      second-look regressions, limitations, dev-set caveat
- [ ] README: note that 901882 guarantee amount was correct but scored wrong (Greek number format)
- [ ] Push local commits

## Demo
- [ ] Second-look answers shown as "⚠️ χαμηλότερη βεβαιότητα, έλεγξε τη σελίδα"
- [ ] Unverified quotes shown as "⚠️ η απόδειξη δεν ταιριάζει ακριβώς, έλεγξε τη σελίδα"
- [ ] Normalise Greek-format amounts ("15.820,00€" -> "15820.00")
- [ ] Practical: PyMuPDF size, shared API key and rate limits, AGPL "Source" link
- [ ] Show a fixed Greek explanation per document label instead of the model's English reason

## Test set (new 2025-2026 documents)
- [ ] Label with the same guidelines, evaluate once, no tuning afterwards
- [ ] Add metric: wrong value instead of abstention (missed by the v2 decision criterion)

## Optional
- [ ] Remaining 4 fields
- [ ] "Παραπέμπει αλλού" handling for summaries
- [ ] Pydantic for LLM answer validation
- [ ] Snowball Greek stemmer / embeddings for retrieval
