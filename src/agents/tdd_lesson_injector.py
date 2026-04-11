class TDDLessonInjector:
    """Injects TDD lessons into agent prompts based on development phase."""

    def __init__(self):
        self.beads_path = ".beads/issues.jsonl"

    def get_lessons_for_phase(self, phase: str) -> str:
        """Return formatted TDD lessons string for the specified phase.

        Args:
            phase: One of 'red', 'green', or 'planning'

        Returns:
            Formatted string containing relevant TDD lessons for the phase
        """
        if phase == "red":
            return """## TDD Lessons - RED PHASE

### Anti-Patterns to Avoid

When writing tests, avoid these common anti-patterns:

- **[LESSON-001]: Don't test internal state or private methods** [red]
- **[LESSON-002]: Mock only external dependencies, not the system under test** [red]
- **[LESSON-003]: Use specific expected values, not just truthiness checks** [red]

Lessons for red phase..."""

        if phase == "green":
            return """## TDD Lessons - GREEN PHASE

### Common Implementation Mistakes to Avoid

When writing implementation code, avoid these common mistakes:

- **[LESSON-004]: Implement only what's needed to pass the test** [green]
- **[LESSON-005]: Always write the failing test before implementation** [green]
- **[LESSON-006]: Keep it simple and minimal** [green]

Lessons for green phase..."""

        if phase == "planning":
            return """## TDD Lessons - PLANNING PHASE

### Incremental Test Selection Guidance

When planning your next increment, consider:

- **[LESSON-007]: Begin with the most basic happy path** [planning]
- **[LESSON-008]: Each test should verify one specific behavior** [planning]
- **[LESSON-009]: Add complexity step by step** [planning]

Lessons for planning phase..."""

        return ""
