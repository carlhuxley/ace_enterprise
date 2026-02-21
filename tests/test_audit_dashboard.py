"""Tests for Audit Analysis Dashboard - insights for humans.

The dashboard reveals what the broker cannot see:
- Agent identities
- Costs (from external tracker)
- Performance patterns
- Winning combinations
"""
import pytest


class TestAgentPerformanceReport:
    """Tests for agent performance analysis."""

    def test_get_agent_success_rates(self):
        """Should calculate success rate per agent."""
        from src.audit.dashboard import AuditDashboard

        # Create dashboard with mock audit data
        audit_events = [
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": False}},
            {"actor_id": "agent-002", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
        ]

        dashboard = AuditDashboard(audit_events)
        performance = dashboard.get_agent_performance()

        assert "agent-001" in performance
        assert performance["agent-001"].success_rate == pytest.approx(2/3, 0.01)
        assert performance["agent-001"].total_tasks == 3

    def test_performance_includes_task_count(self):
        """Should include total task count per agent."""
        from src.audit.dashboard import AuditDashboard

        audit_events = [
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
        ]

        dashboard = AuditDashboard(audit_events)
        performance = dashboard.get_agent_performance()

        assert performance["agent-001"].total_tasks == 2


class TestCostAnalysis:
    """Tests for cost analysis from external tracker data."""

    def test_inject_cost_data(self):
        """Should accept cost data from external tracker."""
        from src.audit.dashboard import AuditDashboard

        dashboard = AuditDashboard([])

        # Cost data from external billing/tracker
        cost_data = {
            "agent-001": {"total_cost": 15.50, "tasks": 100},
            "agent-002": {"total_cost": 2.30, "tasks": 200},
        }

        dashboard.inject_cost_data(cost_data)

        costs = dashboard.get_cost_analysis()
        assert costs["agent-001"]["cost_per_task"] == pytest.approx(0.155)
        assert costs["agent-002"]["cost_per_task"] == pytest.approx(0.0115)

    def test_cost_ranking(self):
        """Should rank agents by cost efficiency."""
        from src.audit.dashboard import AuditDashboard

        dashboard = AuditDashboard([])
        dashboard.inject_cost_data({
            "agent-001": {"total_cost": 10.0, "tasks": 100},  # 0.10 per task
            "agent-002": {"total_cost": 1.0, "tasks": 100},   # 0.01 per task
            "agent-003": {"total_cost": 5.0, "tasks": 100},   # 0.05 per task
        })

        ranking = dashboard.get_cost_ranking()

        # Cheapest first
        assert ranking[0] == "agent-002"
        assert ranking[1] == "agent-003"
        assert ranking[2] == "agent-001"


class TestIdentityMapping:
    """Tests for mapping opaque agent_ref to actual identity."""

    def test_register_identity(self):
        """Should map agent_ref to identity (model name, provider)."""
        from src.audit.dashboard import AuditDashboard, AgentIdentity

        dashboard = AuditDashboard([])

        dashboard.register_identity("agent-001", AgentIdentity(
            display_name="Claude Opus",
            model_id="claude-opus-4-5-20251101",
            provider="Anthropic"
        ))

        identity = dashboard.get_identity("agent-001")
        assert identity.display_name == "Claude Opus"
        assert identity.provider == "Anthropic"

    def test_reveal_identities_in_report(self):
        """Should reveal identities in human-readable report."""
        from src.audit.dashboard import AuditDashboard, AgentIdentity

        audit_events = [
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED", "payload": {"success": True}},
        ]

        dashboard = AuditDashboard(audit_events)
        dashboard.register_identity("agent-001", AgentIdentity(
            display_name="Qwen 2.5 7B",
            model_id="Qwen/Qwen2.5-Coder-7B",
            provider="effGen"
        ))

        report = dashboard.get_full_report()

        assert "agent-001" in report
        assert report["agent-001"]["identity"]["display_name"] == "Qwen 2.5 7B"


class TestWinningCombinations:
    """Tests for discovering winning agent combinations."""

    def test_detect_task_type_strengths(self):
        """Should identify which agents excel at which task types."""
        from src.audit.dashboard import AuditDashboard

        audit_events = [
            # agent-001 good at python
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "python"}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "python"}},
            # agent-001 bad at rust
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": False, "task_type": "rust"}},
            # agent-002 good at rust
            {"actor_id": "agent-002", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "rust"}},
        ]

        dashboard = AuditDashboard(audit_events)
        strengths = dashboard.get_task_type_strengths()

        assert strengths["python"]["best_agent"] == "agent-001"
        assert strengths["rust"]["best_agent"] == "agent-002"

    def test_suggest_team_for_task(self):
        """Should suggest optimal team based on historical performance."""
        from src.audit.dashboard import AuditDashboard

        audit_events = [
            # agent-001 specializes in testing
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "testing"}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "testing"}},
            # agent-002 specializes in implementation
            {"actor_id": "agent-002", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True, "task_type": "implementation"}},
        ]

        dashboard = AuditDashboard(audit_events)

        team = dashboard.suggest_team(["testing", "implementation"])

        assert "agent-001" in team
        assert "agent-002" in team


class TestValueProposition:
    """Tests for unbiased production insights (vs leaderboards)."""

    def test_production_vs_benchmark_comparison(self):
        """Should show real production performance, not benchmark scores."""
        from src.audit.dashboard import AuditDashboard

        # Real production data shows different results than benchmarks
        audit_events = [
            # agent-001 (high benchmark score) struggles in production
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": False}},
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": False}},
            # agent-002 (lower benchmark) excels in production
            {"actor_id": "agent-002", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True}},
            {"actor_id": "agent-002", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True}},
        ]

        dashboard = AuditDashboard(audit_events)

        # Inject benchmark data for comparison
        dashboard.set_benchmark_data({
            "agent-001": {"swe_bench_score": 0.85},
            "agent-002": {"swe_bench_score": 0.65},
        })

        comparison = dashboard.compare_to_benchmarks()

        # Production reality differs from benchmarks
        assert comparison["agent-001"]["production_success_rate"] < comparison["agent-001"]["benchmark_score"]
        assert comparison["agent-002"]["production_success_rate"] > comparison["agent-002"]["benchmark_score"]


class TestDashboardSummary:
    """Tests for dashboard summary generation."""

    def test_generate_summary(self):
        """Should generate human-readable summary."""
        from src.audit.dashboard import AuditDashboard, AgentIdentity

        audit_events = [
            {"actor_id": "agent-001", "event_type": "CYCLE_COMPLETED",
             "payload": {"success": True}},
        ]

        dashboard = AuditDashboard(audit_events)
        dashboard.register_identity("agent-001", AgentIdentity(
            display_name="Claude",
            model_id="claude-opus-4-5-20251101",
            provider="Anthropic"
        ))
        dashboard.inject_cost_data({"agent-001": {"total_cost": 1.0, "tasks": 10}})

        summary = dashboard.get_summary()

        assert "agents" in summary
        assert summary["total_tasks"] >= 1
