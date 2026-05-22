"""
IterativeTDDRunner — Kent Beck-style RED→GREEN→REFACTOR loop.

Uses IncrementalPlanner to decide what test to write next, then delegates
each cycle to TDDCycleRunner. Continues until the planner returns COMPLETE
or max_iterations is reached.
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

    Wraps TDDCycleRunner with an IncrementalPlanner that determines each
    next test increment. After each successful cycle the planner is updated
    with the new test so it knows what's already covered.
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
        """Parse a Gherkin .feature file and run the iterative TDD loop."""
        from pathlib import Path as _Path
        from src.agents.gherkin_feature_bridge import GherkinFeatureBridge
        feature_path = _Path(feature_path)
        spec = GherkinFeatureBridge.parse(feature_path)
        return self.run(
            requirement=spec.as_requirement(),
            gherkin_context=feature_path.read_text(encoding="utf-8"),
            gherkin_scenarios=spec.scenarios,
        )

    def run(
        self,
        requirement: str,
        gherkin_context: str | None = None,
        gherkin_scenarios=None,
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
            )

            runner = TDDCycleRunner(self._pod, **self._runner_kwargs)
            result = runner.run(spec)
            results.append(result)

            if result.red_result.passed is False and result.green_result.passed:
                # RED produced a test file — record it for future planning context
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
