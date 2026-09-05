"""Concrete SimulationScenario implementations for SimulationPod.

Each module here defines one physical task (peg-in-hole insertion,
trajectory following, ...) as a plain class satisfying the
SimulationScenario protocol (src/agents/simulation_scenario.py). Adding a new
physical task requires only a new module here -- no changes to
SimulationPod, SimulationOracle, or simulation_runner.py.
"""
