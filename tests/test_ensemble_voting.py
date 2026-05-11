"""Tests for ensemble voting strategies and VotingSystem (ace_enterprise-h7p)."""
from __future__ import annotations

import pytest

from src.ensemble.models import (
    BulletSection,
    ConsensusBullet,
    ModelPerformance,
    Vote,
    VoteType,
)
from src.ensemble.voting import (
    EscalatingVoting,
    MajorityVoting,
    SupermajorityVoting,
    UnanimousVoting,
    VotingStrategy,
    VotingSystem,
    WeightedVoting,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bullet(content="validate inputs"):
    return ConsensusBullet(
        content=content,
        section=BulletSection.STRATEGIES,
        proposed_by="model-a",
        proposal_reasoning="test",
    )


def _vote(model_id, vote_type, confidence=0.8):
    return Vote(model_id=model_id, vote=vote_type, reasoning="test", confidence=confidence)


def _approved_bullet():
    b = _bullet()
    b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.APPROVE)]
    return b


def _rejected_bullet():
    b = _bullet()
    b.votes = [_vote("m1", VoteType.REJECT), _vote("m2", VoteType.REJECT)]
    return b


def _split_bullet():
    b = _bullet()
    b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]
    return b


# ---------------------------------------------------------------------------
# MajorityVoting
# ---------------------------------------------------------------------------

class TestMajorityVoting:
    def setup_method(self):
        self.strategy = MajorityVoting()

    def test_name(self):
        assert self.strategy.name() == "majority"

    def test_approves_when_over_half_approve(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.APPROVE), _vote("m3", VoteType.REJECT)]
        assert self.strategy.decide(b) is True

    def test_rejects_when_exactly_half(self):
        b = _split_bullet()  # 50% approval — NOT >50%
        assert self.strategy.decide(b) is False

    def test_rejects_when_minority_approve(self):
        assert self.strategy.decide(_rejected_bullet()) is False

    def test_rejects_with_no_votes(self):
        assert self.strategy.decide(_bullet()) is False

    def test_approves_with_all_approve_votes(self):
        assert self.strategy.decide(_approved_bullet()) is True

    def test_abstain_votes_not_counted(self):
        b = _bullet()
        b.votes = [
            _vote("m1", VoteType.APPROVE),
            _vote("m2", VoteType.ABSTAIN),
            _vote("m3", VoteType.REJECT),
        ]
        # 1 approve, 1 reject (abstain excluded) → 50% → reject
        assert self.strategy.decide(b) is False

    def test_is_voting_strategy(self):
        assert isinstance(self.strategy, VotingStrategy)


# ---------------------------------------------------------------------------
# SupermajorityVoting
# ---------------------------------------------------------------------------

class TestSupermajorityVoting:
    def test_name_includes_threshold(self):
        s = SupermajorityVoting(threshold=0.667)
        assert "66" in s.name()

    def test_approves_at_exact_threshold(self):
        s = SupermajorityVoting(threshold=0.5)
        b = _split_bullet()  # 50% approval
        assert s.decide(b) is True

    def test_rejects_below_threshold(self):
        s = SupermajorityVoting(threshold=0.667)
        b = _split_bullet()  # 50% < 66.7%
        assert s.decide(b) is False

    def test_approves_above_threshold(self):
        s = SupermajorityVoting(threshold=0.667)
        b = _bullet()
        b.votes = [
            _vote("m1", VoteType.APPROVE),
            _vote("m2", VoteType.APPROVE),
            _vote("m3", VoteType.APPROVE),
        ]
        assert s.decide(b) is True

    def test_rejects_with_no_votes(self):
        s = SupermajorityVoting()
        assert s.decide(_bullet()) is False

    def test_custom_threshold_stored(self):
        s = SupermajorityVoting(threshold=0.8)
        assert s.threshold == 0.8


# ---------------------------------------------------------------------------
# WeightedVoting
# ---------------------------------------------------------------------------

