"""DocumentationRubric — evaluates Markdown documentation output.

Dimensions (weights sum to 1.0):
  completeness  0.30  has headings and substantive paragraphs
  clarity       0.25  reasonable line lengths; not excessively terse
  examples      0.25  contains fenced code blocks
  formatting    0.20  markdown headings and bullet lists present

Bead: ace_enterprise-nf7
"""

from __future__ import annotations

import re

from src.benchmark.rubrics.base import EvaluationRubric, ScoringDimension


class DocumentationRubric(EvaluationRubric):
    @property
    def name(self) -> str:
        return "documentation"

    @property
    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("completeness", 0.30, "Has headings and substantive paragraphs"),
            ScoringDimension("clarity",      0.25, "Reasonable line lengths; not excessively terse"),
            ScoringDimension("examples",     0.25, "Contains fenced code blocks"),
            ScoringDimension("formatting",   0.20, "Markdown headings and bullet lists present"),
        ]

    def _score_dimension(self, dimension: str, output: str, context: dict) -> float:
        if dimension == "completeness":
            return self._score_completeness(output)
        if dimension == "clarity":
            return self._score_clarity(output)
        if dimension == "examples":
            return self._score_examples(output)
        if dimension == "formatting":
            return self._score_formatting(output)
        return 0.0

    # ------------------------------------------------------------------

    def _score_completeness(self, text: str) -> float:
        score = 0.0
        if re.search(r"^#{1,3}\s+\S", text, re.MULTILINE):
            score += 50.0
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 2:
            score += 30.0
        if len(text.split()) >= 30:
            score += 20.0
        return score

    def _score_clarity(self, text: str) -> float:
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return 0.0
        avg_len = sum(len(l) for l in lines) / len(lines)
        # Sweet spot 40-100 chars per line → 100 pts; very short or very long → lower
        if 40 <= avg_len <= 100:
            return 100.0
        if avg_len < 10:
            return 20.0
        if avg_len < 40:
            return 40.0 + (avg_len - 10) / 30 * 60
        # avg_len > 100
        return max(0.0, 100.0 - (avg_len - 100) * 0.5)

    def _score_examples(self, text: str) -> float:
        blocks = re.findall(r"```[\s\S]*?```", text)
        if not blocks:
            return 0.0
        return min(100.0, 50.0 + len(blocks) * 25.0)

    def _score_formatting(self, text: str) -> float:
        score = 0.0
        if re.search(r"^#{1,3}\s+", text, re.MULTILINE):
            score += 50.0
        if re.search(r"^[-*]\s+", text, re.MULTILINE):
            score += 50.0
        return score
