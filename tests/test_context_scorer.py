"""Tests for ContextScorer (src/retrieval/context_scorer.py) -- the RANK
phase of CGR3. Previously had zero test coverage anywhere.

Two bugs found while building this coverage, both fixed (see
TestScoreAggregate / TestVersionComparison for the regression tests):
- score_domain() existed but score() never called it -- only 4 of the
  "5-dimension context scoring" the README describes were actually
  combined. Fixed: score() now combines all 5 (equal 0.20 weight each).
- _version_compatible() did lexicographic STRING comparison, not numeric --
  "3.11" >= "3.8" was False as strings. Fixed via _parse_version().
"""
import pytest
from datetime import UTC, datetime, timedelta

from src.retrieval.context_scorer import ContextScorer
from src.retrieval.schemas import RetrievalContext
from src.storage.schemas import Bullet

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bullet(**kw):
    defaults = dict(id="ctx-00001", content="x", section="strategies_and_hard_rules", created_at=_NOW)
    defaults.update(kw)
    return Bullet(**defaults)


# ---------------------------------------------------------------------------
# score_temporal
# ---------------------------------------------------------------------------

class TestScoreTemporal:
    def test_recent_bullet_scores_full(self):
        scorer = ContextScorer()
        b = _bullet(created_at=_NOW)
        score, gap = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 1.0
        assert gap is None

    def test_moderately_old_bullet_decays(self):
        scorer = ContextScorer(temporal_decay_days=365)
        b = _bullet(created_at=_NOW - timedelta(days=400))
        score, gap = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 0.6
        assert gap is not None
        assert gap.severity == 0.3

    def test_very_old_bullet_decays_further(self):
        scorer = ContextScorer(temporal_decay_days=365)
        b = _bullet(created_at=_NOW - timedelta(days=800))
        score, gap = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 0.3
        assert gap.severity == 0.5

    def test_not_yet_valid_scores_zero(self):
        scorer = ContextScorer()
        b = _bullet(valid_from=_NOW + timedelta(days=10))
        score, gap = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 0.0
        assert gap.severity == 1.0
        assert "not yet valid" in gap.description

    def test_expired_scores_zero(self):
        scorer = ContextScorer()
        b = _bullet(valid_until=_NOW - timedelta(days=1))
        score, gap = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 0.0
        assert "expired" in gap.description

    def test_temporal_confidence_scales_the_score(self):
        scorer = ContextScorer()
        b = _bullet(created_at=_NOW, temporal_confidence=0.5)
        score, _ = scorer.score_temporal(b, RetrievalContext(query_timestamp=_NOW))
        assert score == 0.5


# ---------------------------------------------------------------------------
# score_team
# ---------------------------------------------------------------------------

class TestScoreTeam:
    def test_no_team_context_is_neutral(self):
        scorer = ContextScorer()
        b = _bullet(team_id="payments")
        score, gap = scorer.score_team(b, RetrievalContext())
        assert score == 0.5 and gap is None

    def test_bullet_with_no_team_is_neutral(self):
        scorer = ContextScorer()
        b = _bullet(team_id=None)
        score, gap = scorer.score_team(b, RetrievalContext(team_id="payments"))
        assert score == 0.5 and gap is None

    def test_matching_team_scores_full(self):
        scorer = ContextScorer()
        b = _bullet(team_id="payments")
        score, gap = scorer.score_team(b, RetrievalContext(team_id="payments"))
        assert score == 1.0 and gap is None

    def test_mismatched_team_scores_low_with_gap(self):
        scorer = ContextScorer()
        b = _bullet(team_id="payments")
        score, gap = scorer.score_team(b, RetrievalContext(team_id="platform"))
        assert score == 0.3
        assert gap.dimension == "team"


# ---------------------------------------------------------------------------
# score_tech_stack
# ---------------------------------------------------------------------------