class TestWeightedVoting:
    def test_name(self):
        assert WeightedVoting().name() == "weighted"

    def test_falls_back_to_majority_when_no_perf_data(self):
        s = WeightedVoting()
        # _approved_bullet has 2 approvals → majority passes → True
        assert s.decide(_approved_bullet(), model_performance=None) is True

    def test_falls_back_to_majority_when_empty_perf_dict(self):
        s = WeightedVoting()
        assert s.decide(_rejected_bullet(), model_performance={}) is False

    def test_high_weight_approver_wins(self):
        s = WeightedVoting(threshold=0.5)
        b = _bullet()
        b.votes = [
            _vote("strong", VoteType.APPROVE),
            _vote("weak", VoteType.REJECT),
        ]
        perf = {
            "strong": ModelPerformance(model_id="strong", voting_weight=3.0),
            "weak": ModelPerformance(model_id="weak", voting_weight=1.0),
        }
        assert s.decide(b, model_performance=perf) is True

    def test_high_weight_rejector_wins(self):
        s = WeightedVoting(threshold=0.5)
        b = _bullet()
        b.votes = [
            _vote("strong", VoteType.REJECT),
            _vote("weak", VoteType.APPROVE),
        ]
        perf = {
            "strong": ModelPerformance(model_id="strong", voting_weight=3.0),
            "weak": ModelPerformance(model_id="weak", voting_weight=1.0),
        }
        assert s.decide(b, model_performance=perf) is False

    def test_unknown_model_gets_default_weight(self):
        s = WeightedVoting(threshold=0.5)
        b = _bullet()
        b.votes = [_vote("unknown", VoteType.APPROVE)]
        # Unknown model gets weight 1.0; one approval → approved
        assert s.decide(b, model_performance={}) is True

    def test_no_votes_returns_false(self):
        s = WeightedVoting()
        assert s.decide(_bullet(), model_performance={}) is False

    def test_abstains_not_counted_in_weight(self):
        s = WeightedVoting(threshold=0.5)
        b = _bullet()
        b.votes = [
            _vote("m1", VoteType.APPROVE),
            _vote("m2", VoteType.ABSTAIN),
        ]
        perf = {
            "m1": ModelPerformance(model_id="m1", voting_weight=1.0),
            "m2": ModelPerformance(model_id="m2", voting_weight=1.0),
        }
        # abstain not counted → only approve → 100% → True
        assert s.decide(b, model_performance=perf) is True


# ---------------------------------------------------------------------------
# UnanimousVoting
# ---------------------------------------------------------------------------

class TestUnanimousVoting:
    def setup_method(self):
        self.strategy = UnanimousVoting()

    def test_name(self):
        assert self.strategy.name() == "unanimous"

    def test_approves_when_all_approve(self):
        assert self.strategy.decide(_approved_bullet()) is True

    def test_rejects_when_any_rejection(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]
        assert self.strategy.decide(b) is False

    def test_rejects_with_no_votes(self):
        assert self.strategy.decide(_bullet()) is False

    def test_abstain_does_not_block_approval(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.ABSTAIN)]
        # One APPROVE, no REJECT → unanimous passes
        assert self.strategy.decide(b) is True

    def test_all_abstain_returns_false(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.ABSTAIN), _vote("m2", VoteType.ABSTAIN)]
        assert self.strategy.decide(b) is False


# ---------------------------------------------------------------------------
# EscalatingVoting
# ---------------------------------------------------------------------------

class TestEscalatingVoting:
    def test_name(self):
        assert EscalatingVoting().name() == "escalating"

    def test_uses_initial_threshold_at_round_zero(self):
        s = EscalatingVoting(initial_threshold=1.0, final_threshold=0.5, max_rounds=3)
        b = _split_bullet()  # 50% approval
        b.deliberation_rounds = 0
        # threshold=1.0 → 50% < 100% → reject
        assert s.decide(b) is False

    def test_uses_final_threshold_at_max_rounds(self):
        s = EscalatingVoting(initial_threshold=1.0, final_threshold=0.4, max_rounds=3)
        b = _split_bullet()  # 50% approval
        b.deliberation_rounds = 3
        # threshold=0.4 → 50% >= 40% → approve
        assert s.decide(b) is True

    def test_interpolates_threshold_midway(self):
        s = EscalatingVoting(initial_threshold=1.0, final_threshold=0.0, max_rounds=2)
        b = _bullet()
        # At round 1 of 2: progress=0.5 → threshold = 1.0 - (1.0-0.0)*0.5 = 0.5
        b.deliberation_rounds = 1
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]
        # 50% approval >= 50% threshold → True
        assert s.decide(b) is True

    def test_no_votes_returns_false(self):
        s = EscalatingVoting()
        assert s.decide(_bullet()) is False

    def test_rounds_beyond_max_uses_final_threshold(self):
        s = EscalatingVoting(initial_threshold=0.9, final_threshold=0.3, max_rounds=2)
        b = _split_bullet()  # 50%
        b.deliberation_rounds = 10  # well past max
        # threshold=0.3 → 50% >= 30% → approve
        assert s.decide(b) is True


# ---------------------------------------------------------------------------
# VotingSystem
# ---------------------------------------------------------------------------

