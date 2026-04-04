#!/usr/bin/env python3
"""
ACE CLI - Command-line interface for ACE Enterprise

Usage:
    ace init                    # Initialize ACE in current project
    ace build-feature <file>    # Build feature from Gherkin file
    ace status                  # Show ACE status for current project
"""

import sys
import logging
from pathlib import Path
import argparse

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.project.detector import ProjectDetector
from src.project.config import ProjectConfig, ACEConfig
from src.project.decision_record import generate_adr_from_tdd_result
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.playbook.postgres_retriever import PostgresBulletRetriever
from src.storage.schemas import PlaybookCreate
from src.agents.test_review_agent import TestReviewAgent
from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.ensemble.learner import EnsembleLearner
from src.utils.llm_client import LLMClient
from src.config.settings import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_init(args):
    """Initialize ACE in current project."""
    print("\n🚀 Initializing ACE Enterprise...\n")

    # Detect project
    detector = ProjectDetector()
    try:
        project_info = detector.detect()
    except ValueError as e:
        print(f"❌ Error: {e}")
        return 1

    print(f"📁 Project detected: {project_info.name}")
    print(f"   Root: {project_info.root}")
    print(f"   Type: {project_info.project_type}")
    print(f"   Source: {project_info.src_dir}")
    print(f"   Tests: {project_info.test_dir}")

    # Check if already initialized
    project_config = ProjectConfig(project_info.root)
    if project_config.exists():
        print(f"\n⚠️  ACE already initialized at: {project_config.ace_dir}")
        print("   Use 'ace status' to see configuration")
        return 0

    # Ask for domain (optional)
    domain = args.domain or input("\n🏷️  Project domain (optional, e.g., 'healthcare', 'fintech'): ").strip()
    domain = domain if domain else None

    # Initialize
    detector.ensure_directories(project_info)
    config = project_config.initialize(
        project_name=project_info.name,
        project_domain=domain
    )

    print(f"\n✅ ACE initialized successfully!")
    print(f"\n📝 Configuration saved to: {project_config.config_file}")
    print(f"   Project: {config.project_name}")
    if config.project_domain:
        print(f"   Domain: {config.project_domain}")
    print(f"   Test framework: {config.test_framework}")
    print(f"   Central knowledge: {'Enabled' if config.use_central_knowledge else 'Disabled'}")

    print(f"\n📂 Directory structure:")
    print(f"   {project_info.ace_dir}/")
    print(f"   ├── config.yml       (ACE configuration)")
    print(f"   ├── decisions/       (Architectural decisions)")
    print(f"   └── README.md        (Documentation)")

    print(f"\n🎯 Next steps:")
    print(f"   1. Create a Gherkin feature file in your project")
    print(f"   2. Run: ace build-feature path/to/feature.feature")
    print(f"   3. Review generated code and tests")
    print(f"   4. Commit to git!")

    return 0