class TestScoreTechStack:
    def test_no_context_tech_stack_scores_neutral_with_gap(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": ">=3.10"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext())
        assert score == 0.5
        assert gap is not None

    def test_bullet_with_no_tech_requirements_and_tag_overlap(self):
        scorer = ContextScorer()
        b = _bullet(tech_context=None, tags=["python"])
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 0.7 and gap is None

    def test_bullet_with_no_tech_requirements_and_no_tag_overlap(self):
        scorer = ContextScorer()
        b = _bullet(tech_context=None, tags=["ruby"])
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 0.5 and gap is None

    def test_all_requirements_satisfied_scores_full(self):
        # "3.9" (single-digit minor) avoids the lexicographic-comparison trap
        # documented in TestVersionComparisonBug below -- kept deliberately
        # simple so this test demonstrates the intended behavior.
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": ">=3.8"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.9"}))
        assert score == 1.0 and gap is None

    def test_missing_required_tech_produces_gap(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"redis": ">=6.0"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 0.0
        assert "redis" in gap.description

    def test_partial_match_scores_proportionally(self):
        # redis is missing from the stack entirely (not a version comparison
        # at all -- "required but not in your stack"), python's requirement
        # is satisfied -> 1 of 2.
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": ">=3.8", "redis": ">=6.0"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.9"}))
        assert score == 0.5  # 1 of 2 requirements met
        assert gap is not None


