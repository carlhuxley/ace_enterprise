"""Tests for src/agents/simulation_replay.py -- replaying an archived
SimulationPod attempt (demos/demo_simulation_pod_gui.py's live GUI playback,
and `ace view`'s headless telemetry inspection + on-demand video export).

resolve_attempt() needs no pybullet (it only loads a controller module and
reads a JSON sidecar); render_attempt_video() is real-physics + real video
muxing, requires the optional `simulation` extra installed.
"""
import json

import pytest

from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_replay import resolve_attempt

_CONTROLLER_SRC = (
    "def compute_action(observation):\n"
    "    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.01}\n"
)


def _write_attempt(tmp_path, with_telemetry=True):
    py_path = tmp_path / "controller_cycle1_green_attempt1.py"
    py_path.write_text(_CONTROLLER_SRC)
    if with_telemetry:
        json_path = tmp_path / "controller_cycle1_green_attempt1.json"
        json_path.write_text(json.dumps({
            "telemetry": {
                "success": True, "steps_taken": 42, "violated": False,
                "violated_metric": None, "stalled": False, "phase": "converged",
                "peak_metrics": {}, "final_metrics": {}, "metric_traces": {},
                "failure_reason": None,
            },
            "invariants": [
                {"metric": "error", "operator": "<=", "threshold": 0.001, "scope": "final", "within_steps": 500},
            ],
        }))
    return py_path


def test_resolve_attempt_from_py_path_loads_controller_and_telemetry(tmp_path):
    py_path = _write_attempt(tmp_path)

    attempt = resolve_attempt(py_path)

    assert attempt.controller({"x": 0}) == {"vx": 0.0, "vy": 0.0, "vz": -0.01}
    assert attempt.telemetry.success is True
    assert attempt.telemetry.steps_taken == 42
    assert attempt.invariants == [MetricBound("error", "<=", 0.001, "final", within_steps=500)]


def test_resolve_attempt_from_json_path_resolves_the_sibling_py(tmp_path):
    py_path = _write_attempt(tmp_path)
    json_path = py_path.with_suffix(".json")

    attempt = resolve_attempt(json_path)

    assert attempt.controller_path == py_path
    assert attempt.telemetry is not None


def test_resolve_attempt_with_no_telemetry_json_degrades_gracefully(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)

    attempt = resolve_attempt(py_path)

    assert attempt.telemetry is None
    assert attempt.invariants == []
    assert attempt.controller is not None  # controller still loads fine


def test_resolve_attempt_missing_py_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_attempt(tmp_path / "nope.py")


def test_resolve_attempt_defaults_scenario_to_peg(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)

    attempt = resolve_attempt(py_path)

    assert attempt.scenario_name == "peg"


def test_resolve_attempt_rejects_unknown_scenario_override(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)

    with pytest.raises(ValueError, match="unknown scenario"):
        resolve_attempt(py_path, scenario_override="not-a-scenario")


# ---------------------------------------------------------------------------
# Real-physics video export (requires the optional `simulation` extra).
# ---------------------------------------------------------------------------

pytest.importorskip("pybullet", reason="pybullet not installed (pip install -e .[simulation])")
pytest.importorskip("imageio", reason="imageio not installed (pip install -e .[simulation])")


def test_render_attempt_video_produces_a_nonempty_file(tmp_path):
    from src.agents.simulation_replay import render_attempt_video

    py_path = _write_attempt(tmp_path, with_telemetry=False)
    attempt = resolve_attempt(py_path)
    output_path = tmp_path / "attempt.mp4"

    result = render_attempt_video(attempt, output_path, max_steps=5)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
