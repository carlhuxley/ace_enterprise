"""Step 1 of the ACE pre-launch proof: generate the benchmark task set.

Exports the curated task bank (benchmarks/tasks.py) -- 30 tricky coding
tasks split evenly across three domains (numeric edge cases, security/linter
boundaries, concurrency boundaries) -- to a JSONL file that benchmarks.runner
consumes. This step itself is deterministic and LLM-free (a fixed selection
over an already-written bank); see benchmarks/tasks.py's module docstring for
the provenance of the tasks and pytest oracles themselves (LLM-authored,
then hand-audited against paired canonical/buggy reference implementations)
-- that audit, not the origin of the tests, is what makes the ground truth
here trustworthy.

Usage:
    .venv/bin/python -m benchmarks.generator
    .venv/bin/python -m benchmarks.generator --count 15 --domain numeric_edge_cases
    .venv/bin/python -m benchmarks.generator --out benchmarks/generated_tasks.jsonl --seed 7
"""
import argparse
import json
import random
import sys
from pathlib import Path

from benchmarks.tasks import ALL_TASKS, Domain, get_tasks

DEFAULT_OUTPUT = Path(__file__).parent / "generated_tasks.jsonl"


def generate_tasks(
    count: int | None = None,
    domain: Domain | None = None,
    seed: int | None = None,
) -> list[dict]:
    """Select up to `count` tasks (default: all of them), optionally filtered
    to one domain and shuffled with `seed` for reproducible sampling."""
    pool = get_tasks(domain)
    if seed is not None:
        rng = random.Random(seed)
        pool = pool[:]
        rng.shuffle(pool)
    if count is not None:
        pool = pool[:count]
    return [t.to_dict() for t in pool]


def write_tasks(tasks: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=None,
        help=f"Number of tasks to emit (default: all {len(ALL_TASKS)})",
    )
    parser.add_argument(
        "--domain", choices=["numeric_edge_cases", "security_boundaries", "concurrency_boundaries"],
        default=None, help="Restrict to a single domain (default: all three)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Shuffle seed for sampling a subset")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Output JSONL path")
    args = parser.parse_args(argv)

    tasks = generate_tasks(count=args.count, domain=args.domain, seed=args.seed)
    write_tasks(tasks, args.out)

    by_domain: dict[str, int] = {}
    for t in tasks:
        by_domain[t["domain"]] = by_domain.get(t["domain"], 0) + 1

    print(f"Wrote {len(tasks)} tasks to {args.out}")
    for domain, n in sorted(by_domain.items()):
        print(f"  {domain}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