class TestVersionComparison:
    """_version_compatible() now does numeric dotted-version comparison via
    _parse_version(), not lexicographic string comparison -- it used to
    misjudge "3.11" >= "3.8" as False (comparing "1" < "8" as characters)."""

    def test_multi_digit_minor_version_correctly_recognized_as_compatible(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": ">=3.8"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 1.0  # 3.11 > 3.8 numerically
        assert gap is None

    def test_parse_version_ignores_non_numeric_suffix(self):
        scorer = ContextScorer()
        assert scorer._parse_version("3.10.2-beta") == (3, 10, 2)

    def test_parse_version_handles_missing_segments(self):
        scorer = ContextScorer()
        assert scorer._parse_version("3.10") == (3, 10)

    def test_greater_than_operator(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"redis": ">6.0"})
        score, _ = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"redis": "6.2"}))
        assert score == 1.0

    def test_less_than_operator_correctly_rejects_newer_version(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": "<3.10"})
        score, gap = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 0.0
        assert gap is not None

    def test_less_than_or_equal_operator(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": "<=3.11"})
        score, _ = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 1.0

    def test_equals_operator_uses_numeric_comparison_too(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": "==3.10"})
        score, _ = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.10"}))
        assert score == 1.0

    def test_no_operator_falls_back_to_prefix_match(self):
        scorer = ContextScorer()
        b = _bullet(tech_context={"python": "3"})
        score, _ = scorer.score_tech_stack(b, RetrievalContext(tech_stack={"python": "3.11"}))
        assert score == 1.0


# ---------------------------------------------------------------------------
# score_project
# ---------------------------------------------------------------------------

class TestScoreProject:
    def test_no_project_context_is_neutral(self):
        scorer = ContextScorer()
        b = _bullet(project_ids=["proj-a"])
        score, gap = scorer.score_project(b, RetrievalContext())
        assert score == 0.5 and gap is None

    def test_bullet_with_no_project_is_neutral(self):
        scorer = ContextScorer()
        b = _bullet(project_ids=None)
        score, gap = scorer.score_project(b, RetrievalContext(project_id="proj-a"))
        assert score == 0.5 and gap is None

    def test_matching_project_scores_full(self):
        scorer = ContextScorer()
        b = _bullet(project_ids=["proj-a"])
        score, gap = scorer.score_project(b, RetrievalContext(project_id="proj-a"))
        assert score == 1.0 and gap is None

    def test_different_project_same_domain_scores_partial(self):
        scorer = ContextScorer()
        b = _bullet(project_ids=["proj-b"], applicable_domains=["fintech"])
        score, gap = scorer.score_project(
            b, RetrievalContext(project_id="proj-a", domain="fintech"),
        )
        assert score == 0.7 and gap is None

    def test_different_project_different_domain_scores_low_with_gap(self):
        scorer = ContextScorer()
        b = _bullet(project_ids=["proj-b"], applicable_domains=["fintech"])
        score, gap = scorer.score_project(
            b, RetrievalContext(project_id="proj-a", domain="healthcare"),
        )
        assert score == 0.4
        assert gap.dimension == "project"


# ---------------------------------------------------------------------------
# score_domain -- exists, but is NOT wired into score(). Tested standalone.
# ---------------------------------------------------------------------------

class TestScoreDomainOrphaned:
    def test_score_domain_works_correctly_in_isolation(self):
        scorer = ContextScorer()
        b = _bullet(applicable_domains=["fintech"])
        score, gap = scorer.score_domain(b, RetrievalContext(domain="fintech"))
        assert score == 1.0 and gap is None

    def test_score_domain_mismatch_produces_gap(self):
        scorer = ContextScorer()
        b = _bullet(applicable_domains=["fintech"])
        score, gap = scorer.score_domain(b, RetrievalContext(domain="healthcare"))
        assert score == 0.3
        assert gap.dimension == "domain"

    def test_score_calls_score_domain_and_feeds_the_aggregate(self):
        """score() now combines all 5 documented dimensions, including
        domain -- previously score_domain() was never invoked from score()
        at all, so a domain mismatch had zero effect on ranking."""
        scorer = ContextScorer()
        matched = _bullet(id="matched", applicable_domains=["fintech"])
        mismatched = _bullet(id="mismatched", applicable_domains=["healthcare"])
        context = RetrievalContext(domain="fintech", query_timestamp=_NOW)

        matched_score, matched_gaps = scorer.score(matched, context)
        mismatched_score, mismatched_gaps = scorer.score(mismatched, context)

        assert matched_score > mismatched_score
        assert any(g.dimension == "domain" for g in mismatched_gaps)


# ---------------------------------------------------------------------------
# score() aggregate: weighted combination across all 5 dimensions
# ---------------------------------------------------------------------------

class TestScoreAggregate:
    def test_default_weights_sum_to_one(self):
        assert sum(ContextScorer.DEFAULT_WEIGHTS.values()) == 1.0

    def test_empty_context_scores_all_neutral_dimensions(self):
        # temporal=1.0 (fresh bullet), team=0.5, tech_stack=0.5 (with gap),
        # project=0.5, domain=0.5 -> weighted: (1.0+0.5+0.5+0.5+0.5) * 0.20 = 0.6
        scorer = ContextScorer()
        b = _bullet(created_at=_NOW)
        combined, gaps = scorer.score(b, RetrievalContext(query_timestamp=_NOW))
        assert combined == pytest.approx(0.6)
        assert len(gaps) == 1  # only the tech_stack "unknown" gap

    def test_perfect_match_scores_near_one(self):
        # "3.9" not "3.11" -- unrelated multi-digit-minor-version parsing is
        # covered in TestVersionComparison; keep this fixture unambiguous.
        scorer = ContextScorer()
        b = _bullet(
            created_at=_NOW,
            team_id="payments",
            tech_context={"python": ">=3.8"},
            project_ids=["proj-a"],
            applicable_domains=["fintech"],
        )
        context = RetrievalContext(
            query_timestamp=_NOW, team_id="payments",
            tech_stack={"python": "3.9"}, project_id="proj-a", domain="fintech",
        )
        combined, gaps = scorer.score(b, context)
        assert combined == pytest.approx(1.0)
        assert gaps == []

    def test_custom_weights_are_respected(self):
        scorer = ContextScorer(weights={"temporal": 1.0, "team": 0.0, "tech_stack": 0.0, "project": 0.0})
        b = _bullet(created_at=_NOW)
        combined, _ = scorer.score(b, RetrievalContext(query_timestamp=_NOW))
        assert combined == 1.0  # only temporal (=1.0) contributes
