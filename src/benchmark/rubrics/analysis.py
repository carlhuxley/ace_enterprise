"""AnalysisRubric — evaluates analytical / research output.

Dimensions (weights sum to 1.0):
  coverage    0.30  addresses multiple aspects / sections
  reasoning   0.30  logical connectives and conclusions present
  accuracy    0.25  well-structured sentences, consistent voice
  citations   0.15  references or evidence markers present

Bead: ace_enterprise-nf7
"""

from __future__ import annotations

import re

from src.benchmark.rubrics.base import EvaluationRubric, ScoringDimension

_REASONING_WORDS = (
    "because", "therefore", "however", "thus", "consequently",
    "as a result", "in contrast", "furthermore", "moreover", "although",
)

_CITATION_PATTERNS = (
    r"\[[\w\s,]+\]",          # [Author, 2024] style
    r"https?://",              # URLs
    r"according to",
    r"source:",
    r"\breferences?\s*:",      # "References:" section header
    r"\bcited\b",
)


class AnalysisRubric(EvaluationRubric):
    @property
    def name(self) -> str:
        return "analysis"

    @property
    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("coverage",  0.30, "Addresses multiple aspects / sections"),
            ScoringDimension("reasoning", 0.30, "Logical connectives and conclusions"),
            ScoringDimension("accuracy",  0.25, "Well-structured sentences"),
            ScoringDimension("citations", 0.15, "References or evidence markers"),
        ]

    def _score_dimension(self, dimension: str, output: str, context: dict) -> float:
        if dimension == "coverage":
            return self._score_coverage(output)
        if dimension == "reasoning":
            return self._score_reasoning(output)
        if dimension == "accuracy":
            return self._score_accuracy(output)
        if dimension == "citations":
            return self._score_citations(output)
        return 0.0

    # ------------------------------------------------------------------

    def _score_coverage(self, text: str) -> float:
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
        headings = re.findall(r"^#{1,4}\s+\S", text, re.MULTILINE)
        score = 0.0
        if len(paragraphs) >= 2:
            score += 40.0
        if len(paragraphs) >= 4:
            score += 30.0
        if headings:
            score += 30.0
        return min(100.0, score)

    def _score_reasoning(self, text: str) -> float:
        lower = text.lower()
        found = sum(1 for w in _REASONING_WORDS if w in lower)
        return min(100.0, found * 20.0)

    def _score_accuracy(self, text: str) -> float:
        sentences = re.split(r"[.!?]+", text)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
        if not meaningful:
            return 0.0
        score = 0.0
        if len(meaningful) >= 3:
            score += 50.0
        avg_words = sum(len(s.split()) for s in meaningful) / len(meaningful)
        if 8 <= avg_words <= 30:
            score += 50.0
        elif avg_words > 5:
            score += 25.0
        return min(100.0, score)

    def _score_citations(self, text: str) -> float:
        for pattern in _CITATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return 100.0
        return 0.0
