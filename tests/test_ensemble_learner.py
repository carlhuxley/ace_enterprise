"""Tests for EnsembleLearner (ace_enterprise-e4q).

LLM-calling methods (_execute_single_model, _conduct_cross_voting,
_conduct_deliberation) are patched throughout. Tests cover construction,
pure-logic helpers, and orchestration flow.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.ensemble.learner import EnsembleLearner
from src.ensemble.models import (
    BulletSection,
    ConsensusBullet,
    EnsembleResult,
    ModelPerformance,
    Vote,
    VoteResults,
    VoteType,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MODELS = [("togetherai", "Qwen/Qwen2.5-72B"), ("ollama", "llama3")]


def _make_learner(tmp_path, models=None, **kwargs):
    """Return an EnsembleLearner with a file-isolated PlaybookManager."""
    if models is None:
        models = _MODELS
    with patch("src.ensemble.learner.PlaybookManager") as MockPM:
        MockPM.return_value = MagicMock()
        learner = EnsembleLearner(
            models=models,
            playbook_id="test-pb",
            **kwargs,
        )
    return learner


def _bullet(content="validate inputs", proposed_by="togetherai/Qwen", approved=None):
    return ConsensusBullet(
        content=content,
        section=BulletSection.STRATEGIES,
        proposed_by=proposed_by,
        proposal_reasoning="test",
        approved=approved,
    )


def _vote(model_id, vote_type, confidence=0.8):
    return Vote(model_id=model_id, vote=vote_type, reasoning="test", confidence=confidence)


def _minimal_vote_results():
    return VoteResults(total_bullets=0, approved=0, rejected=0, pending=0)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestEnsembleLearnerInit:
    def test_model_performance_keys_match_model_ids(self, tmp_path):
        learner = _make_learner(tmp_path)
        assert "togetherai/Qwen/Qwen2.5-72B" in learner.model_performance
        assert "ollama/llama3" in learner.model_performance

    def test_all_models_get_performance_entry(self, tmp_path):
        learner = _make_learner(tmp_path)
        assert len(learner.model_performance) == len(_MODELS)

    def test_initial_performance_scores_are_zero(self, tmp_path):
        learner = _make_learner(tmp_path)
        for perf in learner.model_performance.values():
            assert perf.proposals_made == 0
            assert perf.accuracy_score == 0.0

    def test_three_tuple_model_tracked_correctly(self, tmp_path):
        models = [("vllm", "deepseek", "http://localhost:8000")]
        learner = _make_learner(tmp_path, models=models)
        assert "vllm/deepseek" in learner.model_performance

    def test_deliberation_settings_stored(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        assert learner.enable_deliberation is False

    def test_similarity_threshold_stored(self, tmp_path):
        learner = _make_learner(tmp_path, similarity_threshold=0.9)
        assert learner.consensus_builder.similarity_threshold == 0.9


# ---------------------------------------------------------------------------
# _parse_vote_response
# ---------------------------------------------------------------------------

class TestParseVoteResponse:
    def setup_method(self):
        self.learner = _make_learner(None)

    def test_parses_approve(self):
        response = "VOTE: APPROVE\nCONFIDENCE: 0.9\nREASONING: Looks good."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.vote == VoteType.APPROVE

    def test_parses_reject(self):
        response = "VOTE: REJECT\nCONFIDENCE: 0.8\nREASONING: Too vague."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.vote == VoteType.REJECT

    def test_parses_abstain(self):
        response = "VOTE: ABSTAIN\nCONFIDENCE: 0.5\nREASONING: Not enough context."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.vote == VoteType.ABSTAIN

    def test_parses_confidence(self):
        response = "VOTE: APPROVE\nCONFIDENCE: 0.75\nREASONING: Good."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.confidence == pytest.approx(0.75)

    def test_clamps_confidence_to_one(self):
        response = "VOTE: APPROVE\nCONFIDENCE: 1.5\nREASONING: Great."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.confidence <= 1.0

    def test_clamps_confidence_to_zero(self):
        response = "VOTE: REJECT\nCONFIDENCE: -0.3\nREASONING: Bad."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.confidence >= 0.0

    def test_defaults_to_approve_when_vote_missing(self):
        response = "The bullet looks reasonable to me."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.vote == VoteType.APPROVE

    def test_model_id_set_on_vote(self):
        response = "VOTE: APPROVE\nCONFIDENCE: 0.8\nREASONING: Fine."
        vote = self.learner._parse_vote_response(response, "my-model")
        assert vote.model_id == "my-model"

    def test_parses_reasoning(self):
        response = "VOTE: APPROVE\nCONFIDENCE: 0.8\nREASONING: This is helpful."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert "helpful" in vote.reasoning

    def test_case_insensitive_vote_parsing(self):
        response = "vote: approve\nconfidence: 0.9\nreasoning: Fine."
        vote = self.learner._parse_vote_response(response, "model-a")
        assert vote.vote == VoteType.APPROVE


# ---------------------------------------------------------------------------
# _fallback_heuristic_vote
# ---------------------------------------------------------------------------

class TestFallbackHeuristicVote:
    def setup_method(self):
        self.learner = _make_learner(None)

    def test_proposer_gets_approve(self):
        bullet = _bullet(proposed_by="model-a")
        vote = self.learner._fallback_heuristic_vote(bullet, "model-a")
        assert vote.vote == VoteType.APPROVE

    def test_proposer_gets_high_confidence(self):
        bullet = _bullet(proposed_by="model-a")
        vote = self.learner._fallback_heuristic_vote(bullet, "model-a")
        assert vote.confidence >= 0.8

    def test_non_proposer_gets_approve(self):
        bullet = _bullet(proposed_by="model-a")
        vote = self.learner._fallback_heuristic_vote(bullet, "model-b")
        assert vote.vote == VoteType.APPROVE

    def test_non_proposer_gets_lower_confidence_than_proposer(self):
        bullet = _bullet(proposed_by="model-a")
        proposer_vote = self.learner._fallback_heuristic_vote(bullet, "model-a")
        other_vote = self.learner._fallback_heuristic_vote(bullet, "model-b")
        assert other_vote.confidence < proposer_vote.confidence

    def test_consensus_prefix_treated_as_proposer(self):
        bullet = _bullet(proposed_by="consensus-xyz")
        vote = self.learner._fallback_heuristic_vote(bullet, "consensus-xyz")
        assert vote.confidence >= 0.8


# ---------------------------------------------------------------------------
# _calculate_vote_results
# ---------------------------------------------------------------------------

class TestCalculateVoteResults:
    def setup_method(self):
        self.learner = _make_learner(None)

    def test_counts_approved(self):
        bullets = [_bullet(approved=True), _bullet(approved=True), _bullet(approved=False)]
        results = self.learner._calculate_vote_results(bullets)
        assert results.approved == 2

    def test_counts_rejected(self):
        bullets = [_bullet(approved=False), _bullet(approved=False)]
        results = self.learner._calculate_vote_results(bullets)
        assert results.rejected == 2

    def test_counts_pending(self):
        bullets = [_bullet(approved=None), _bullet(approved=True)]
        results = self.learner._calculate_vote_results(bullets)
        assert results.pending == 1

    def test_total_matches_input(self):
        bullets = [_bullet(approved=True), _bullet(approved=False), _bullet(approved=None)]
        results = self.learner._calculate_vote_results(bullets)
        assert results.total_bullets == 3

    def test_empty_bullets_returns_zeros(self):
        results = self.learner._calculate_vote_results([])
        assert results.total_bullets == 0
        assert results.approved == 0

    def test_highly_contested_counted_when_split_vote(self):
        bullet = _bullet()
        bullet.votes = [
            _vote("m1", VoteType.APPROVE, 0.7),
            _vote("m2", VoteType.REJECT, 0.7),
        ]
        # approval_rate == 0.5, which is in [0.4, 0.6]
        results = self.learner._calculate_vote_results([bullet])
        assert results.highly_contested == 1

    def test_unanimous_counted_when_all_approve(self):
        bullet = _bullet()
        bullet.votes = [
            _vote("m1", VoteType.APPROVE, 0.9),
            _vote("m2", VoteType.APPROVE, 0.9),
        ]
        results = self.learner._calculate_vote_results([bullet])
        assert results.unanimous_decisions == 1


# ---------------------------------------------------------------------------
# _update_model_performance
# ---------------------------------------------------------------------------

class TestUpdateModelPerformance:
    def setup_method(self):
        self.learner = _make_learner(None)

    def test_approved_bullet_increments_proposer_approved(self):
        mid = "togetherai/Qwen/Qwen2.5-72B"
        bullet = _bullet(proposed_by=mid, approved=True)
        self.learner._update_model_performance([bullet])
        assert self.learner.model_performance[mid].proposals_approved == 1

    def test_rejected_bullet_increments_proposer_rejected(self):
        mid = "togetherai/Qwen/Qwen2.5-72B"
        bullet = _bullet(proposed_by=mid, approved=False)
        self.learner._update_model_performance([bullet])
        assert self.learner.model_performance[mid].proposals_rejected == 1

    def test_pending_bullet_ignored(self):
        mid = "togetherai/Qwen/Qwen2.5-72B"
        bullet = _bullet(proposed_by=mid, approved=None)
        self.learner._update_model_performance([bullet])
        assert self.learner.model_performance[mid].proposals_approved == 0
        assert self.learner.model_performance[mid].proposals_rejected == 0

    def test_vote_agreement_tracked(self):
        mid = "ollama/llama3"
        bullet = _bullet(approved=True)
        bullet.votes = [_vote(mid, VoteType.APPROVE, 0.9)]
        self.learner._update_model_performance([bullet])
        assert self.learner.model_performance[mid].votes_with_majority == 1

    def test_vote_disagreement_not_counted_as_majority(self):
        mid = "ollama/llama3"
        bullet = _bullet(approved=True)
        bullet.votes = [_vote(mid, VoteType.REJECT, 0.9)]
        before = self.learner.model_performance[mid].votes_with_majority
        self.learner._update_model_performance([bullet])
        assert self.learner.model_performance[mid].votes_with_majority == before


# ---------------------------------------------------------------------------
# _get_license_type
# ---------------------------------------------------------------------------

class TestGetLicenseType:
    def setup_method(self):
        self.learner = _make_learner(None)

    def test_openai_returns_proprietary(self):
        assert self.learner._get_license_type("openai", "gpt-4o") == "proprietary"

    def test_anthropic_returns_proprietary(self):
        assert self.learner._get_license_type("anthropic", "claude-3") == "proprietary"

    def test_ollama_qwen_returns_apache(self):
        assert self.learner._get_license_type("ollama", "qwen2.5") == "apache-2.0"

    def test_ollama_mistral_returns_apache(self):
        assert self.learner._get_license_type("ollama", "mistral-7b") == "apache-2.0"

    def test_ollama_llama_returns_llama_license(self):
        result = self.learner._get_license_type("ollama", "llama3")
        assert "llama" in result.lower()

    def test_deepseek_provider_returns_mit(self):
        assert self.learner._get_license_type("deepseek", "deepseek-v2") == "mit"

    def test_ollama_deepseek_base_returns_mit(self):
        assert self.learner._get_license_type("ollama", "deepseek-v2") == "mit"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            self.learner._get_license_type("mystery-cloud", "model-x")


# ---------------------------------------------------------------------------
# add_approved_bullets_to_playbook
# ---------------------------------------------------------------------------

class TestAddApprovedBulletsToPlaybook:
    def _make_result(self, bullets):
        now = datetime.now()
        return EnsembleResult(
            task_description="test",
            models_used=["ollama/llama3"],
            voting_strategy="majority",
            bullets=bullets,
            vote_results=_minimal_vote_results(),
            model_performance={},
            started_at=now,
            completed_at=now,
        )

    def test_approved_bullets_added_returns_count(self, tmp_path):
        with patch("src.ensemble.learner.PlaybookManager") as MockPM:
            mock_pm = MagicMock()
            MockPM.return_value = mock_pm
            learner = EnsembleLearner(
                models=[("ollama", "llama3")],
                playbook_id="pb1",
            )
            learner.playbook_manager = mock_pm

        bullet = _bullet(proposed_by="ollama/llama3", approved=True)
        result = self._make_result([bullet])
        count = learner.add_approved_bullets_to_playbook(result)
        assert count == 1

    def test_rejected_bullets_not_added(self, tmp_path):
        with patch("src.ensemble.learner.PlaybookManager") as MockPM:
            mock_pm = MagicMock()
            MockPM.return_value = mock_pm
            learner = EnsembleLearner(
                models=[("ollama", "llama3")],
                playbook_id="pb1",
            )
            learner.playbook_manager = mock_pm

        bullet = _bullet(proposed_by="ollama/llama3", approved=False)
        result = self._make_result([bullet])
        count = learner.add_approved_bullets_to_playbook(result)
        assert count == 0
        mock_pm.add_bullet.assert_not_called()

    def test_unknown_provider_bullet_skipped(self, tmp_path):
        with patch("src.ensemble.learner.PlaybookManager") as MockPM:
            mock_pm = MagicMock()
            MockPM.return_value = mock_pm
            learner = EnsembleLearner(
                models=[("mystery", "model")],
                playbook_id="pb1",
            )
            learner.playbook_manager = mock_pm

        bullet = _bullet(proposed_by="mystery/model", approved=True)
        result = self._make_result([bullet])
        count = learner.add_approved_bullets_to_playbook(result)
        assert count == 0

    def test_playbook_manager_called_for_each_approved_bullet(self, tmp_path):
        with patch("src.ensemble.learner.PlaybookManager") as MockPM:
            mock_pm = MagicMock()
            MockPM.return_value = mock_pm
            learner = EnsembleLearner(
                models=[("ollama", "llama3")],
                playbook_id="pb1",
            )
            learner.playbook_manager = mock_pm

        bullets = [
            _bullet(content="rule one", proposed_by="ollama/llama3", approved=True),
            _bullet(content="rule two", proposed_by="ollama/llama3", approved=True),
        ]
        result = self._make_result(bullets)
        learner.add_approved_bullets_to_playbook(result)
        assert mock_pm.add_bullet.call_count == 2


# ---------------------------------------------------------------------------
# learn_from_task — orchestration (LLM calls patched out)
# ---------------------------------------------------------------------------

class TestLearnFromTask:
    def _make_canned_proposals(self):
        b = _bullet(proposed_by="togetherai/Qwen/Qwen2.5-72B")
        return {"togetherai/Qwen/Qwen2.5-72B": [b], "ollama/llama3": []}

    def test_returns_ensemble_result(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        canned = self._make_canned_proposals()

        with patch.object(learner, "_execute_models", return_value=canned), \
             patch.object(learner, "_conduct_cross_voting"):
            from src.storage.schemas import TaskInput, EnvironmentFeedback
            task = TaskInput(id="t1", query="test task", context={})
            env = EnvironmentFeedback(result="SUCCESS")
            result = learner.learn_from_task(task, env, parallel=False)

        assert isinstance(result, EnsembleResult)

    def test_models_used_matches_config(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        canned = self._make_canned_proposals()

        with patch.object(learner, "_execute_models", return_value=canned), \
             patch.object(learner, "_conduct_cross_voting"):
            from src.storage.schemas import TaskInput, EnvironmentFeedback
            task = TaskInput(id="t1", query="test task", context={})
            env = EnvironmentFeedback(result="SUCCESS")
            result = learner.learn_from_task(task, env, parallel=False)

        expected_ids = {f"{m[0]}/{m[1]}" for m in _MODELS}
        assert set(result.models_used) == expected_ids

    def test_model_performance_populated_in_result(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        canned = self._make_canned_proposals()

        with patch.object(learner, "_execute_models", return_value=canned), \
             patch.object(learner, "_conduct_cross_voting"):
            from src.storage.schemas import TaskInput, EnvironmentFeedback
            task = TaskInput(id="t1", query="test task", context={})
            env = EnvironmentFeedback(result="SUCCESS")
            result = learner.learn_from_task(task, env, parallel=False)

        assert len(result.model_performance) == len(_MODELS)

    def test_vote_results_in_result(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        canned = self._make_canned_proposals()

        with patch.object(learner, "_execute_models", return_value=canned), \
             patch.object(learner, "_conduct_cross_voting"):
            from src.storage.schemas import TaskInput, EnvironmentFeedback
            task = TaskInput(id="t1", query="test task", context={})
            env = EnvironmentFeedback(result="SUCCESS")
            result = learner.learn_from_task(task, env, parallel=False)

        assert isinstance(result.vote_results, VoteResults)

    def test_execute_models_called_with_parallel_flag(self, tmp_path):
        learner = _make_learner(tmp_path, enable_deliberation=False)
        canned = self._make_canned_proposals()

        with patch.object(learner, "_execute_models", return_value=canned) as mock_exec, \
             patch.object(learner, "_conduct_cross_voting"):
            from src.storage.schemas import TaskInput, EnvironmentFeedback
            task = TaskInput(id="t1", query="test task", context={})
            env = EnvironmentFeedback(result="SUCCESS")
            learner.learn_from_task(task, env, parallel=True)

        _, _, parallel_arg = mock_exec.call_args[0]
        assert parallel_arg is True
