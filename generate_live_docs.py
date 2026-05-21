#!/usr/bin/env python3
"""
Regenerates docs/SYSTEM_ARCHITECTURE.md from the live source tree.
Run: python generate_live_docs.py
"""
import ast
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

# Core files read in full — these define the main data flow
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

OUTPUT = ROOT / "docs" / "SYSTEM_ARCHITECTURE.md"
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
    """Return a compact structural summary using AST: classes, methods, top-level functions."""
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
You are a technical documentarian generating machine-readable architecture documentation.
Output EXACTLY two sections with NO preamble, no explanation, no extra text:

SECTION 1 — a markdown table:
| Component | Module | Role |
|-----------|--------|------|
Include ONLY classes with meaningful behaviour (orchestrators, agents, runners, managers, clients,
analyzers, routers, stores). EXCLUDE pure data containers: @dataclass types, result/metrics/config
structs, Pydantic schemas, SQLAlchemy models, and enums. Aim for 20-35 rows maximum.

SECTION 2 — a fenced Mermaid sequence diagram showing the core data flow:
```mermaid
sequenceDiagram
    ...
```

STRICT MERMAID RULES — violating any of these produces a parse error in GitHub:
- Use ONLY these block types: alt/else/end, opt/end, loop/end, Note
- NEVER use: break, par, par_over, critical, rect — they are unsupported or context-restricted
- `break` is NOT a keyword inside alt/opt/loop — use `Note right of X: exits if ...` instead
- `else` is ONLY valid as part of `alt ... else ... end`, never standalone
- Every `activate` must have a matching `deactivate`
- Participant aliases must not contain spaces or special characters

Start immediately with the table header. Nothing before it. Nothing after the closing fence."""


def _strip_outer_fence(content: str) -> str:
    """Remove accidental outer markdown fence the model occasionally wraps its entire response in."""
    if content.startswith("```") and content.endswith("```"):
        content = "\n".join(content.splitlines()[1:-1]).strip()
    return content


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from src.utils.llm_client import LLMClient  # noqa: PLC0415

    print("Scanning source tree...")
    context = build_context()
    print(f"  {len(context):,} chars of source context")

    prompt = (
        "Review this Python codebase and produce the two architecture sections.\n\n"
        f"SOURCE CODE:\n{context}"
    )

    print(f"Calling {PROVIDER}/{MODEL}...")
    client = LLMClient(provider=PROVIDER, model=MODEL)
    result = client.generate(prompt, system_prompt=SYSTEM_PROMPT, temperature=0, max_tokens=8192)

    content = _strip_outer_fence(result["content"].strip())
    tokens = result.get("tokens_used", "?")

    header = (
        f"<!-- Generated by generate_live_docs.py on {datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"— do not edit by hand -->\n\n"
        f"# System Architecture\n\n"
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(header + content + "\n")

    print(f"Wrote {OUTPUT.relative_to(ROOT)}  ({len(content):,} chars, {tokens} tokens used)")


if __name__ == "__main__":
    main()
