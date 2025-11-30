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
from src.playbook.manager import PlaybookManager
from src.storage.schemas import PlaybookCreate
from src.agents.test_review_agent import TestReviewAgent
from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
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

    # Initialize ACE components
    print(f"\n⚙️  Initializing ACE components...")

    # Playbook manager
    playbook_manager = PlaybookManager(settings.storage_dir)

    # Get or create playbook
    playbook_name = f"{project_info.name.lower().replace('-', '_')}_playbook"
    existing_playbooks = [pb for pb in playbook_manager.list_playbooks()
                          if project_info.name.lower() in pb['playbook_id'].lower()]

    if existing_playbooks:
        playbook = playbook_manager.get_playbook(existing_playbooks[0]['playbook_id'])
        print(f"   Using existing playbook: {playbook.playbook_id}")
    else:
        playbook_create = PlaybookCreate(
            domain=config.project_domain or "general",
            base_model=settings.default_model_id
        )
        playbook = playbook_manager.create_playbook(playbook_create)
        print(f"   Created new playbook: {playbook.playbook_id}")

    # LLM client
    llm_client = LLMClient(
        provider=settings.default_provider,
        model=settings.default_model_id
    )

    # Test reviewer
    test_reviewer = TestReviewAgent(llm_client=llm_client)

    # TDD Agent
    tdd_agent = AutonomousTDDAgent(
        playbook=playbook,
        llm_client=llm_client,
        test_reviewer=test_reviewer,
        playbook_manager=playbook_manager
    )

    print(f"✅ Components initialized")

    # Build feature
    print(f"\n🔨 Starting Gherkin-driven TDD...")
    print(f"=" * 80)

    try:
        # Create temporary gherkin directory with just this feature
        import tempfile
        import shutil
        temp_gherkin_dir = Path(tempfile.mkdtemp(prefix="ace_gherkin_"))
        shutil.copy(feature_file, temp_gherkin_dir / feature_file.name)

        # Build feature - output to project directories
        tdd_agent.build_feature(
            gherkin_dir=temp_gherkin_dir,
            project_root=project_info.root,  # Use real project root
            source_dir=project_info.src_dir,  # Use real source dir
            test_dir=project_info.test_dir,   # Use real test dir
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
