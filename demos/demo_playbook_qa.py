#!/usr/bin/env python3
"""
Playbook Q&A Demo - Answer coding questions using learned knowledge.

Shows how to:
1. Ask questions and get answers backed by playbook
2. See which bullets were used as sources
3. Get ensemble consensus from multiple models
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from src.playbook.manager import PlaybookManager
from src.playbook.qa import PlaybookQA

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_answer(answer, show_sources: bool = True):
    """Print formatted answer."""
    print(f"\n📝 Question: {answer.question}")
    print(f"\n💡 Answer:")
    print(f"{answer.answer}")

    print(f"\n📊 Metadata:")
    print(f"   Confidence: {answer.confidence:.0%}")
    print(f"   Playbook Coverage: {answer.playbook_coverage:.0%}")
    print(f"   Model: {answer.model_id or 'Ensemble'}")

    if show_sources and answer.sources:
        print(f"\n📚 Sources from Playbook ({len(answer.sources)} bullets used):")
        for i, bullet in enumerate(answer.sources[:3], 1):  # Show top 3
            helpful = f" (👍 {bullet.helpful_count})" if bullet.helpful_count > 0 else ""
            print(f"   {i}. [{bullet.section}] {bullet.content[:80]}...{helpful}")
        if len(answer.sources) > 3:
            print(f"   ... and {len(answer.sources) - 3} more")
    elif show_sources:
        print(f"\n⚠️  No playbook knowledge found for this question")
        print(f"   Answer is from LLM general knowledge only")

    if answer.consensus:
        print(f"\n🤝 Ensemble Consensus:")
        print(f"   Models: {', '.join(answer.consensus['models'])}")
        print(f"   Agreement: {answer.consensus['agreement']:.0%}")
        print(f"   Selected: {answer.consensus['selected']}")


def main():
    print_section("PLAYBOOK Q&A SYSTEM DEMO")

    print("\nThis demo shows how to ask coding questions and get answers")
    print("backed by learned knowledge from your playbooks.")

    # Initialize
    print("\n✓ Loading playbooks...")
    pm = PlaybookManager()

    # Count bullets
    total_bullets = sum(
        pb.metadata.total_bullets
        for pb in pm._playbooks.values()
    )
    print(f"✓ Loaded {len(pm._playbooks)} playbooks with {total_bullets} bullets")

    # Create Q&A system
    print("\n✓ Initializing Q&A system...")
    qa = PlaybookQA(playbook_manager=pm)

    # Example questions
    questions = [
        "How should I validate email addresses in Python?",
        "What's the best way to handle file paths for cross-platform compatibility?",
        "How do I write good unit tests?",
    ]

    print_section("SINGLE MODEL Q&A")
    print("\nAsking questions using a single model with playbook context...")

    for question in questions[:2]:  # Ask first 2 questions
        print("\n" + "-" * 80)
        answer = qa.ask(question, domain="python_development")
        print_answer(answer)

    print_section("ENSEMBLE CONSENSUS Q&A")
    print("\nAsking a question to multiple models and getting consensus...")

    models = [
        ("ollama", "qwen2.5-coder:1.5b"),
        ("ollama", "qwen2.5-coder:0.5b"),
        ("ollama", "deepseek-coder:1.3b"),
    ]

    print(f"\nUsing {len(models)} models:")
    for provider, model in models:
        print(f"  • {provider}/{model}")

    print("\n" + "-" * 80)
    answer = qa.ask_ensemble(
        questions[2],  # Ask third question
        models=models,
        domain="python_development"
    )
    print_answer(answer, show_sources=True)

    # Interactive mode
    print_section("INTERACTIVE MODE")
    print("\nNow you can ask your own questions!")
    print("(Type 'quit' or press Ctrl+C to exit)")

    while True:
        try:
            print("\n" + "-" * 80)
            question = input("\n❓ Your question: ").strip()

            if not question:
                continue

            if question.lower() in ('quit', 'exit', 'q'):
                print("\n👋 Goodbye!")
                break

            # Ask with single model (faster)
            answer = qa.ask(question, domain="python_development")
            print_answer(answer)

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
