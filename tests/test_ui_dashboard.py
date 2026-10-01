"""Smoke tests for src/ui/dashboard.py -- skipped cleanly when the optional
`dashboard` extra (textual) isn't installed, matching this repo's existing
extra-gated-test convention (e.g. simulation/pybullet-dependent tests)."""
from unittest.mock import patch

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, RichLog  # noqa: E402

from src.ui.dashboard import AuditTicker, DashboardApp, PostureBar  # noqa: E402


@pytest.mark.asyncio
async def test_app_mounts_and_renders_expected_widgets(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        assert app.query_one(PostureBar) is not None
        assert app.query_one("#exec_log", RichLog) is not None
        assert app.query_one("#playbook_table", DataTable) is not None
        assert app.query_one(AuditTicker) is not None
        await pilot.pause()


@pytest.mark.asyncio
async def test_sandbox_posture_event_updates_the_posture_bar(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        app._handle_event({
            "type": "sandbox_posture", "pod_name": "harness_abc", "network_mode": "none",
            "cap_drop": "all", "no_new_privileges": True, "rootless": True, "read_only_root": True,
        })
        await pilot.pause()
        rendered = app.query_one(PostureBar).content
        assert "harness_abc" in rendered
        assert "Blocked" in rendered


@pytest.mark.asyncio
async def test_execution_stream_event_appends_to_the_log(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        log = app.query_one("#exec_log", RichLog)
        with patch.object(log, "write") as mock_write:
            app._handle_event({"type": "execution_stream", "phase": "RED", "status": "started"})
            app._handle_event({
                "type": "execution_stream", "phase": "RED", "status": "completed",
                "stdout_chunk": "1 failed", "exit_code": 1,
            })
            await pilot.pause()
        written = [call.args[0] for call in mock_write.call_args_list]
        assert any("RED" in line for line in written)
        assert any("1 failed" in line for line in written)


@pytest.mark.asyncio
async def test_playbook_delta_event_adds_a_table_row(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        app._handle_event({
            "type": "playbook_delta", "bullet_content": "check boundary conditions",
            "bullet_section": "strategies_and_hard_rules", "root_cause": "off-by-one", "cycle_number": 3,
        })
        await pilot.pause()
        table = app.query_one("#playbook_table", DataTable)
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_audit_chain_event_updates_the_ticker(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        app._handle_event({"type": "audit_chain", "event_type": "cycle_completed", "event_hash": "abc123def456"})
        await pilot.pause()
        rendered = app.query_one(AuditTicker).content
        assert "abc123def456"[:12] in rendered


@pytest.mark.asyncio
async def test_malformed_event_does_not_crash_the_app(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        app._handle_event({"type": "sandbox_posture"})  # missing every real field
        app._handle_event({"type": "unknown_event_type", "foo": "bar"})
        await pilot.pause()  # must not raise


@pytest.mark.asyncio
async def test_clear_log_binding_clears_the_execution_log(tmp_path):
    app = DashboardApp(project_root=tmp_path)
    async with app.run_test() as pilot:
        app._handle_event({"type": "execution_stream", "phase": "RED", "status": "started"})
        await pilot.pause()
        log = app.query_one("#exec_log", RichLog)
        with patch.object(log, "clear") as mock_clear:
            await pilot.press("c")
            await pilot.pause()
        mock_clear.assert_called_once()


def test_socket_is_created_on_mount_and_cleaned_up_on_unmount(tmp_path):
    import asyncio

    sock_path = tmp_path / ".ace" / "events.sock"

    async def _run():
        app = DashboardApp(project_root=tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert sock_path.exists()
        return app

    asyncio.run(_run())
    assert not sock_path.exists()


def test_run_dashboard_with_worker_runs_build_fn_and_returns_its_exit_code(tmp_path, monkeypatch):
    calls = []

    def fake_build():
        calls.append("called")
        return 0

    # DashboardApp.run() is a real blocking terminal takeover -- can't call
    # it in a unit test. Exercise the worker wiring directly instead: build
    # the app the same way run_dashboard_with_worker does, drive its worker
    # via the test harness, and confirm the exit code propagates.
    import asyncio

    from src.ui.dashboard import DashboardApp

    async def _run():
        app = DashboardApp(project_root=tmp_path, build_fn=fake_build)
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(20):
                if app.build_exit_code is not None:
                    break
                await asyncio.sleep(0.05)
        return app

    app = asyncio.run(_run())
    assert calls == ["called"]
    assert app.build_exit_code == 0