def cmd_build_feature(args):
    """Build feature from Gherkin file."""
    feature_file = Path(args.feature_file)

    if not feature_file.exists():
        print(f"❌ Feature file not found: {feature_file}")
        return 1

    print(f"\n🏗️  Building feature from: {feature_file.name}\n")

    # Detect project
    detector = ProjectDetector()
    try:
        project_info = detector.detect()
    except ValueError as e:
        print(f"❌ Error: {e}")
        return 1

    print(f"📁 Project: {project_info.name}")
    print(f"   Source: {project_info.src_dir}")
    print(f"   Tests: {project_info.test_dir}")

    # Load or create config
    project_config = ProjectConfig(project_info.root)
    if not project_config.exists():
        print(f"\n⚠️  ACE not initialized. Initializing with defaults...")
        detector.ensure_directories(project_info)
        config = project_config.initialize(project_name=project_info.name)
    else:
        config = project_config.load()

    print(f"   Config: {config.test_framework}, TDD cycles: {config.tdd_cycles}")

    # Initialize ACE components with PostgreSQL
    print(f"\n⚙️  Initializing ACE components (PostgreSQL backend)...")

    # PostgreSQL Playbook Adapter
    playbook_adapter = PostgresPlaybookAdapter()

    # Get or create playbook - reuse existing one for same domain
    target_domain = config.project_domain or "general"

    # Find existing playbook for this domain (with bullets preferred)
    existing_playbook = None
    best_bullet_count = -1

    for pb_model in playbook_adapter.repo.list_playbooks():
        if pb_model.domain == target_domain:
            bullet_count = len(playbook_adapter.repo.get_bullets_by_playbook(pb_model.playbook_id))
            # Prefer playbook with most learned bullets
            if bullet_count > best_bullet_count:
                best_bullet_count = bullet_count
                existing_playbook = pb_model

    if existing_playbook:
        playbook = playbook_adapter.get_playbook(existing_playbook.playbook_id)
        print(f"   Using existing playbook: {playbook.playbook_id} ({best_bullet_count} bullets)")
    else:
        playbook_create = PlaybookCreate(
            domain=target_domain,
            base_model=settings.default_model_id
        )
        playbook = playbook_adapter.create_playbook(playbook_create)
        print(f"   Created new playbook: {playbook.playbook_id}")

    # LLM client
    llm_client = LLMClient(
        provider=settings.default_provider,
        model=settings.default_model_id
    )
    print(f"   Initialized LLM client: {settings.default_provider}/{settings.default_model_id}")

    # Test reviewer
    test_reviewer = TestReviewAgent(llm_client=llm_client)

    # EnsembleLearner (required by AutonomousTDDAgent)
    ensemble_learner = EnsembleLearner(
        models=[(settings.default_provider, settings.default_model_id, None)],
        playbook_id=playbook.playbook_id,
    )
    # Override with PostgreSQL playbook manager
    ensemble_learner.playbook_manager = playbook_adapter

    # TDD Agent with PostgreSQL backend
    tdd_agent = AutonomousTDDAgent(
        ensemble_learner=ensemble_learner,
        test_reviewer=test_reviewer,
        project_root=project_info.root,
        test_dir=project_info.test_dir,
        src_dir=project_info.src_dir,
        max_iterations=20,
    )

    # Override with PostgreSQL bullet retriever
    tdd_agent.bullet_retriever = PostgresBulletRetriever(
        playbook_adapter=playbook_adapter,
        top_k=10,
        similarity_threshold=0.3
    )

    print(f"✅ Components initialized (PostgreSQL backend)")

    # Build feature
    print(f"\n🔨 Starting Gherkin-driven TDD...")
    print(f"=" * 80)

    try:
        # Create temporary gherkin directory with just this feature
        import tempfile
        import shutil
        temp_gherkin_dir = Path(tempfile.mkdtemp(prefix="ace_gherkin_"))
        shutil.copy(feature_file, temp_gherkin_dir / feature_file.name)

        # Read gherkin content as requirement
        gherkin_content = feature_file.read_text()
        requirement = f"Implement the following Gherkin feature:\n\n{gherkin_content}"

        # Build feature - output to project directories
        tdd_agent.build_feature(
            requirement=requirement,
            gherkin_dir=temp_gherkin_dir,
        )

        # Clean up temp directory
        shutil.rmtree(temp_gherkin_dir)

        print(f"\n" + "=" * 80)
        print(f"✅ Feature built successfully!")

        # Generate decision record
        print(f"\n📝 Generating decision record...")
        try:
            # Read gherkin content
            gherkin_content = feature_file.read_text() if feature_file.exists() else None

            # Extract test names from playbook (simplified)
            test_names = [f"test_{feature_file.stem}"]

            # Get patterns learned from playbook
            patterns_learned = []
            if playbook and hasattr(playbook, 'sections') and playbook.sections:
                if playbook.sections.get("strategies_and_hard_rules"):
                    patterns_learned = [
                        bullet["content"]
                        for bullet in playbook.sections["strategies_and_hard_rules"][-3:]  # Last 3
                    ]

            # Generate ADR
            adr = generate_adr_from_tdd_result(
                feature_name=feature_file.stem.replace('_', ' ').title(),
                gherkin_content=gherkin_content,
                files_created=[
                    str(project_info.src_dir / f"{feature_file.stem}.py"),
                    str(project_info.test_dir / f"test_{feature_file.stem}.py")
                ],
                tests_generated=test_names,
                patterns_learned=patterns_learned,
                human_contributor=config.contributors[0] if config.contributors else None,
                ai_models=[settings.default_model_id]
            )

            # Save ADR
            adr_file = adr.save(project_info.ace_dir / "decisions")
            print(f"   Saved ADR: {adr_file.name}")
        except Exception as e:
            logger.warning(f"Failed to generate ADR: {e}")
            print(f"   ⚠️  Warning: Could not generate ADR")

        print(f"\n📂 Generated files:")
        print(f"   Source: {project_info.src_dir}")
        print(f"   Tests: {project_info.test_dir}")
        print(f"   Decisions: {project_info.ace_dir / 'decisions'}")

        if project_info.has_git:
            print(f"\n📝 Git status:")
            import subprocess
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=project_info.root,
                capture_output=True,
                text=True
            )
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    print(f"   {line}")

            print(f"\n💡 Next steps:")
            print(f"   1. Review generated code: git diff")
            print(f"   2. Run tests: pytest")
            print(f"   3. Stage changes: git add .")
            print(f"   4. Commit: git commit -m 'Add {feature_file.stem} feature'")
        else:
            print(f"\n💡 Next steps:")
            print(f"   1. Review generated code")
            print(f"   2. Run tests: pytest")

        return 0

    except Exception as e:
        print(f"\n❌ Error building feature: {e}")
        logger.exception("Build failed")
        return 1


