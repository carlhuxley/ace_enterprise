"""
IterativeTDDRunner — Kent Beck-style RED→GREEN→REFACTOR loop.

Two execution modes:

  Gherkin-driven  (when gherkin_scenarios is supplied):
    Iterates one scenario per cycle in declaration order. File paths are
    pinned from the first planning call so all scenarios write into the
    same test / impl files.

  Planner-driven  (plain requirement string, no scenarios):
    IncrementalPlanner freely chooses the next test increment each cycle
    until it returns COMPLETE or max_iterations is reached.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.incremental_planner import COMPLETE, IncrementalPlanner, TestIncrement
from src.agents.language_pod import PodSpec
from src.agents.tdd_cycle_runner import CycleResult, TDDCycleRunner

logger = logging.getLogger(__name__)


@dataclass
class IterativeResult:
    """Outcome of a full iterative TDD session."""

    cycles: list[CycleResult] = field(default_factory=list)
    complete: bool = False
    iterations: int = 0

    @property
    def success(self) -> bool:
        return self.complete and all(c.success for c in self.cycles)


class IterativeTDDRunner:
    """
    Iterative TDD loop: plan → RED → GREEN → REFACTOR → repeat.

    When gherkin_scenarios is supplied, each scenario becomes exactly one
    cycle (Gherkin-driven mode). Otherwise, IncrementalPlanner chooses the
    next test each cycle until COMPLETE (planner-driven mode).
    """

    def __init__(
        self,
        pod,
        planner: IncrementalPlanner,
        max_iterations: int = 10,
        max_green_attempts: int = 3,
        experiment_logger=None,
        playbook_id: str = "default",
        reflector=None,
        curator=None,
    ) -> None:
        self._pod = pod
        self._planner = planner
        self._max_iterations = max_iterations
        self._runner_kwargs = dict(
            max_green_attempts=max_green_attempts,
            experiment_logger=experiment_logger,
            playbook_id=playbook_id,
            reflector=reflector,
            curator=curator,
        )

    def run_from_feature(self, feature_path: "Path | str") -> IterativeResult:
        """Parse a Gherkin .feature file and run in Gherkin-driven mode.

        File paths are derived from the feature file stem so all scenarios
        write into the same consistently-named test / impl files.
        """
        from pathlib import Path as _Path
        from src.agents.gherkin_feature_bridge import GherkinFeatureBridge
        feature_path = _Path(feature_path)
        spec = GherkinFeatureBridge.parse(feature_path)
        stem = feature_path.stem
        return self.run(
            requirement=spec.as_requirement(),
            gherkin_context=feature_path.read_text(encoding="utf-8"),
            gherkin_scenarios=spec.scenarios,
            test_file=self._planner._test_dir / f"test_{stem}.py",
            impl_file=self._planner._src_dir / f"{stem}.py",
        )

    def run(
        self,
        requirement: str,
        gherkin_context: str | None = None,
        gherkin_scenarios=None,
        test_file: "Path | None" = None,
        impl_file: "Path | None" = None,
    ) -> IterativeResult:
        if gherkin_scenarios:
            return self._run_gherkin_driven(
                requirement, gherkin_context, gherkin_scenarios,
                test_file=test_file, impl_file=impl_file,
            )
        return self._run_planner_driven(requirement, gherkin_context, gherkin_scenarios)

    # ------------------------------------------------------------------
    # Gherkin-driven: one scenario per cycle
    # ------------------------------------------------------------------

    def _run_gherkin_driven(
        self,
        requirement: str,
        gherkin_context: str,
        gherkin_scenarios,
        *,
        test_file: "Path | None" = None,
        impl_file: "Path | None" = None,
    ) -> IterativeResult:
        results: list[CycleResult] = []
        # Pre-pin paths when supplied (e.g. derived from feature file name in
        # run_from_feature). If not supplied, pin from the first planning call.
        pinned_test_file: Path | None = test_file
        pinned_impl_file: Path | None = impl_file

        for i, scenario in enumerate(gherkin_scenarios, 1):
            sname = scenario.name if hasattr(scenario, "name") else scenario.get("name", f"scenario_{i}")
            logger.info("IterativeTDDRunner [gherkin]: cycle %d — %s", i, sname)

            try:
                increment = self._planner.next_increment_for_scenario(
                    requirement=requirement,
                    cycle_number=i,
                    scenario=scenario,
                    gherkin_context=gherkin_context,
                    test_file=pinned_test_file,
                    impl_file=pinned_impl_file,
                )
            except Exception as exc:
                logger.warning("IterativeTDDRunner: planner error on scenario %d — %s", i, exc)
                increment = None

            if increment is None:
                logger.warning("IterativeTDDRunner: parse error for scenario %d, skipping", i)
                continue

            # Pin file paths from first planning call when not pre-supplied
            if pinned_test_file is None:
                pinned_test_file = increment.test_file
                pinned_impl_file = increment.implementation_file

            spec = PodSpec(
                feature_requirement=increment.description,
                test_file=increment.test_file,
                implementation_file=increment.implementation_file,
                cycle_number=i,
                gherkin_context=gherkin_context,
            )

            runner = TDDCycleRunner(self._pod, **self._runner_kwargs)
            result = runner.run(spec)
            results.append(result)

            if result.red_result.passed is False and result.green_result.passed:
                if spec.test_file.exists():
                    self._planner.record_test_written(
                        test_file=spec.test_file,
                        test_name=increment.test_name,
                        test_code=spec.test_file.read_text(),
                        cycle_number=i,
                    )

            if not result.success:
                logger.warning("IterativeTDDRunner: scenario %d failed — %s", i, result.error)

        complete = len(results) == len(gherkin_scenarios) and all(r.success for r in results)
        return IterativeResult(cycles=results, complete=complete, iterations=len(gherkin_scenarios))

    # ------------------------------------------------------------------
    # Planner-driven: free-choice increments until COMPLETE
    # ------------------------------------------------------------------

    def _run_planner_driven(
        self,
        requirement: str,
        gherkin_context: str | None,
        gherkin_scenarios,
    ) -> IterativeResult:
        results: list[CycleResult] = []
        cycle_number = 1

        while cycle_number <= self._max_iterations:
            logger.info("IterativeTDDRunner: cycle %d — planning next increment", cycle_number)

            increment = self._planner.next_increment(
                requirement,
                cycle_number,
                gherkin_context=gherkin_context,
                gherkin_scenarios=gherkin_scenarios,
            )

            if increment is COMPLETE:
                logger.info("IterativeTDDRunner: planner says COMPLETE after %d cycles", cycle_number - 1)
                return IterativeResult(cycles=results, complete=True, iterations=cycle_number - 1)

            if increment is None:
                logger.warning("IterativeTDDRunner: parse error on cycle %d, skipping", cycle_number)
                cycle_number += 1
                continue

            spec = PodSpec(
                feature_requirement=increment.description,
                test_file=increment.test_file,
                implementation_file=increment.implementation_file,
                cycle_number=cycle_number,
                gherkin_context=gherkin_context,
            )

            runner = TDDCycleRunner(self._pod, **self._runner_kwargs)
            result = runner.run(spec)
            results.append(result)

            if result.red_result.passed is False and result.green_result.passed:
                if spec.test_file.exists():
                    self._planner.record_test_written(
                        test_file=spec.test_file,
                        test_name=increment.test_name,
                        test_code=spec.test_file.read_text(),
                        cycle_number=cycle_number,
                    )

            if not result.success:
                logger.warning("IterativeTDDRunner: cycle %d failed — %s", cycle_number, result.error)

            cycle_number += 1

        logger.warning("IterativeTDDRunner: reached max_iterations (%d)", self._max_iterations)
        return IterativeResult(cycles=results, complete=False, iterations=self._max_iterations)
