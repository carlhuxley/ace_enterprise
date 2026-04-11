# Test file for tdd_lesson_injector
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agents.tdd_lesson_injector import *


def test_default_beads_path():
    injector = TDDLessonInjector()
    assert injector.beads_path == ".beads/issues.jsonl"


def test_get_lessons_for_red_phase_returns_formatted_string():
    injector = TDDLessonInjector()
    result = injector.get_lessons_for_phase("red")
    assert "RED PHASE" in result


def test_get_lessons_for_red_includes_anti_patterns():
    injector = TDDLessonInjector()
    result = injector.get_lessons_for_phase("red")
    assert "anti-pattern" in result.lower()


def test_get_lessons_for_green_phase_returns_formatted_string():
    injector = TDDLessonInjector()
    result = injector.get_lessons_for_phase("green")
    assert "GREEN PHASE" in result


def test_get_lessons_for_planning_phase_returns_formatted_string():
    injector = TDDLessonInjector()
    result = injector.get_lessons_for_phase("planning")
    assert "PLANNING PHASE" in result


def test_format_includes_known_tdd_lessons():
    injector = TDDLessonInjector()
    result = injector.get_lessons_for_phase("red")

    # Verify structured lesson format with unique identifiers and metadata
    # Current implementation only provides flat text without lesson IDs
    lines = result.split("\n")

    lesson_entries = [line for line in lines if line.startswith("- **")]
    assert len(lesson_entries) >= 3, (
        f"Expected at least 3 structured lessons, found {len(lesson_entries)}"
    )

    for entry in lesson_entries:
        # Each lesson should have ID and category metadata in format:
        # - **[LESSON-XXX] Title**: Description [category]
        assert "[LESSON-" in entry, f"Missing lesson ID in: {entry}"
        assert entry.count("[") >= 2, f"Missing category tag in: {entry}"
        assert "]: " in entry, f"Missing title separator in: {entry}"

    # Verify phase tag appears in each lesson
    phase_tagged_lessons = [line for line in lines if "[red]" in line.lower()]
    assert len(phase_tagged_lessons) == len(lesson_entries), (
        f"All red phase lessons must have [red] tag, expected {len(lesson_entries)} got {len(phase_tagged_lessons)}"
    )
