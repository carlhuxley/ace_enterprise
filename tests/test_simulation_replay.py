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
# Reflection loading (#46)
# ---------------------------------------------------------------------------

_REFLECTION_PAYLOAD = {
    "cycle": 1,
    "success": True,
    "feature_requirement": "peg in hole",
    "reflector": {
        "error_identification": None,
        "root_cause": None,
        "correct_approach": None,
        "key_insight": "slow down near contact",
        "code_invariant": None,
    },
    "curator": {
        "reasoning": "converged cleanly",
        "delta_bullets": [{"section": "strategies_and_hard_rules", "content": "slow down near contact"}],
    },
}


def test_resolve_attempt_loads_matching_reflection_file(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)
    (tmp_path / "controller_cycle1.reflection.json").write_text(json.dumps(_REFLECTION_PAYLOAD))

    attempt = resolve_attempt(py_path)

    assert attempt.reflection == _REFLECTION_PAYLOAD


def test_resolve_attempt_reflection_is_none_when_no_file_present(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)

    attempt = resolve_attempt(py_path)

    assert attempt.reflection is None


def test_resolve_attempt_reflection_keys_on_cycle_not_specific_attempt(tmp_path):
    # A second archived attempt in the SAME cycle (e.g. a later GREEN retry)
    # must resolve to the same, coarser per-cycle reflection file.
    py_path2 = tmp_path / "controller_cycle1_green_attempt2.py"
    py_path2.write_text(_CONTROLLER_SRC)
    (tmp_path / "controller_cycle1.reflection.json").write_text(json.dumps(_REFLECTION_PAYLOAD))

    attempt = resolve_attempt(py_path2)

    assert attempt.reflection == _REFLECTION_PAYLOAD


def test_resolve_attempt_reflection_does_not_match_a_different_cycle(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)  # cycle1
    (tmp_path / "controller_cycle2.reflection.json").write_text(json.dumps(_REFLECTION_PAYLOAD))

    attempt = resolve_attempt(py_path)

    assert attempt.reflection is None


def test_resolve_attempt_malformed_reflection_file_degrades_gracefully(tmp_path):
    py_path = _write_attempt(tmp_path, with_telemetry=False)
    (tmp_path / "controller_cycle1.reflection.json").write_text("not valid json")

    attempt = resolve_attempt(py_path)

    assert attempt.reflection is None


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


def test_frame_stride_captures_fewer_frames(tmp_path):
    import imageio.v3 as iio

    from src.agents.simulation_replay import render_attempt_video

    py_path = _write_attempt(tmp_path, with_telemetry=False)
    attempt = resolve_attempt(py_path)

    full = render_attempt_video(attempt, tmp_path / "full.mp4", max_steps=20, frame_stride=1)
    strided = render_attempt_video(attempt, tmp_path / "strided.mp4", max_steps=20, frame_stride=5)

    full_frames = iio.imread(full).shape[0]
    strided_frames = iio.imread(strided).shape[0]
    assert strided_frames < full_frames
