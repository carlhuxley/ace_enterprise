"""Per-module model routing for the bootstrap synthesis pipeline.

Reads historical outcomes from audit.jsonl and recommends the cheapest model
likely to succeed for each module, with an appropriate escalation threshold.

agent_ref in AdaptiveBroker terms = the OpenRouter model string.

Routing outcomes:
  cheap, escalate=999   Module passed cleanly with cheap model — stay cheap.
  cheap, escalate=2     Module struggled with cheap model (≥50% fail rate) but
                        eventually passed — give it 2 tries then escalate.
  cheap, escalate=1     Module has only failures (no passes yet) — attempt once
                        then escalate immediately (feature file may have been fixed).
  cheap, escalate=999   No history — default cheap, no escalation.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SynthesisRouter:
    """Recommends (primary_model, escalate_after) per module from audit history."""

    def __init__(
        self,
        audit_log: Path,
        cheap_model: str,
        premium_model: str,
    ) -> None:
        self._audit_log = audit_log
        self._cheap = cheap_model
        self._premium = premium_model
        # stem → model → {"pass": int, "fail": int, "tokens": list[int]}
        self._stats: dict[str, dict[str, dict]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, stem: str) -> tuple[str, int]:
        """Return (primary_model, escalate_after) for this module stem."""
        if stem not in self._stats:
            return self._cheap, 999

        cheap = self._stats[stem].get(self._cheap, {})
        cheap_pass = cheap.get("pass", 0)
        cheap_fail = cheap.get("fail", 0)
        cheap_total = cheap_pass + cheap_fail

        premium = self._stats[stem].get(self._premium, {})
        premium_pass = premium.get("pass", 0)

        if cheap_pass > 0 and cheap_fail == 0:
            return self._cheap, 999

        if cheap_pass == 0 and cheap_fail > 0 and premium_pass > 0:
            return self._premium, 999

        if cheap_pass > 0 and cheap_fail > 0:
            fail_rate = cheap_fail / cheap_total
            if fail_rate >= 0.5:
                return self._cheap, 2
            return self._cheap, 999

        if cheap_pass == 0 and cheap_fail > 0:
            return self._cheap, 1

        return self._cheap, 999

    def print_plan(self) -> None:
        """Log a human-readable routing plan for modules with non-default routing."""
        non_default = []
        for stem in sorted(self._stats):
            model, escalate = self.recommend(stem)
            cheap = self._stats[stem].get(self._cheap, {})
            p, f = cheap.get("pass", 0), cheap.get("fail", 0)
            label = "sonnet" if model == self._premium else "haiku"
            if model != self._cheap or escalate != 999:
                non_default.append(f"    {stem:<40s} → {label} esc={escalate}  [{p}p/{f}f]")
        if non_default:
            print(f"  SynthesisRouter: {len(non_default)} module(s) with non-default routing:")
            for line in non_default:
                print(line)
        else:
            print("  SynthesisRouter: all modules default to haiku/esc=999")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._audit_log.exists():
            return
        with open(self._audit_log, encoding="utf-8") as f:
            for raw in f:
                try:
                    r = json.loads(raw)
                    event = r.get("event")
                    if event not in ("CLEAN_ROOM_PASS", "STYLE_BLOCK"):
                        continue
                    feature = r.get("feature", "")
                    model = r.get("model", "")
                    if not feature or not model:
                        continue
                    stem = Path(feature).stem
                    bucket = self._stats.setdefault(stem, {}).setdefault(
                        model, {"pass": 0, "fail": 0, "tokens": []}
                    )
                    if event == "CLEAN_ROOM_PASS":
                        bucket["pass"] += 1
                        tok = r.get("input_tokens", 0) + r.get("output_tokens", 0)
                        bucket["tokens"].append(tok)
                    else:
                        bucket["fail"] += 1
                except Exception:
                    pass
        logger.debug("SynthesisRouter loaded %d module histories", len(self._stats))
