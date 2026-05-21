#!/usr/bin/env python3
"""
Updates CONTEXT.md from the live source tree.
Preserves existing domain definitions; adds new concepts and updates
the Architectural Decisions section based on what's in the code.
Run: python generate_live_context.py
"""
import ast
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

CORE_FILES = [
    "run_cycle.py",
    "src/agents/tdd_cycle_runner.py",
    "src/agents/python_language_pod.py",
    "src/agents/worker_agent.py",
    "src/agents/language_pod.py",
    "src/playbook/manager.py",
    "src/storage/experiment_logger.py",
    "src/core/reflector/module.py",
    "src/core/curator/module.py",
    "src/core/generator/module.py",
]

OUTPUT = ROOT / "CONTEXT.md"
MODEL = "deepseek/deepseek-v4-flash"
PROVIDER = "openrouter"


def _first_line(text: str, limit: int, fallback: str = "") -> str:
    lines = text.splitlines()
    return lines[0][:limit] if lines else fallback


def _sig(args_node: ast.arguments, skip_self: bool = True) -> str:
    parts = []
    for a in args_node.args:
        if skip_self and a.arg == "self":
            continue
        parts.append(a.arg)
    if args_node.vararg:
        parts.append(f"*{args_node.vararg.arg}")
    for a in args_node.kwonlyargs:
        parts.append(a.arg)
    if args_node.kwarg:
        parts.append(f"**{args_node.kwarg.arg}")
    return ", ".join(parts)


def extract_signatures(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, OSError):
        return ""

    out = [f"### {path.relative_to(ROOT)}"]
    mod_doc = ast.get_docstring(tree) or ""
    if mod_doc:
        out.append(f'"""{_first_line(mod_doc, 140)}"""')

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            doc = _first_line(ast.get_docstring(node) or "", 120, "No description provided.")
            out.append(f"\nclass {node.name}:  # {doc}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fdoc = _first_line(ast.get_docstring(item) or "", 80, "No description provided.")
                    out.append(f"    def {item.name}({_sig(item.args)})  # {fdoc}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _first_line(ast.get_docstring(node) or "", 80, "No description provided.")
            out.append(f"\ndef {node.name}({_sig(node.args, skip_self=False)})  # {doc}")

    return "\n".join(out)


def build_context() -> str:
    sections = []

    core_paths = set()
    for rel in CORE_FILES:
        p = ROOT / rel
        if p.exists():
            core_paths.add(p.resolve())
            sections.append(f"=== FULL SOURCE: {rel} ===\n{p.read_text()}")

    all_py = sorted(ROOT.glob("src/**/*.py"))
    others = [
        p for p in all_py
        if p.resolve() not in core_paths
        and "__pycache__" not in str(p)
        and p.name != "__init__.py"
    ]
    summaries = [s for p in others if (s := extract_signatures(p))]
    if summaries:
        sections.append("=== MODULE SUMMARIES (non-core files) ===\n" + "\n\n".join(summaries))

    return "\n\n".join(sections)


SYSTEM_PROMPT = """\
You are a domain knowledge curator maintaining a living codebase glossary.

You will be given:
1. The current CONTEXT.md
2. The full source code of the project

Your task is to produce an updated CONTEXT.md that:
- PRESERVES all existing domain definitions exactly unless the code directly contradicts them
- ADDS any domain concepts present in the code that are missing from the current document
- UPDATES the Architectural Decisions section to reflect decisions visible in the source
- Keeps the same format, heading structure, and concise prose style
- Does NOT add padding, preamble, or any text outside the document

Output the complete updated CONTEXT.md only. Start directly with the # heading. Nothing else."""


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from src.utils.llm_client import LLMClient  # noqa: PLC0415

    current = OUTPUT.read_text() if OUTPUT.exists() else ""

    print("Scanning source tree...")
    source_context = build_context()
    print(f"  {len(source_context):,} chars of source context")

    prompt = (
        f"CURRENT CONTEXT.md:\n{current}\n\n"
        f"SOURCE CODE:\n{source_context}"
    )

    print(f"Calling {PROVIDER}/{MODEL}...")
    client = LLMClient(provider=PROVIDER, model=MODEL)
    result = client.generate(prompt, system_prompt=SYSTEM_PROMPT, temperature=0, max_tokens=8192)

    content = result["content"].strip()
    tokens = result.get("tokens_used", "?")

    # Strip accidental outer fence
    if content.startswith("```") and content.endswith("```"):
        content = "\n".join(content.splitlines()[1:-1]).strip()

    OUTPUT.write_text(content + "\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}  ({len(content):,} chars, {tokens} tokens used)")


if __name__ == "__main__":
    main()
