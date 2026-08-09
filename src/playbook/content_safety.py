"""Heuristic content screening for playbook bullets (ace_enterprise-z51).

Playbook bullets get concatenated verbatim into future Generator/Worker
prompts once retrieved, so a bullet's content is not just data — it's future
prompt content. Two untrusted entry points write bullets from LLM-influenced
or externally-supplied text: mcp_server/tools.py's `learn` tool (any MCP
client can call it directly) and Curator's synthesis path (an LLM call whose
output is shaped by Reflector's analysis of a task, which is itself
attacker-influenced if the task/spec was adversarial). Neither validated
content before this.

This is a heuristic pattern-matcher, not a full classifier — it catches
recognisable instruction-hijack and delimiter-spoofing patterns cheaply and
deterministically, without new ML infra or an extra LLM call per bullet. It
is explicitly a narrowing layer, not a guarantee: sophisticated, novel
phrasing can still slip through the FLAG tier. See REJECT vs FLAG below for
what each tier is expected to catch.
"""
import re
from dataclasses import dataclass, field
from enum import Enum

# Marks a bullet as needing human review before its confidence_score can be
# promoted further by ordinary "helpful" feedback (see
# PlaybookManager.update_bullet_feedback / clear_review_flag).
NEEDS_REVIEW_TAG = "needs-review"

# A playbook bullet is meant to be one concise, actionable piece of guidance.
# Anything this long is itself a signal something unusual is going on
# (e.g. an attempt to smuggle a large block of instructions/data).
MAX_BULLET_LENGTH = 2000

# REJECT: clear instruction-hijack or delimiter-spoofing markers. No
# legitimate playbook bullet ("use pytest fixtures for setup", "prefer
# composition over inheritance") should ever match these — false positives
# here are expected to be rare.
_REJECT_PATTERNS = [
    r"\bignore (all |any )?(previous|prior|above|earlier) instructions?\b",
    r"\bdisregard (the )?(above|previous|prior) (instructions?|context|prompt)\b",
    r"\bnew instructions?:",
    r"\byou are now\b",
    r"\bact as (if you are |)(a|an)\b.{0,40}\b(unrestricted|jailbroken|dan)\b",
    r"\breveal your (system prompt|instructions|configuration)\b",
    r"\bprint your (system prompt|instructions|configuration)\b",
    r"<\|im_start\|>",
    r"^\s*\[?(system|assistant)\]?\s*:",  # role-header spoofing at line start
    r"###\s*instruction\b",
    r"\bsend (this|the following|your) (data|credentials|api[_ ]?key|secret)s?\s+to\b",
]

# FLAG: softer signals — imperative language addressed to "you" as an AI/
# model/assistant inside what should be a factual/procedural bullet, or
# other content that's plausible-but-unusual for a playbook entry. Persisted
# with a needs-review tag and a capped confidence_score rather than blocked
# outright, since these are more prone to false positives on legitimate
# meta-commentary about AI behavior (a bullet CAN legitimately be about how
# an agent should behave).
_FLAG_PATTERNS = [
    r"\bas an ai\b",
    r"\byou are an? (ai|language model|assistant)\b",
    r"\bfrom now on\b",
    r"\boverride your\b",
    r"\bdo not (tell|inform|mention to)\b.{0,30}\b(user|human|operator)\b",
]

_REJECT_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _REJECT_PATTERNS]
_FLAG_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _FLAG_PATTERNS]


class Verdict(str, Enum):
    OK = "ok"
    FLAG = "flag"
    REJECT = "reject"


@dataclass
class ScreenResult:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)


def screen_bullet_content(content: str) -> ScreenResult:
    """Heuristically screen bullet content before it's persisted.

    Returns REJECT for content that should never be stored, FLAG for content
    that should be stored but treated as unverified pending human review, and
    OK otherwise.
    """
    reasons: list[str] = []

    if len(content) > MAX_BULLET_LENGTH:
        reasons.append(f"content exceeds {MAX_BULLET_LENGTH} chars ({len(content)})")
        return ScreenResult(Verdict.REJECT, reasons)

    for pattern in _REJECT_RE:
        if pattern.search(content):
            reasons.append(f"matched reject pattern: {pattern.pattern}")
            return ScreenResult(Verdict.REJECT, reasons)

    for pattern in _FLAG_RE:
        if pattern.search(content):
            reasons.append(f"matched flag pattern: {pattern.pattern}")

    if reasons:
        return ScreenResult(Verdict.FLAG, reasons)
    return ScreenResult(Verdict.OK, reasons)


class ContentRejectedError(ValueError):
    """Raised when bullet content fails the REJECT-tier screen."""