def cmd_status(args):
    """Show ACE status for current project."""
    print("\n📊 ACE Enterprise Status\n")

    # Detect project
    detector = ProjectDetector()
    try:
        project_info = detector.detect()
    except ValueError as e:
        print(f"❌ Error: {e}")
        return 1

    print(f"📁 Project: {project_info.name}")
    print(f"   Root: {project_info.root}")
    print(f"   Type: {project_info.project_type}")
    print(f"   Source: {project_info.src_dir}")
    print(f"   Tests: {project_info.test_dir}")
    if project_info.has_git:
        print(f"   Git: ✅ Initialized")
    else:
        print(f"   Git: ❌ Not initialized")

    # Check ACE configuration
    project_config = ProjectConfig(project_info.root)
    if not project_config.exists():
        print(f"\n⚠️  ACE not initialized in this project")
        print(f"   Run 'ace init' to get started")
        return 0

    config = project_config.load()

    print(f"\n⚙️  ACE Configuration:")
    print(f"   Config file: {project_config.config_file}")
    if config.project_domain:
        print(f"   Domain: {config.project_domain}")
    print(f"   Test framework: {config.test_framework}")
    print(f"   Code style: {config.code_style}")
    print(f"   Type hints: {'✅' if config.type_hints else '❌'}")
    print(f"   Docstrings: {'✅' if config.docstrings else '❌'}")
    print(f"   TDD cycles: {config.tdd_cycles}")
    print(f"   Central knowledge: {'✅ Enabled' if config.use_central_knowledge else '❌ Disabled'}")

    if config.playbooks:
        print(f"   Playbooks: {', '.join(config.playbooks)}")

    # Check decisions
    decisions_dir = project_info.ace_dir / "decisions"
    if decisions_dir.exists():
        decision_files = list(decisions_dir.glob("*.md"))
        print(f"\n📝 Decisions: {len(decision_files)} ADRs")
        if decision_files:
            print(f"   Latest: {decision_files[-1].name}")

    print(f"\n✅ ACE is ready! Run 'ace build-feature <file>' to start building.")

    return 0


def cmd_learn(args):
    """Add knowledge to playbook manually."""
    from src.storage.schemas import BulletCreate
    from src.playbook.postgres_adapter import PostgresPlaybookAdapter

    print("\n🧠 Adding knowledge to playbook...\n")

    # Initialize PostgreSQL adapter
    try:
        adapter = PostgresPlaybookAdapter()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        print(f"❌ Database connection failed. Is PostgreSQL running?")
        print(f"   Error: {e}")
        return 1

    # Determine playbook ID
    playbook_id = args.playbook
    if not playbook_id:
        # Try to find project-specific playbook
        detector = ProjectDetector()
        try:
            project_info = detector.detect()
            playbook_id = f"{project_info.name.lower().replace('-', '_')}_playbook"
        except ValueError:
            playbook_id = "ace_enterprise_playbook"

    # Check if playbook exists, create if not
    existing_playbooks = adapter.list_playbooks()
    if playbook_id not in existing_playbooks:
        print(f"   Creating new playbook: {playbook_id}")
        from src.storage.schemas import PlaybookCreate
        adapter.create_playbook(PlaybookCreate(
            domain=args.domain or "general",
            base_model="human"
        ))

    # Map knowledge type to section
    section_map = {
        "decision": "strategies_and_hard_rules",
        "pattern": "strategies_and_hard_rules",
        "snippet": "code_snippets",
        "troubleshooting": "troubleshooting",
        "domain": "domain_knowledge",
    }
    section = section_map.get(args.type, "domain_knowledge")

    # Parse tags
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # Add type as a tag for easier filtering
    if args.type and args.type not in tags:
        tags.append(args.type)

    # Create bullet
    bullet_data = BulletCreate(
        content=args.content,
        section=section,
        tags=tags,
        created_by_model="human",
        model_provider=None,
        license_type=None,
    )

    try:
        bullet = adapter.add_bullet(playbook_id, bullet_data)

        print(f"✅ Knowledge added successfully!")
        print(f"   Playbook: {playbook_id}")
        print(f"   Section: {section}")
        print(f"   ID: {bullet.id}")
        if tags:
            print(f"   Tags: {', '.join(tags)}")
        print(f"\n📝 Content preview:")
        preview = args.content[:200] + "..." if len(args.content) > 200 else args.content
        print(f"   {preview}")

        return 0

    except Exception as e:
        logger.error(f"Failed to add bullet: {e}")
        print(f"❌ Failed to add knowledge: {e}")
        return 1


