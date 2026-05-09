"""ace — CLI entry point for ACE Enterprise."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace",
        description="ACE Enterprise — agentic TDD for your projects",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ace tdd
    tdd = sub.add_parser("tdd", help="Build a feature using TDD from a .feature file")
    tdd.add_argument(
        "--project",
        type=Path,
        default=Path("."),
        help="Path to the target project (default: current directory)",
    )
    tdd.add_argument(
        "--feature",
        type=Path,
        default=None,
        help="Path to a .feature file (auto-discovered if omitted)",
    )
    tdd.add_argument(
        "--requirement",
        default=None,
        help="Feature requirement text (extracted from feature file if omitted)",
    )
    tdd.add_argument(
        "--playbook-id",
        default=None,
        help="Playbook ID override (default: project directory name)",
    )
    tdd.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum TDD cycles (default from config or 20)",
    )
    tdd.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def cmd_tdd(args: argparse.Namespace) -> int:
    from src.cli.config import ProjectConfig
    from src.cli.factory import build_agent

    project_root = args.project.resolve()
    if not project_root.is_dir():
        print(f"error: project directory not found: {project_root}", file=sys.stderr)
        return 1

    config = ProjectConfig.load(project_root)

    if args.playbook_id:
        config.playbook_id = args.playbook_id
    if args.max_iterations:
        config.max_iterations = args.max_iterations

    # Resolve feature file
    feature_path: Path | None = args.feature
    if feature_path is None:
        candidates = config.discover_features()
        if not candidates:
            print(
                "error: no .feature files found. "
                "Put them in <project>/features/ or pass --feature",
                file=sys.stderr,
            )
            return 1
        if len(candidates) > 1:
            print("Found multiple feature files — building all in sequence:")
            for f in candidates:
                print(f"  {f.relative_to(project_root)}")
        feature_path = candidates[0]
    else:
        feature_path = feature_path.resolve()
        if not feature_path.exists():
            print(f"error: feature file not found: {feature_path}", file=sys.stderr)
            return 1

    # Derive requirement from feature file if not given
    requirement = args.requirement
    if requirement is None:
        requirement = _extract_requirement(feature_path)

    gherkin_dir = feature_path.parent

    print(f"Project:    {project_root}")
    print(f"Feature:    {feature_path.relative_to(project_root)}")
    print(f"Playbook:   {config.playbook_id} ({config.playbook_scope})")
    print(f"Tests →     {config.test_dir.relative_to(project_root)}")
    print(f"Source →    {config.src_dir.relative_to(project_root)}")
    print()

    agent = build_agent(config)
    result = agent.build_feature(requirement=requirement, gherkin_dir=gherkin_dir)

    print()
    print(f"Done — {len(result.test_files)} test file(s), {len(result.implementation_files)} implementation file(s)")
    return 0


def _extract_requirement(feature_file: Path) -> str:
    """Pull the Feature: line from a .feature file as the requirement string."""
    for line in feature_file.read_text().splitlines():
        line = line.strip()
        if line.lower().startswith("feature:"):
            return line[len("feature:"):].strip()
    return feature_file.stem.replace("_", " ").replace("-", " ")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    handlers = {"tdd": cmd_tdd}
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
