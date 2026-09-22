"""
WorkerAgent — standalone LLM code-generation component.

Separates the prompt-building + LLM-calling concern from the TDD loop
orchestration. Receives feature context and optional constraints (playbook
bullets, AST context map) explicitly; returns code strings. File I/O and
test execution are the caller's (pod's) responsibility.
"""
from __future__ import annotations

import re

from src.agents.import_filter import DEFAULT_BLOCKED_BUILTINS, DEFAULT_BLOCKLIST
from src.agents.language_pod import PodSpec

_PLAYBOOK_SECTION = "strategies_and_hard_rules"
_TEST_RULES_SECTION = "test_assertion_rules"

# WorkerAgent always generates for pytest-run Python (see PodmanRunner's
# `python -m pytest` invocation) -- fixed by this class's own design, not
# something a caller configures.
_TECH_STACK = {"language": "python", "testing": "pytest"}

# The sandbox's static import filter rejects these outright and does NOT retry,
# so every prompt has to warn the model up front (see src/agents/import_filter.py).
_SANDBOX_IMPORT_RULE = (
    "SANDBOX: these imports are blocked and abort the run — "
    f"{', '.join(sorted(DEFAULT_BLOCKLIST))}; "
    f"and {', '.join(sorted(DEFAULT_BLOCKED_BUILTINS))}() are blocked as calls. "
    "Use pathlib.Path for all filesystem work (mkdir(parents=True, exist_ok=True), "
    "write_text, read_text, exists); use pytest's tmp_path fixture for temp dirs."
)


def _flat_import_rule(spec: PodSpec) -> str:
    """Neither _test_prompt nor _impl_prompt stated any convention for
    importing sibling project modules, so the model guessed -- often a
    `src.`-qualified package path that doesn't exist in this project's flat
    layout (test/impl files as siblings, no package wrapper), failing every
    run at pytest collection before any test logic runs, with no retry able
    to recover since the same guess repeats. State it explicitly and
    concretely, naming this module, rather than leaving it to a prior."""
    stem = spec.implementation_file.stem
    return (
        f"LAYOUT: this project is flat — {spec.implementation_file.name} and every "
        f"sibling module live directly under the source directory, with no package "
        f"wrapper. Import this module as `from {stem} import ...`, and any other "
        f"project module the same way: `from other_module import ...`. NEVER "
        f"prefix a project-module import with `src.` or any other package/"
        f"directory name (e.g. `from src.{stem} import ...` is wrong) — that path "
        f"does not exist in the sandbox and fails at collection before any test "
        f"logic runs."
    )

_DEFAULT_TEST_RULES = [
    (
        "Assert PROPERTIES not exact value when multiple correct outputs exist "
        "(e.g. shortest paths, orderings, set members): use len(), structural validity loops, "
        "membership checks like result[0]==start and result[-1]==end"
    ),
    (
        "Use == equality on the full result only when there is provably ONE correct answer "
        "(arithmetic, deterministic transformations, unique key lookup)"
    ),
    (
        "Never assert a specific path or ordering when the algorithm may produce "
        "any valid path of equal quality"
    ),
]