class TestVotingSystem:
    def test_defaults_to_majority_strategy(self):
        vs = VotingSystem()
        assert isinstance(vs.strategy, MajorityVoting)

    def test_accepts_custom_strategy(self):
        vs = VotingSystem(strategy=UnanimousVoting())
        assert isinstance(vs.strategy, UnanimousVoting)

    def test_vote_on_bullets_returns_tuple(self):
        vs = VotingSystem()
        approved, rejected = vs.vote_on_bullets([_approved_bullet()])
        assert isinstance(approved, list)
        assert isinstance(rejected, list)

    def test_approved_bullet_in_approved_list(self):
        vs = VotingSystem()
        approved, rejected = vs.vote_on_bullets([_approved_bullet()])
        assert len(approved) == 1
        assert len(rejected) == 0

    def test_rejected_bullet_in_rejected_list(self):
        vs = VotingSystem()
        approved, rejected = vs.vote_on_bullets([_rejected_bullet()])
        assert len(approved) == 0
        assert len(rejected) == 1

    def test_bullet_with_no_votes_is_rejected(self):
        vs = VotingSystem()
        b = _bullet()
        approved, rejected = vs.vote_on_bullets([b])
        assert len(rejected) == 1
        assert b.approved is False

    def test_approval_strategy_set_on_approved_bullet(self):
        vs = VotingSystem(strategy=MajorityVoting())
        b = _approved_bullet()
        vs.vote_on_bullets([b])
        assert b.approval_strategy == "majority"

    def test_approval_strategy_set_on_rejected_bullet(self):
        vs = VotingSystem(strategy=MajorityVoting())
        b = _rejected_bullet()
        vs.vote_on_bullets([b])
        assert b.approval_strategy == "majority"

    def test_no_votes_strategy_tagged_as_no_votes(self):
        vs = VotingSystem()
        b = _bullet()
        vs.vote_on_bullets([b])
        assert b.approval_strategy == "no_votes"

    def test_approved_flag_true_on_approved(self):
        vs = VotingSystem()
        b = _approved_bullet()
        vs.vote_on_bullets([b])
        assert b.approved is True

    def test_approved_flag_false_on_rejected(self):
        vs = VotingSystem()
        b = _rejected_bullet()
        vs.vote_on_bullets([b])
        assert b.approved is False

    def test_mixed_bullets_split_correctly(self):
        vs = VotingSystem()
        approved, rejected = vs.vote_on_bullets([_approved_bullet(), _rejected_bullet()])
        assert len(approved) == 1
        assert len(rejected) == 1

    def test_empty_list_returns_empty_lists(self):
        vs = VotingSystem()
        approved, rejected = vs.vote_on_bullets([])
        assert approved == []
        assert rejected == []


# ---------------------------------------------------------------------------
# VotingSystem.get_contested_bullets
# ---------------------------------------------------------------------------

class TestGetContestedBullets:
    def test_returns_bullets_in_contested_range(self):
        vs = VotingSystem()
        b = _split_bullet()  # 50% approval — in [40%, 60%]
        result = vs.get_contested_bullets([b])
        assert b in result

    def test_excludes_unanimous_approval(self):
        vs = VotingSystem()
        b = _approved_bullet()  # 100% approval
        result = vs.get_contested_bullets([b])
        assert b not in result

    def test_excludes_unanimous_rejection(self):
        vs = VotingSystem()
        b = _rejected_bullet()  # 0% approval
        result = vs.get_contested_bullets([b])
        assert b not in result

    def test_empty_list_returns_empty(self):
        vs = VotingSystem()
        assert vs.get_contested_bullets([]) == []

    def test_custom_range_filters_correctly(self):
        vs = VotingSystem()
        b = _split_bullet()  # 50%
        # narrow range that excludes 50%
        result = vs.get_contested_bullets([b], min_approval=0.6, max_approval=0.9)
        assert b not in result


# ---------------------------------------------------------------------------
# VotingSystem.analyze_disagreement
# ---------------------------------------------------------------------------

class TestAnalyzeDisagreement:
    def test_empty_list_returns_empty_dict(self):
        vs = VotingSystem()
        assert vs.analyze_disagreement([]) == {}

    def test_returns_total_bullets_count(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_approved_bullet(), _rejected_bullet()])
        assert result["total_bullets"] == 2

    def test_unanimous_counted_for_full_approval(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_approved_bullet()])
        assert result["unanimous"] == 1

    def test_unanimous_counted_for_full_rejection(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_rejected_bullet()])
        assert result["unanimous"] == 1

    def test_highly_contested_counted_for_split(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_split_bullet()])
        assert result["highly_contested"] == 1

    def test_avg_approval_rate_computed(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_approved_bullet(), _rejected_bullet()])
        assert result["avg_approval_rate"] == pytest.approx(0.5)

    def test_min_and_max_approval_rate(self):
        vs = VotingSystem()
        result = vs.analyze_disagreement([_approved_bullet(), _rejected_bullet()])
        assert result["min_approval_rate"] == pytest.approx(0.0)
        assert result["max_approval_rate"] == pytest.approx(1.0)
