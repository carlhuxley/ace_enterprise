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
        "--model",
        default=None,
        metavar="PROVIDER/MODEL",
        help=(
            "Override the LLM for this run, e.g. 'openrouter/qwen/qwen3-coder', "
            "'ollama/qwen3-coder:30b', or 'claude-cli' / 'claude-cli/haiku' for the "
            "local Claude Code session (no API key; ~2.5s/call subprocess cost). "
            "Beats .ace/config.yaml candidate_models and the .env default."
        ),
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
        "--no-learn",
        action="store_true",
        help="Skip the LEARN phase (faster, no playbook updates)",
    )
    tdd.add_argument(
        "--keep-going",
        action="store_true",
        help="When building multiple features, don't stop at the first failure",
    )
    tdd.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    # ace project
    proj = sub.add_parser(
        "project",
        help="Decompose a spec into modules and build them in dependency order",
    )
    proj.add_argument("spec", type=Path, help="Path to the project spec file (free text)")
    proj.add_argument(
        "--project", type=Path, default=Path("."),
        help="Target project directory (default: current directory)",
    )
    proj.add_argument(
        "--model", default=None, metavar="PROVIDER/MODEL",
        help=(
            "Override the LLM, e.g. 'openrouter/qwen/qwen3-coder', or 'claude-cli' / "
            "'claude-cli/haiku' for the local Claude Code session (default: .env)"
        ),
    )
    proj.add_argument(
        "--playbook-id",
        default=None,
        help="Playbook to read prior lessons from and write new ones to "
             "(default: project directory name)",
    )
    proj.add_argument(
        "--no-learn",
        action="store_true",
        help="Skip the LEARN phase — no Reflector/Curator, no playbook writes",
    )
    proj.add_argument(
        "--plan-only", action="store_true",
        help="Print the module plan and exit without building",
    )
    proj.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the 'build these modules?' confirmation prompt",
    )
    proj.add_argument(
        "--resume", action="store_true",
        help="Skip modules whose files already exist",
    )
    proj.add_argument(
        "--keep-going", action="store_true",
        help="Don't stop the build at the first module failure",
    )
    proj.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    return parser


def cmd_tdd(args: argparse.Namespace) -> int:
    from src.cli.config import ProjectConfig

    project_root = args.project.resolve()
    if not project_root.is_dir():
        print(f"error: project directory not found: {project_root}", file=sys.stderr)
        return 1

    config = ProjectConfig.load(project_root)

    if args.playbook_id:
        config.playbook_id = args.playbook_id
    if args.max_iterations:
        config.max_iterations = args.max_iterations

    if args.model and not _valid_model_ref(args.model):
        return 1

    features = _resolve_features(args, project_root, config)
    if features is None:
        return 1

    print(f"Project:    {project_root}")
    print(f"Playbook:   {config.playbook_id} ({config.playbook_scope})")
    print(f"Tests →     {config.test_dir.relative_to(project_root)}")
    print(f"Source →    {config.src_dir.relative_to(project_root)}")
    if args.model:
        print(f"Model:      {args.model} (--model override)")
    if len(features) > 1:
        print(f"Features:   {len(features)} — build order: "
              f"{', '.join(f.stem for f in features)}")
    else:
        print(f"Feature:    {features[0].relative_to(project_root)}")
    print()

    base_playbook = config.playbook_id
    multi = len(features) > 1
    outcomes: list[tuple[str, bool, int]] = []

    for i, feature_path in enumerate(features, 1):
        if multi:
            print(f"── [{i}/{len(features)}] {feature_path.relative_to(project_root)} ──")
            # Per-feature playbook so learned bullets are scoped to the module.
            config.playbook_id = f"{base_playbook}_{feature_path.stem}"

        ok, iterations = _build_feature(
            config, feature_path,
            # A one-off --requirement override only makes sense for a single build.
            requirement=args.requirement if not multi else None,
            skip_learn=args.no_learn,
            model_ref=args.model,
        )
        outcomes.append((feature_path.stem, ok, iterations))

        if not ok and multi and not args.keep_going:
            print(f"\nstopping: {feature_path.stem} failed "
                  "(use --keep-going to build the rest anyway)", file=sys.stderr)
            break

    if multi:
        print("\nSummary:")
        for stem, ok, iters in outcomes:
            print(f"  {'✓' if ok else '✗'} {stem}  ({iters} cycle(s))")

    built_all = len(outcomes) == len(features)
    return 0 if built_all and all(ok for _, ok, _ in outcomes) else 1


def _resolve_features(args, project_root: Path, config) -> list[Path] | None:
    """The ordered list of .feature files to build, or None on a fatal error.

    An explicit --feature is always a single build. Otherwise every discovered
    feature is built, in dependency order (see _order_features).
    """
    if args.feature is not None:
        feature_path = args.feature
        if not feature_path.is_absolute():
            feature_path = project_root / feature_path
        feature_path = feature_path.resolve()
        if not feature_path.exists():
            print(f"error: feature file not found: {feature_path}", file=sys.stderr)
            return None
        return [feature_path]

    candidates = config.discover_features()
    if not candidates:
        print(
            "error: no .feature files found. "
            "Put them in <project>/features/ or pass --feature",
            file=sys.stderr,
        )
        return None
    return _order_features(candidates)