def cmd_query(args):
    """Query knowledge from playbook."""
    from src.playbook.postgres_adapter import PostgresPlaybookAdapter
    from src.playbook.postgres_retriever import PostgresBulletRetriever

    print(f"\n🔍 Querying playbook for: \"{args.query}\"\n")

    # Initialize adapter and retriever
    try:
        adapter = PostgresPlaybookAdapter()
        retriever = PostgresBulletRetriever(
            playbook_adapter=adapter,
            top_k=args.top_k,
            similarity_threshold=0.3
        )
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        print(f"❌ Database connection failed: {e}")
        return 1

    # Determine playbook ID
    playbook_id = args.playbook
    if not playbook_id:
        detector = ProjectDetector()
        try:
            project_info = detector.detect()
            playbook_id = f"{project_info.name.lower().replace('-', '_')}_playbook"
        except ValueError:
            playbook_id = "ace_enterprise_playbook"

    # Retrieve relevant bullets
    try:
        results = retriever.retrieve(
            query=args.query,
            playbook_id=playbook_id,
            filter_section=args.section,
        )

        if not results:
            print("   No matching knowledge found.")
            return 0

        print(f"Found {len(results)} relevant entries:\n")

        for i, (bullet, score) in enumerate(results, 1):
            print(f"{'─' * 60}")
            print(f"[{i}] Score: {score:.2f} | Section: {bullet.section}")
            if bullet.tags:
                print(f"    Tags: {', '.join(bullet.tags)}")
            print(f"    ID: {bullet.id}")
            print(f"\n    {bullet.content}\n")

        return 0

    except Exception as e:
        logger.error(f"Query failed: {e}")
        print(f"❌ Query failed: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ACE Enterprise - Institutional Knowledge Development Middleware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ace init                          # Initialize ACE in current project
  ace build-feature auth.feature    # Build auth feature from Gherkin
  ace status                        # Show current project status

  # Add knowledge manually
  ace learn "Pattern description" --type decision --tags "architecture,design"
  ace learn "When testing async endpoints, mock at dependency level" --type pattern

  # Query knowledge
  ace query "auth timeout handling" --top-k 3
  ace query "testing patterns" --section strategies_and_hard_rules

Documentation: https://github.com/carlhuxley/ace_enterprise
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Init command
    parser_init = subparsers.add_parser('init', help='Initialize ACE in current project')
    parser_init.add_argument('--domain', help='Project domain (e.g., healthcare, fintech)')
    parser_init.set_defaults(func=cmd_init)

    # Build-feature command
    parser_build = subparsers.add_parser('build-feature', help='Build feature from Gherkin file')
    parser_build.add_argument('feature_file', help='Path to Gherkin feature file')
    parser_build.set_defaults(func=cmd_build_feature)

    # Status command
    parser_status = subparsers.add_parser('status', help='Show ACE status for current project')
    parser_status.set_defaults(func=cmd_status)

    # Learn command
    parser_learn = subparsers.add_parser('learn', help='Add knowledge to playbook manually')
    parser_learn.add_argument('content', help='Knowledge content to add')
    parser_learn.add_argument(
        '--type', '-t',
        choices=['decision', 'pattern', 'snippet', 'troubleshooting', 'domain'],
        default='decision',
        help='Type of knowledge (default: decision)'
    )
    parser_learn.add_argument(
        '--tags',
        help='Comma-separated tags (e.g., "architecture,cgr3,retrieval")'
    )
    parser_learn.add_argument(
        '--playbook',
        help='Target playbook ID (default: auto-detect from project)'
    )
    parser_learn.add_argument(
        '--domain',
        help='Domain for new playbook if created (e.g., "fintech")'
    )
    parser_learn.set_defaults(func=cmd_learn)

    # Query command
    parser_query = subparsers.add_parser('query', help='Query knowledge from playbook')
    parser_query.add_argument('query', help='Search query')
    parser_query.add_argument(
        '--top-k', '-k',
        type=int,
        default=5,
        help='Number of results to return (default: 5)'
    )
    parser_query.add_argument(
        '--section', '-s',
        choices=['strategies_and_hard_rules', 'code_snippets', 'troubleshooting', 'domain_knowledge'],
        help='Filter by section'
    )
    parser_query.add_argument(
        '--playbook',
        help='Target playbook ID (default: auto-detect from project)'
    )
    parser_query.set_defaults(func=cmd_query)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
