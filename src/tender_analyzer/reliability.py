"""Decide whether a page's extracted text can be trusted.

Thresholds come from calibration scripts on the 30-document sample:
- scripts/calibrate_reliability.py: normal pages never exceeded a 0.04
  sigma-error ratio, broken pages were almost always above 0.9, so 0.5 sits
  in the middle of an empty gap.
- scripts/measure_image_coverage.py: low-text pages were either at 0% image
  coverage (blank or signature pages) or at 52-66% (scans), so 0.25 sits in
  the gap; no page with real text exceeded 25% coverage.
"""

from dataclasses import dataclass

from tender_analyzer.text_signals import (
    letter_count,
    sigma_position_error_ratio,
    unassigned_greek_count,
)

SIGMA_ERROR_THRESHOLD = 0.5
LOW_TEXT_LETTERS = 50
SCANNED_IMAGE_COVERAGE = 0.25


@dataclass(frozen=True)
class Reliability:
    reliable: bool
    issues: tuple[str, ...]


def assess_reliability(text, image_coverage=0.0):
    """Judge a page from its normalized text and the share of it covered by images.

    image_coverage is measured by the PDF layer and passed in as a number, so
    this function stays independent of any PDF library and testable on strings.
    """
    issues = []
    if unassigned_greek_count(text) > 0:
        # In the sample, every page containing such a character was broken
        # throughout, under two different corruption patterns, so one is enough.
        issues.append("unassigned_greek_characters")
    sigma = sigma_position_error_ratio(text)
    if sigma is not None and sigma >= SIGMA_ERROR_THRESHOLD:
        issues.append("sigma_position_errors")
    if letter_count(text) < LOW_TEXT_LETTERS and image_coverage >= SCANNED_IMAGE_COVERAGE:
        # Content is an image the extractor cannot read. Flagging it keeps a
        # requirement hidden in a scanned annex from being reported as absent.
        issues.append("possibly_scanned")
    return Reliability(reliable=not issues, issues=tuple(issues))