def _order_features(features: list[Path]) -> list[Path] | None:
    """Order features by their `@depends_on(...)` tags (lexical when none)."""
    from src.agents.gherkin_feature_bridge import parse_depends_on
    from src.utils.topo import DependencyError, topo_order

    by_stem = {f.stem: f for f in features}
    deps = {stem: d for stem, path in by_stem.items() if (d := parse_depends_on(path))}
    if not deps:
        return sorted(features, key=lambda p: p.stem)
    try:
        order = topo_order(sorted(by_stem), deps)
    except DependencyError as exc:
        print(f"error: feature build order — {exc}", file=sys.stderr)
        return None
    return [by_stem[s] for s in order]


def _valid_model_ref(ref: str) -> bool:
    from src.cli.factory import _split_model_ref

    try:
        _split_model_ref(ref)
        return True
    except ValueError as exc:
        print(f"error: --model {exc}", file=sys.stderr)
        return False


def _build_feature(
    config, feature_path: Path, *, requirement: str | None, skip_learn: bool,
    model_ref: str | None = None,
) -> tuple[bool, int]:
    from src.cli.factory import build_agent

    handle = build_agent(config, skip_learn=skip_learn, model_ref=model_ref)
    if handle.routing is not None:
        print(handle.routing.summary_line())
    try:
        # requirement=None lets build_from_feature derive it from the Gherkin
        # file itself (title + scenarios); --requirement overrides that.
        result = handle.build_from_feature(feature_path, requirement=requirement)
    finally:
        handle.stop()

    test_file, impl_file = handle.file_paths_for(feature_path)
    print(f"  {'Done' if result.success else 'Incomplete'} — {result.iterations} cycle(s)")
    print(f"    test:            {test_file}")
    print(f"    implementation:  {impl_file}")
    return result.success, result.iterations


_PROJECT_STATUS_GLYPH = {
    "built": "✓",
    "skipped": "•",
    "failed": "✗",
    "blocked": "–",
}


def cmd_project(args: argparse.Namespace) -> int:
    from src.audit.local_client import LocalAuditClient
    from src.cli.config import ProjectConfig
    from src.cli.factory import default_llm_client, llm_client_from_ref
    from src.cli.project_builder import ProjectBuilder
    from src.contracts.project_architect import ProjectArchitect

    if args.model and not _valid_model_ref(args.model):
        return 1

    spec_path = args.spec if args.spec.is_absolute() else Path.cwd() / args.spec
    spec_path = spec_path.resolve()
    if not spec_path.is_file():
        print(f"error: spec file not found: {spec_path}", file=sys.stderr)
        return 1

    project_root = args.project.resolve()
    if not project_root.is_dir():
        print(f"error: project directory not found: {project_root}", file=sys.stderr)
        return 1
    config = ProjectConfig.load(project_root)
    if args.playbook_id:
        config.playbook_id = args.playbook_id

    llm = llm_client_from_ref(args.model) if args.model else default_llm_client()
    model_id = f"{llm.provider}/{llm.model}" if getattr(llm, "provider", None) else llm.model
    audit = LocalAuditClient()

    architect = ProjectArchitect(llm, audit_client=audit, model_id=model_id)
    plan_result = architect.plan(spec_path.read_text(encoding="utf-8"))
    if not plan_result.success or plan_result.plan is None:
        print(f"error: could not plan the project — {plan_result.error}", file=sys.stderr)
        return 1
    plan = plan_result.plan

    print(f"Project:    {project_root}")
    print(f"Spec:       {spec_path}")
    if not args.no_learn:
        print(f"Playbook:   {config.playbook_id}")
    print()
    print(plan.render())
    print()

    if args.plan_only:
        return 0
    if not args.yes and not _confirm(f"Build these {len(plan.modules)} module(s)?"):
        print("aborted.")
        return 1

    builder = ProjectBuilder(
        llm, audit_client=audit, model_id=model_id,
        playbook_id=config.playbook_id, skip_learn=args.no_learn,
    )
    result = builder.build(
        plan, project_root, config.src_dir, config.test_dir,
        resume=args.resume, stop_on_failure=not args.keep_going,
    )

    print("\nModules:")
    for o in result.outcomes:
        line = f"  {_PROJECT_STATUS_GLYPH.get(o.status.value, '?')} {o.name}  ({o.cycles} cycle(s))"
        if getattr(o, "learned", 0):
            line += f", +{o.learned} bullet(s)"
        if o.error:
            line += f" — {o.error}"
        print(line)

    if result.assembly_passed is not None:
        print(f"\nAssembly suite: {'passed' if result.assembly_passed else 'FAILED'}")
        for failure in result.assembly_failures:
            print(f"  {failure}")

    total_learned = sum(getattr(o, "learned", 0) for o in result.outcomes)
    if total_learned:
        print(f"\nLearned {total_learned} bullet(s) → playbook '{config.playbook_id}'")

    return 0 if result.success else 1


def _confirm(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    handlers = {"tdd": cmd_tdd, "project": cmd_project}
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
