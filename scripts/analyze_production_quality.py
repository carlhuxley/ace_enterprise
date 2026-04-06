#!/usr/bin/env python3
"""
Analyze quality data from production TDD cycles.

Usage:
    python scripts/analyze_production_quality.py --days 7
    python scripts/analyze_production_quality.py --backfill-scores --limit 50
    python scripts/analyze_production_quality.py --export report.json
    python scripts/analyze_production_quality.py --raw-data --limit 20
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.benchmark.production_analyzer import ProductionDataAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze quality data from production TDD cycles"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--backfill-scores",
        action="store_true",
        help="Backfill quality scores using BlindEvaluator"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit for backfill or raw data queries (default: 100)"
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export report to JSON file"
    )
    parser.add_argument(
        "--raw-data",
        action="store_true",
        help="Show raw experiment data"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        analyzer = ProductionDataAnalyzer()

        # Backfill quality scores if requested
        if args.backfill_scores:
            logger.info(f"Backfilling quality scores (limit: {args.limit})...")
            count = analyzer.backfill_quality_scores(limit=args.limit)
            print(f"Evaluated {count} cycles with BlindEvaluator")
            return

        # Show raw data if requested
        if args.raw_data:
            logger.info(f"Fetching raw data (days: {args.days}, limit: {args.limit})...")
            data = analyzer.get_raw_data(days=args.days, limit=args.limit)

            if not data:
                print("No TDD cycle data found in experiment_logs.")
                return

            print(f"\nRaw Experiment Data ({len(data)} records):")
            print("-" * 80)
            for record in data:
                print(f"  {record['timestamp'][:19]} | {record['result']:7} | "
                      f"{record['test_name'] or 'N/A'[:30]}")
                if record['actual_model']:
                    print(f"    Model: {record['actual_model']}")
                if record['latency_ms']:
                    print(f"    Latency: {record['latency_ms']:.0f}ms")
            return

        # Generate and display report
        logger.info(f"Generating production quality report (last {args.days} days)...")
        report = analyzer.generate_report(days=args.days)

        # Print summary
        report.print_summary()

        # Export to JSON if requested
        if args.export:
            export_data = {
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "total_cycles": report.total_cycles,
                "unique_models": report.unique_models,
                "best_model_overall": report.best_model_overall,
                "best_model_by_task_type": report.best_model_by_task_type,
                "model_performance": {
                    model_id: {
                        "task_count": perf.task_count,
                        "success_count": perf.success_count,
                        "success_rate": perf.success_rate,
                        "avg_latency_ms": perf.avg_latency_ms,
                        "avg_tokens": perf.avg_tokens,
                        "tasks_by_type": perf.tasks_by_type,
                    }
                    for model_id, perf in report.model_performance.items()
                },
                "trends": report.trends,
            }

            with open(args.export, "w") as f:
                json.dump(export_data, f, indent=2)
            print(f"\nReport exported to: {args.export}")

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
