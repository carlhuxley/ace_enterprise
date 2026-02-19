"""
TDD Agent - Test-Driven Development with ACE Learning

This agent follows TDD workflow:
1. Red: Run failing test(s)
2. Green: Generate minimal code to pass test(s)
3. Refactor: (Future: suggest improvements)
4. Learn: When generation fails, reflect and update playbook

The agent works with real project structures and separate test files.
"""
import re
import subprocess
from pathlib import Path

from src.core.curator.module import Curator
from src.core.generator.module import Generator
from src.core.reflector.module import Reflector
from src.playbook.manager import PlaybookManager
from src.storage.schemas import (
    EnvironmentFeedback,
    PlaybookCreate,
    TaskInput,
)
from src.utils.llm_client import LLMClient


class TDDAgent:
    """
    Agent that implements TDD workflow with ACE learning.

    The agent:
    - Runs tests to identify failures
    - Generates code to make tests pass
    - Learns from failures through reflection and curation
    - Follows TDD best practices from playbook
    """

    def __init__(
        self,
        playbook_manager: PlaybookManager | None = None,
        llm_client: LLMClient | None = None,
        playbook_id: str | None = None,
        language: str = "python",
    ):
        """
        Initialize TDD Agent.

        Args:
            playbook_manager: Manages playbooks (creates one if None)
            llm_client: LLM client for generation (creates one if None)
            playbook_id: Existing playbook to use (creates one if None)
            language: Programming language (python, javascript, java, etc.)
        """
        self.playbook_manager = playbook_manager or PlaybookManager()
        self.llm_client = llm_client or LLMClient()
        self.language = language

        # Initialize ACE modules
        self.generator = Generator(self.playbook_manager, self.llm_client)
        self.reflector = Reflector(self.llm_client)
        self.curator = Curator(self.playbook_manager, self.llm_client)

        # Get or create playbook
        if playbook_id:
            self.playbook_id = playbook_id
        else:
            playbook = self.playbook_manager.create_playbook(
                PlaybookCreate(
                    domain=f"tdd_{language}",
                    base_model=self.llm_client.model,
                )
            )
            self.playbook_id = playbook.playbook_id

    def run_tests(
        self,
        test_path: Path,
        specific_test: str | None = None,
    ) -> tuple[bool, str, list[str]]:
        """
        Run tests and return results.

        Args:
            test_path: Path to test file or directory
            specific_test: Specific test name to run (None = all tests)

        Returns:
            (all_passed, output, failed_tests)
        """
        if self.language == "python":
            return self._run_python_tests(test_path, specific_test)
        else:
            raise NotImplementedError(f"Language {self.language} not yet supported")

    def _run_python_tests(
        self,
        test_path: Path,
        specific_test: str | None = None,
    ) -> tuple[bool, str, list[str]]:
        """Run Python tests with pytest."""
        cmd = [
            "python", "-m", "pytest",
            str(test_path),
            "-v",
            "--tb=short",
            "-p", "no:cov",
            "--override-ini=addopts=",
        ]

        if specific_test:
            cmd.extend(["-k", specific_test])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=test_path.parent if test_path.is_file() else test_path,
        )

        output = result.stdout + "\n" + result.stderr
        all_passed = result.returncode == 0

        # Extract failed test names
        failed_tests = []
        for line in output.split('\n'):
            if 'FAILED' in line:
                # Extract test name from lines like:
                # "FAILED test_file.py::test_name - AssertionError"
                match = re.search(r'FAILED\s+(.+?)\s+-', line)
                if match:
                    failed_tests.append(match.group(1))

        return all_passed, output, failed_tests

    def extract_code_from_solution(self, solution: str) -> str:
        """Extract clean code from LLM solution (handles markdown blocks)."""
        patterns = [
            r'```python\n(.*?)\n```',
            r'```\n(.*?)\n```',
            r'```python(.*?)```',
            r'```(.*?)```',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, solution, re.DOTALL)
            if matches:
                return matches[0].strip()

        return solution.strip()

    def make_test_pass(
        self,
        test_path: Path,
        impl_path: Path,
        test_name: str | None = None,
        max_iterations: int = 3,
    ) -> dict:
        """
        Implement TDD cycle to make test(s) pass.

        Args:
            test_path: Path to test file
            impl_path: Path where implementation should be written
            test_name: Specific test to make pass (None = all tests)
            max_iterations: Maximum learning iterations

        Returns:
            dict with results including success, iterations, playbook changes
        """
        results = {
            "success": False,
            "iterations": 0,
            "test_name": test_name or "all tests",
            "final_output": "",
            "bullets_added": 0,
            "learning_occurred": False,
        }

        # Read test file for context
        test_content = test_path.read_text()

        for iteration in range(1, max_iterations + 1):
            results["iterations"] = iteration

            # Step 1: Generate implementation
            task = self._create_task(
                test_content=test_content,
                test_name=test_name,
                impl_path=impl_path,
                iteration=iteration,
            )

            gen_output = self.generator.execute(
                task=task,
                playbook_id=self.playbook_id,
            )

            # Extract clean code
            clean_code = self.extract_code_from_solution(gen_output.solution)

            # Write implementation
            impl_path.parent.mkdir(parents=True, exist_ok=True)
            impl_path.write_text(clean_code)

            # Step 2: Run tests
            passed, output, failed_tests = self.run_tests(test_path, test_name)

            results["final_output"] = output

            if passed:
                results["success"] = True
                return results

            # Step 3: Tests failed - create environment feedback
            env_feedback = EnvironmentFeedback(
                result="FAILED",
                feedback=f"Tests failed on iteration {iteration}",
                expected="All tests pass",
                actual=f"{len(failed_tests)} test(s) failed",
                test_report={
                    "output": output,
                    "failed_tests": failed_tests,
                    "iteration": iteration,
                }
            )

            # Step 4: Reflect on failure
            refl_output = self.reflector.reflect(
                task=task,
                generator_output=gen_output,
                environment_feedback=env_feedback,
            )

            # Step 5: Curate new knowledge
            cur_output = self.curator.curate(
                reflector_output=refl_output,
                playbook_id=self.playbook_id,
            )

            # Step 6: Apply updates
            added_ids = self.curator.apply_updates(
                playbook_id=self.playbook_id,
                curator_output=cur_output,
            )

            results["bullets_added"] += len(added_ids)
            results["learning_occurred"] = True

            # Continue to next iteration with learned knowledge

        return results

    def _create_task(
        self,
        test_content: str,
        test_name: str | None,
        impl_path: Path,
        iteration: int,
    ) -> TaskInput:
        """Create task for generator based on test requirements."""
        if test_name:
            # Extract specific test
            test_section = self._extract_test_section(test_content, test_name)
            focus = f"the test '{test_name}'"
        else:
            test_section = test_content
            focus = "all tests"

        module_name = impl_path.stem  # e.g., "calculator" from "calculator.py"

        # Read existing implementation if it exists
        existing_code = ""
        if impl_path.exists():
            existing_code = impl_path.read_text()

        # Build query
        if existing_code:
            query = f"""Update implementation for '{module_name}.py' to make {focus} pass.

Current implementation:
{existing_code}

Test code:
{test_section}

Requirements:
- KEEP all existing functions that already work
- ADD or UPDATE only what's needed to pass {focus}
- Follow TDD best practices: minimal changes to pass the test
- Return the COMPLETE updated code for {module_name}.py
- No markdown blocks, no explanations
- Just the full Python code with all functions

This is iteration {iteration}. If you have playbook guidance, follow it.
"""
        else:
            query = f"""Generate implementation for '{module_name}.py' to make {focus} pass.

Test code:
{test_section}

Requirements:
- Follow TDD best practices: write minimal code to pass the test
- Return ONLY the Python code for {module_name}.py
- No markdown blocks, no explanations
- Just the necessary functions/classes

This is iteration {iteration}. If you have playbook guidance, follow it.
"""

        return TaskInput(
            id=f"tdd_{module_name}_{iteration:03d}",
            query=query,
            type="code_generation",
            difficulty="normal",
        )

    def _extract_test_section(self, test_content: str, test_name: str) -> str:
        """Extract a specific test function from test file."""
        lines = test_content.split('\n')
        result_lines = []
        in_target = False

        for line in lines:
            if f"def {test_name}" in line:
                in_target = True

            if in_target:
                result_lines.append(line)

                # Stop at next function or class definition
                if line.strip().startswith('def ') and f"def {test_name}" not in line:
                    break
                if line.strip().startswith('class '):
                    break

        return '\n'.join(result_lines)

    def get_playbook_stats(self) -> dict:
        """Get current playbook statistics."""
        return self.playbook_manager.get_statistics(self.playbook_id)