class WorkerAgent:
    """
    Generates code for each TDD phase given a PodSpec and optional context.

    Call generate_test for RED, generate_implementation for GREEN,
    and generate_refactor for REFACTOR. All methods return raw code strings.
    """

    def __init__(
        self, llm_client, playbook_manager=None, context_map=None, temperature: float = 0.0,
        retrieval_service=None, team_id: str | None = None, project_id: str | None = None,
        project_path: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self._playbook_manager = playbook_manager
        self._context_map = context_map
        self._temperature = temperature
        # Optional src.retrieval.service.InstitutionalKnowledgeService (CGR3).
        # When set, _get_bullets() asks it for context-ranked, verdict-filtered
        # guidance instead of dumping every bullet in the section -- see
        # ace_enterprise#66. None preserves the original unconditional-dump
        # behavior exactly, so this is additive, not a breaking change.
        self._retrieval_service = retrieval_service
        # Real signal for RetrievalContext (ace_enterprise#66 gap 2) -- until
        # now every retrieval_service call passed context=None, so CGR3's
        # team/tech_stack/project scoring dimensions (src/retrieval/
        # context_scorer.py) never had anything to score against. team_id
        # and project_id mirror ProjectConfig's own fields of the same name
        # (src/cli/config.py); tech_stack is this pod's own fixed toolchain,
        # not caller-configurable.
        self._team_id = team_id
        self._project_id = project_id
        self._project_path = project_path
        # IDs from the most recent _get_bullets() call (the GREEN/patch strategy
        # bullets, not test-rules bullets) -- pods read this right after calling
        # generate_implementation/generate_patch to attach it to the PhaseResult,
        # so TDDCycleRunner can put it on the CYCLE_COMPLETED audit payload.
        self.last_retrieved_bullet_ids: list[str] = []

    def generate_test(self, spec: PodSpec, existing_code: str = "") -> str:
        prompt = self._test_prompt(spec, existing_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_implementation(
        self,
        spec: PodSpec,
        error_output: str = "",
        module_context: str = "",
        failing_test_ids: list[str] | None = None,
        test_code: str = "",
        existing_code: str = "",
    ) -> str:
        if not module_context and self._context_map and failing_test_ids:
            module_context = self._context_from_map(failing_test_ids)
        bullets = self._get_bullets(spec.feature_requirement)
        prompt = self._impl_prompt(
            spec, error_output, module_context, bullets, test_code, existing_code
        )
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_refactor(self, spec: PodSpec, current_code: str = "") -> str:
        prompt = self._refactor_prompt(spec, current_code)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return _extract_code(response.get("content", ""))

    def generate_patch(
        self,
        spec: PodSpec,
        *,
        existing_code: str,
        error_output: str = "",
        test_code: str = "",
    ) -> str:
        """SEARCH/REPLACE-block edit of `existing_code` (src/utils/patcher.py
        applies it deterministically, host-side) rather than a whole-file
        rewrite. Returns the raw response text -- not code-fence-extracted,
        since the payload is SEARCH/REPLACE markers, not a source file."""
        bullets = self._get_bullets(spec.feature_requirement)
        prompt = self._patch_prompt(spec, existing_code, error_output, test_code, bullets)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return response.get("content", "")

    def generate_multi_file_patch(
        self,
        spec: PodSpec,
        *,
        existing_by_file: dict[str, str],
        error_output: str = "",
        test_code: str = "",
    ) -> str:
        """Coordinated SEARCH/REPLACE edit across multiple existing files in
        one GREEN (ace_enterprise#64) -- e.g. a change that spans an enum in
        one module and a method using it in another. `existing_by_file` maps
        filename (as it must be referenced in the response's '### FILE:'
        markers) to that file's current content; src/utils/patcher.py's
        apply_multi_file_patch() applies the result. Returns the raw
        response text, same as generate_patch()."""
        bullets = self._get_bullets(spec.feature_requirement)
        prompt = self._multi_file_patch_prompt(spec, existing_by_file, error_output, test_code, bullets)
        response = self.llm_client.generate(prompt, temperature=self._temperature)
        return response.get("content", "")

    # --- prompt builders ---

    def _test_prompt(self, spec: PodSpec, existing_code: str) -> str:
        parts = [
            f"Add ONE new failing pytest test for: {spec.feature_requirement}",
            f"Test file: {spec.test_file.name}",
            "The new test must FAIL before any implementation exists (RED phase).",
            "Do NOT duplicate or overlap with any existing test; give it a unique name.",
            _SANDBOX_IMPORT_RULE,
            _flat_import_rule(spec),
        ]
        if spec.gherkin_context:
            parts.append(
                f"\nAcceptance criteria (Gherkin — use exact values from relevant scenarios):\n"
                f"```gherkin\n{spec.gherkin_context}\n```"
            )
        rules = self._get_test_bullets()
        if rules:
            parts.append("\nAssertion contract rules:\n" + "\n".join(f"- {r}" for r in rules))
        if existing_code:
            parts.append(
                f"\nExisting tests (KEEP ALL of these unchanged):\n{existing_code}"
                "\n\nOutput the COMPLETE test file: all existing tests preserved, "
                "plus exactly ONE new failing test function appended at the end."
            )
        else:
            parts.append("Output only valid Python code.")
        return "\n".join(parts)

    def _impl_prompt(
        self,
        spec: PodSpec,
        error_output: str,
        module_context: str,
        bullets: list[str],
        test_code: str = "",
        existing_code: str = "",
    ) -> str:
        if existing_code:
            lead = (
                "Extend the EXISTING module below so the whole test file passes. "
                "Keep every function, class, and import that the already-passing "
                "tests depend on — add to or refactor the code, do NOT rewrite it "
                "from scratch or drop anything. Output the COMPLETE updated module."
            )
        else:
            lead = "Write the minimal implementation to make the failing tests pass."
        parts = [
            lead,
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
            _SANDBOX_IMPORT_RULE,
            _flat_import_rule(spec),
        ]
        if existing_code:
            parts.append(f"\nExisting module ({spec.implementation_file.name}):\n"
                         f"```python\n{existing_code}\n```")
        if test_code:
            parts.append(f"\nTest file to satisfy:\n```python\n{test_code}\n```")
        if error_output:
            parts.append(f"\nTest failure output:\n{error_output}")
        if module_context:
            parts.append(f"\nModule context (AST signatures):\n{module_context}")
        if bullets:
            parts.append("\nPlaybook guidance:\n" + "\n".join(f"- {b}" for b in bullets))
        parts.append("Output only valid Python code.")
        return "\n".join(parts)

    def _patch_prompt(
        self,
        spec: PodSpec,
        existing_code: str,
        error_output: str,
        test_code: str,
        bullets: list[str],
    ) -> str:
        parts = [
            "Modify the EXISTING module below so the whole test file passes, "
            "using SEARCH/REPLACE blocks -- do NOT output the whole file.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
            _SANDBOX_IMPORT_RULE,
            _flat_import_rule(spec),
            f"\nExisting module ({spec.implementation_file.name}):\n"
            f"```python\n{existing_code}\n```",
        ]
        if test_code:
            parts.append(f"\nTest file to satisfy:\n```python\n{test_code}\n```")
        if error_output:
            parts.append(f"\nTest failure output:\n{error_output}")
        if bullets:
            parts.append("\nPlaybook guidance:\n" + "\n".join(f"- {b}" for b in bullets))
        parts.append(
            "\nOutput ONLY one or more SEARCH/REPLACE blocks in this EXACT "
            "format, nothing else -- no prose, no markdown fence around the "
            "blocks themselves:\n\n"
            "<<<<<<< SEARCH\n"
            "<exact existing lines to find, copied verbatim from the module above>\n"
            "=======\n"
            "<the replacement lines>\n"
            ">>>>>>> REPLACE\n\n"
            "Rules:\n"
            "- The SEARCH text must match a contiguous block of lines EXACTLY "
            "as they appear above (same whitespace/indentation) -- copy it, "
            "don't retype it from memory.\n"
            "- Keep each block minimal: only the lines that change, plus just "
            "enough surrounding context to make the match unambiguous (it "
            "must match exactly once).\n"
            "- Output multiple SEARCH/REPLACE blocks for multiple separate edits.\n"
            "- To add new code with nothing to anchor it to, SEARCH for the "
            "last line of the existing module and REPLACE it with itself plus "
            "the new code appended after."
        )
        return "\n".join(parts)

    def _multi_file_patch_prompt(
        self,
        spec: PodSpec,
        existing_by_file: dict[str, str],
        error_output: str,
        test_code: str,
        bullets: list[str],
    ) -> str:
        parts = [
            "Modify the EXISTING files below so the whole test file passes, "
            "using SEARCH/REPLACE blocks -- do NOT output whole files. This "
            "change spans multiple files; coordinate the edits across all of "
            "them as needed, but only touch a file if it actually needs to change.",
            f"Feature: {spec.feature_requirement}",
            _SANDBOX_IMPORT_RULE,
            _flat_import_rule(spec),
        ]
        for filename, content in existing_by_file.items():
            parts.append(f"\nExisting file ({filename}):\n```python\n{content}\n```")
        if test_code:
            parts.append(f"\nTest file to satisfy:\n```python\n{test_code}\n```")
        if error_output:
            parts.append(f"\nTest failure output:\n{error_output}")
        if bullets:
            parts.append("\nPlaybook guidance:\n" + "\n".join(f"- {b}" for b in bullets))
        parts.append(
            "\nOutput ONLY one or more '### FILE: <filename>' sections, each "
            "followed by one or more SEARCH/REPLACE blocks, in this EXACT "
            "format, nothing else -- no prose, no markdown fence:\n\n"
            "### FILE: <filename>\n"
            "<<<<<<< SEARCH\n"
            "<exact existing lines to find, copied verbatim from that file above>\n"
            "=======\n"
            "<the replacement lines>\n"
            ">>>>>>> REPLACE\n\n"
            "Rules:\n"
            "- <filename> must be EXACTLY one of the file names given above, "
            "e.g. \"schemas.py\" — not a path, not invented.\n"
            "- The SEARCH text must match a contiguous block of lines EXACTLY "
            "as they appear in that file above (same whitespace/indentation) -- "
            "copy it, don't retype it from memory.\n"
            "- Keep each block minimal: only the lines that change, plus just "
            "enough surrounding context to make the match unambiguous within "
            "that file (it must match exactly once).\n"
            "- Output multiple '### FILE:' sections to edit multiple files, "
            "and multiple SEARCH/REPLACE blocks within one section for "
            "multiple separate edits to that file.\n"
            "- To add new code with nothing to anchor it to, SEARCH for the "
            "last line of that file and REPLACE it with itself plus the new "
            "code appended after.\n"
            "- Do not include a '### FILE:' section for a file that needs no change."
        )
        return "\n".join(parts)

    def _refactor_prompt(self, spec: PodSpec, current_code: str) -> str:
        parts = [
            "Refactor the implementation while keeping tests green.",
            f"Feature: {spec.feature_requirement}",
            f"Implementation file: {spec.implementation_file.name}",
            _SANDBOX_IMPORT_RULE,
            _flat_import_rule(spec),
        ]
        if current_code:
            parts.append(f"\nCurrent code:\n{current_code}")
        parts.append("Output only the refactored Python code.")
        return "\n".join(parts)

    # --- context helpers ---

    def _get_bullets(self, feature_requirement: str = "") -> list[str]:
        if self._retrieval_service is not None:
            try:
                from src.retrieval.schemas import RetrievalContext

                context = RetrievalContext(
                    team_id=self._team_id,
                    project_id=self._project_id,
                    project_path=self._project_path,
                    tech_stack=dict(_TECH_STACK),
                )
                response = self._retrieval_service.get_guidance_for_implementation(
                    feature_requirement, context=context,
                )
                pairs = [(rb.bullet.id, rb.bullet.content) for rb in response.apply]
            except Exception:
                pairs = None
            if pairs is not None:
                # A genuinely empty result (CGR3 ran and found nothing that
                # clears its verdict) is meaningful, not a failure -- return
                # it as-is rather than falling through to the unconditional
                # dump below. Only an exception (the retrieval call itself
                # breaking) falls through, so a real answer is still given.
                self.last_retrieved_bullet_ids = [bullet_id for bullet_id, _ in pairs]
                return [content for _, content in pairs]
        if not self._playbook_manager:
            self.last_retrieved_bullet_ids = []
            return []
        try:
            pairs = self._playbook_manager.get_bullets_with_ids(_PLAYBOOK_SECTION) or []
        except Exception:
            self.last_retrieved_bullet_ids = []
            return []
        self.last_retrieved_bullet_ids = [bullet_id for bullet_id, _ in pairs]
        return [content for _, content in pairs]

    def _get_test_bullets(self) -> list[str]:
        if not self._playbook_manager:
            return _DEFAULT_TEST_RULES
        try:
            bullets = self._playbook_manager.get_bullets(_TEST_RULES_SECTION) or []
            return bullets if bullets else _DEFAULT_TEST_RULES
        except Exception:
            return _DEFAULT_TEST_RULES

    def _context_from_map(self, failing_test_ids: list[str]) -> str:
        try:
            nodes = self._context_map.nodes_relevant_to(failing_test_ids)
            return "\n".join(n.format_compact() for n in nodes)
        except Exception:
            return ""


_PYTHON_CODE_START = re.compile(
    r"^(import\s|from\s\S+\simport\s|def\s|class\s|async def\s|@\w)", re.MULTILINE
)


def _extract_code(content: str) -> str:
    match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\w*\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Unclosed fence (model truncated before closing ```)
    match = re.search(r"```(?:\w+)?\n(.*?)$", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # No fence at all -- the LLM occasionally skips it and replies with a
    # conversational preamble directly followed by source. Drop everything
    # before the first line that's actually Python.
    code_match = _PYTHON_CODE_START.search(content)
    if code_match:
        return content[code_match.start():].strip()
    return content.strip()

