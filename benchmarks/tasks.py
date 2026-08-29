"""Curated bank of tricky coding tasks for the ACE proof-of-concept benchmark.

Provenance: the task specs and pytest suites below were authored by Claude
(an LLM) from a three-domain outline, then audited -- see
benchmarks/verify_oracles.py, runnable with
`.venv/bin/python -m benchmarks.verify_oracles` -- against a canonical
(known-correct) reference implementation and a naive/buggy implementation
for every single task:

  - the canonical reference must pass the task's full pytest suite
  - the naive/buggy implementation demonstrating the task's `trap` must fail
    it, on the specific assertion targeting that edge case

Several tasks failed this audit on the first pass and were rewritten (see
git history): a Kahan-summation comparison that relied on `sum()`, which
CPython already compensates internally; an asyncio.shield test that didn't
actually force a second cancellation, so shielded and unshielded code were
indistinguishable; a CancelledError-retry test that still passed even when
the buggy solution retried the cancellation pointlessly; and a shell-
injection test whose "safe" reference failed once because an *earlier*
buggy run had leaked a side-effect file into the repo root (a real bug in
the local sandbox's cwd handling, since fixed in benchmarks/sandbox.py, not
in the test itself). None of this makes the suites "hand-authored by human
domain experts" -- an LLM wrote every assertion here. What the audit buys is
narrower and verifiable: strict oracle fidelity (canonical passes, naive
buggy fails) for the specific reference/buggy pairs that were tried, on this
Python version and interpreter. It does not guarantee no test is still
too permissive against some other incorrect implementation the audit didn't
think to try.

Each task ships:
  - a natural-language spec + exact required function signature(s)
  - a self-contained pytest test module that imports from `solution.py` and
    exercises the specific edge case the task is designed to catch
  - a one-line `trap` describing the footgun, for humans reading the report

Three domains, ~10 tasks each (see the module docstring in generator.py):
  numeric_edge_cases      - float/int edge cases (signed zero, NaN, precision)
  security_boundaries     - path traversal, injection, weak crypto, unsafe (de)serialization
  concurrency_boundaries  - asyncio cancellation, timeouts, shared-state races
"""
from dataclasses import dataclass, field
from typing import Literal

Domain = Literal["numeric_edge_cases", "security_boundaries", "concurrency_boundaries"]


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    domain: Domain
    title: str
    prompt: str
    test_code: str
    trap: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "title": self.title,
            "prompt": self.prompt,
            "test_code": self.test_code,
            "trap": self.trap,
            "tags": self.tags,
        }


def _spec(title: str, body: str, signatures: list[str]) -> str:
    sig_block = "\n".join(f"    {s}" for s in signatures)
    return (
        f"Write a Python module named `solution.py`.\n\n"
        f"Task: {title}\n\n{body.strip()}\n\n"
        f"Required signature(s) (use these exact names):\n{sig_block}\n\n"
        "Return ONLY a single ```python code block containing the complete "
        "contents of solution.py. No explanation, no test code."
    )


# ============================================================================
# Domain 1: numeric / float edge cases
# ============================================================================

NUMERIC_TASKS = [
    BenchmarkTask(
        id="num_div_zero",
        domain="numeric_edge_cases",
        title="IEEE-754-correct division",
        prompt=_spec(
            "IEEE-754-correct division",
            """
Implement `safe_divide(a, b)` which divides two floats and NEVER raises
ZeroDivisionError. When the divisor is zero, follow IEEE 754 semantics:
a positive numerator over zero is +infinity, a negative numerator over zero
is -infinity, and zero over zero is NaN. Preserve the sign of a zero divisor
(dividing by -0.0 flips the sign of the result relative to dividing by 0.0).
""",
            ["def safe_divide(a: float, b: float) -> float:"],
        ),
        test_code="""
import math
from solution import safe_divide


def test_positive_over_positive_zero_is_inf():
    assert safe_divide(1.0, 0.0) == math.inf


def test_negative_over_positive_zero_is_neg_inf():
    assert safe_divide(-1.0, 0.0) == -math.inf


def test_positive_over_negative_zero_is_neg_inf():
    assert safe_divide(1.0, -0.0) == -math.inf


def test_zero_over_zero_is_nan():
    assert math.isnan(safe_divide(0.0, 0.0))


def test_normal_division_still_works():
    assert safe_divide(10.0, 2.0) == 5.0
""",
        trap="naive `a / b` raises ZeroDivisionError instead of producing inf/-inf/nan",
        tags=["zero_division_sign"],
    ),
    BenchmarkTask(
        id="num_neg_zero",
        domain="numeric_edge_cases",
        title="Detect negative zero",
        prompt=_spec(
            "Detect negative zero",
            """
Implement `is_negative_zero(x)` that returns True only for the float value
-0.0, and False for +0.0 and every other float (including negative numbers
and NaN).
""",
            ["def is_negative_zero(x: float) -> bool:"],
        ),
        test_code="""
import math
from solution import is_negative_zero


def test_negative_zero_is_true():
    assert is_negative_zero(-0.0) is True


def test_positive_zero_is_false():
    assert is_negative_zero(0.0) is False


def test_positive_number_is_false():
    assert is_negative_zero(1.0) is False


def test_negative_number_is_false():
    assert is_negative_zero(-3.5) is False


def test_nan_is_false():
    assert is_negative_zero(math.nan) is False
""",
        trap="`x == -0.0` and `x < 0` both fail: -0.0 == 0.0 in Python and -0.0 < 0 is False",
        tags=["negative_zero_detection"],
    ),
    BenchmarkTask(
        id="num_round_half_even",
        domain="numeric_edge_cases",
        title="Banker's rounding",
        prompt=_spec(
            "Banker's rounding",
            """
Implement `round_half_even(value, ndigits=0)` that rounds `value` to
`ndigits` decimal places using round-half-to-even ("banker's rounding"): a
value exactly halfway between two candidates rounds to whichever candidate
is even.
""",
            ["def round_half_even(value: float, ndigits: int = 0) -> float:"],
        ),
        test_code="""
from solution import round_half_even


def test_rounds_half_up_to_even():
    assert round_half_even(2.5) == 2.0


def test_rounds_half_down_to_even():
    assert round_half_even(3.5) == 4.0


def test_rounds_negative_half_to_even():
    assert round_half_even(-2.5) == -2.0


def test_rounds_with_ndigits():
    assert round_half_even(0.125, 2) == 0.12
""",
        trap="`int(x + 0.5)`-style rounding always rounds .5 up, not to even",
        tags=["banker_rounding"],
    ),
    BenchmarkTask(
        id="num_nearly_equal",
        domain="numeric_edge_cases",
        title="Float comparison with tolerance",
        prompt=_spec(
            "Float comparison with tolerance",
            """
Implement `nearly_equal(a, b, rel_tol=1e-9)`, comparable to `math.isclose`.
It must: return True for values within `rel_tol` relative tolerance of each
other; return True when a and b are the same infinity; return False when
either value is NaN (NaN is never equal to anything, including itself).
""",
            ["def nearly_equal(a: float, b: float, rel_tol: float = 1e-9) -> bool:"],
        ),
        test_code="""
import math
from solution import nearly_equal


def test_close_values_are_equal():
    assert nearly_equal(1.0000000001, 1.0000000002) is True


def test_far_values_are_not_equal():
    assert nearly_equal(1.0, 2.0) is False


def test_nan_is_never_equal():
    assert nearly_equal(math.nan, math.nan) is False


def test_same_infinity_is_equal():
    assert nearly_equal(math.inf, math.inf) is True
""",
        trap="`abs(a - b) < rel_tol` breaks for large magnitudes and for inf - inf (= NaN)",
        tags=["float_tolerance_comparison"],
    ),
    BenchmarkTask(
        id="num_average_empty",
        domain="numeric_edge_cases",
        title="Average of a possibly-empty list",
        prompt=_spec(
            "Average of a possibly-empty list",
            """
Implement `average(nums)` returning the arithmetic mean of a list of floats.
For an empty list, return `float('nan')` instead of raising an exception.
""",
            ["def average(nums: list) -> float:"],
        ),
        test_code="""
import math
from solution import average


def test_average_of_values():
    assert average([1.0, 2.0, 3.0]) == 2.0


def test_average_of_empty_list_is_nan():
    assert math.isnan(average([]))
""",
        trap="`sum(nums) / len(nums)` raises ZeroDivisionError on an empty list",
        tags=["empty_list_average"],
    ),
    BenchmarkTask(
        id="num_pct_change",
        domain="numeric_edge_cases",
        title="Percentage change from a zero baseline",
        prompt=_spec(
            "Percentage change from a zero baseline",
            """
Implement `percentage_change(old, new)` returning `(new - old) / old * 100`.
When `old` is 0.0: return +infinity if `new` is positive, -infinity if `new`
is negative, and 0.0 if `new` is also 0.0. Never raise ZeroDivisionError.
""",
            ["def percentage_change(old: float, new: float) -> float:"],
        ),
        test_code="""
import math
from solution import percentage_change


def test_normal_change():
    assert percentage_change(50.0, 75.0) == 50.0


def test_zero_baseline_positive_new_is_inf():
    assert percentage_change(0.0, 5.0) == math.inf


def test_zero_baseline_negative_new_is_neg_inf():
    assert percentage_change(0.0, -5.0) == -math.inf


def test_zero_baseline_zero_new_is_zero():
    assert percentage_change(0.0, 0.0) == 0.0
""",
        trap="dividing by `old` directly raises ZeroDivisionError when old == 0.0",
        tags=["percentage_change_zero_baseline"],
    ),
    BenchmarkTask(
        id="num_clamp_nan",
        domain="numeric_edge_cases",
        title="Clamp that respects NaN and invalid bounds",
        prompt=_spec(
            "Clamp that respects NaN and invalid bounds",
            """
Implement `clamp(value, lo, hi)` that constrains `value` to `[lo, hi]`. If
`lo > hi`, raise ValueError. If `value` is NaN, return it unchanged (NaN
comparisons are always False, so do not let it silently become `lo` or `hi`).
""",
            ["def clamp(value: float, lo: float, hi: float) -> float:"],
        ),
        test_code="""
import math
import pytest
from solution import clamp


def test_value_in_range_unchanged():
    assert clamp(5.0, 1.0, 10.0) == 5.0


def test_value_below_range_clamped_to_lo():
    assert clamp(-5.0, 1.0, 10.0) == 1.0


def test_value_above_range_clamped_to_hi():
    assert clamp(50.0, 1.0, 10.0) == 10.0


def test_nan_passes_through():
    assert math.isnan(clamp(math.nan, 1.0, 10.0))


def test_invalid_bounds_raise():
    with pytest.raises(ValueError):
        clamp(5.0, 10.0, 1.0)
""",
        trap="`max(lo, min(hi, value))` gives order-dependent, often wrong results when value is NaN",
        tags=["clamp_nan_handling"],
    ),
    BenchmarkTask(
        id="num_kahan_sum",
        domain="numeric_edge_cases",
        title="Kahan compensated summation",
        prompt=_spec(
            "Kahan compensated summation",
            """
Implement `kahan_sum(nums)` using Kahan's compensated summation algorithm to
sum a list of floats with lower rounding error than naive left-to-right
summation.
""",
            ["def kahan_sum(nums: list) -> float:"],
        ),
        test_code="""
import math
from solution import kahan_sum


def _naive_sum(nums):
    # Explicit left-to-right accumulation -- NOT the `sum()` builtin, which
    # on modern CPython already uses an internally compensated algorithm for
    # floats and would defeat the point of this comparison.
    total = 0.0
    for x in nums:
        total += x
    return total


def test_matches_exact_sum_closely():
    nums = [1.0] + [math.ulp(1.0) / 4] * 400
    expected = math.fsum(nums)
    assert abs(kahan_sum(nums) - expected) < 1e-12


def test_more_accurate_than_naive_sum():
    nums = [1.0] + [math.ulp(1.0) / 4] * 400
    expected = math.fsum(nums)
    naive_error = abs(_naive_sum(nums) - expected)
    kahan_error = abs(kahan_sum(nums) - expected)
    assert kahan_error < naive_error


def test_handles_empty_list():
    assert kahan_sum([]) == 0.0
""",
        trap="plain `sum()` silently drops small addends below the running total's ULP",
        tags=["kahan_summation"],
    ),
    BenchmarkTask(
        id="num_currency_cents",
        domain="numeric_edge_cases",
        title="Parse decimal currency strings to integer cents",
        prompt=_spec(
            "Parse decimal currency strings to integer cents",
            """
Implement `parse_currency_to_cents(amount)` that parses a decimal string
like "19.99" into an integer number of cents (1999), without float rounding
artifacts. Handle: two decimal digits ("19.99" -> 1999), one decimal digit
("3.5" -> 350), no decimal point ("100" -> 10000), and a leading minus sign
("-5.25" -> -525).
""",
            ["def parse_currency_to_cents(amount: str) -> int:"],
        ),
        test_code="""
from solution import parse_currency_to_cents


def test_two_decimal_digits():
    assert parse_currency_to_cents("19.99") == 1999


def test_one_decimal_digit():
    assert parse_currency_to_cents("3.5") == 350


def test_no_decimal_point():
    assert parse_currency_to_cents("100") == 10000


def test_negative_amount():
    assert parse_currency_to_cents("-5.25") == -525


def test_small_amount_no_float_drift():
    assert parse_currency_to_cents("0.10") == 10
""",
        trap="`int(float(s) * 100)` gives 1998 for \"19.99\" due to binary float representation error",
        tags=["currency_string_parsing"],
    ),
    BenchmarkTask(
        id="num_normalize_angle",
        domain="numeric_edge_cases",
        title="Normalize an angle to [0, 360)",
        prompt=_spec(
            "Normalize an angle to [0, 360)",
            """
Implement `normalize_angle_degrees(deg)` that wraps any float degree value
into the half-open range [0.0, 360.0), including negative values and values
that are already an exact multiple of 360.
""",
            ["def normalize_angle_degrees(deg: float) -> float:"],
        ),
        test_code="""
from solution import normalize_angle_degrees


def test_within_range_unchanged():
    assert normalize_angle_degrees(10.0) == 10.0


def test_over_360_wraps():
    assert normalize_angle_degrees(370.0) == 10.0


def test_negative_wraps_up():
    assert normalize_angle_degrees(-10.0) == 350.0


def test_exact_360_wraps_to_zero():
    assert normalize_angle_degrees(360.0) == 0.0


def test_large_negative_wraps_to_zero():
    assert normalize_angle_degrees(-720.0) == 0.0
""",
        trap="`math.fmod(deg, 360)` follows C semantics (sign of dividend) and returns negative results for negative input, unlike Python's `%`",
        tags=["angle_normalization"],
    ),
]


# ============================================================================
# Domain 2: security / linter boundaries
# ============================================================================

SECURITY_TASKS = [
    BenchmarkTask(
        id="sec_safe_join",
        domain="security_boundaries",
        title="Path-traversal-safe join",
        prompt=_spec(
            "Path-traversal-safe join",
            """
Implement `safe_join(base_dir, user_path)` that joins `base_dir` with a
user-supplied relative path and returns the resulting absolute path, ONLY if
that path stays within `base_dir`. Raise ValueError if `user_path` is an
absolute path, or if it (via `..` segments or otherwise) would resolve to a
location outside `base_dir`.
""",
            ["def safe_join(base_dir: str, user_path: str) -> str:"],
        ),
        test_code="""
import pytest
from solution import safe_join


def test_joins_normal_relative_path():
    result = safe_join("/srv/app/uploads", "report.pdf")
    assert result == "/srv/app/uploads/report.pdf"


def test_rejects_parent_traversal():
    with pytest.raises(ValueError):
        safe_join("/srv/app/uploads", "../../etc/passwd")


def test_rejects_absolute_path_override():
    with pytest.raises(ValueError):
        safe_join("/srv/app/uploads", "/etc/passwd")
""",
        trap="`os.path.join(base, user_path)` happily returns a path outside base_dir for '../' input or an absolute user_path",
        tags=["path_traversal_join"],
    ),
    BenchmarkTask(
        id="sec_list_directory",
        domain="security_boundaries",
        title="Shell-injection-safe directory listing",
        prompt=_spec(
            "Shell-injection-safe directory listing",
            """
Implement `list_directory(path)` that returns the stdout of listing the
given directory (equivalent to `ls -la path`), as a string. Do not use a
shell (no `shell=True`, no `os.system`, no string-interpolated commands):
`path` must be passed as a literal argument, never interpreted for shell
metacharacters.
""",
            ["def list_directory(path: str) -> str:"],
        ),
        test_code="""
from solution import list_directory


def test_lists_existing_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    output = list_directory(str(tmp_path))
    assert "a.txt" in output


def test_does_not_execute_injected_command(tmp_path):
    marker = tmp_path / "should_not_exist.txt"
    malicious = f"{tmp_path}; touch {marker}"
    try:
        list_directory(malicious)
    except Exception:
        pass
    assert not marker.exists()
""",
        trap="`subprocess.run(f\"ls -la {path}\", shell=True)` lets `path` inject arbitrary shell commands",
        tags=["shell_injection"],
    ),
    BenchmarkTask(
        id="sec_yaml_safe",
        domain="security_boundaries",
        title="Safe YAML config parsing",
        prompt=_spec(
            "Safe YAML config parsing",
            """
Implement `load_config(yaml_text)` that parses a YAML document into a dict
using a safe loader only (no arbitrary Python object construction from tags
like `!!python/object/apply:...`).
""",
            ["def load_config(yaml_text: str) -> dict:"],
        ),
        test_code="""
import pytest
from solution import load_config


def test_parses_simple_mapping():
    result = load_config("key: value\\nnum: 5\\n")
    assert result == {"key": "value", "num": 5}


def test_rejects_python_object_tag():
    malicious = "bad: !!python/object/apply:os.system ['echo pwned']"
    with pytest.raises(Exception):
        load_config(malicious)
""",
        trap="`yaml.load(text)` (or `Loader=yaml.Loader`) executes arbitrary Python object constructors; must use `yaml.safe_load`",
        tags=["unsafe_yaml_load"],
    ),
    BenchmarkTask(
        id="sec_hash_password",
        domain="security_boundaries",
        title="Salted password hashing",
        prompt=_spec(
            "Salted password hashing",
            """
Implement `hash_password(password)` returning a salted hash string (a
different random salt each call, so hashing the same password twice gives
different output), and `verify_password(password, stored)` that checks a
password against a previously stored hash.
""",
            [
                "def hash_password(password: str) -> str:",
                "def verify_password(password: str, stored: str) -> bool:",
            ],
        ),
        test_code="""
from solution import hash_password, verify_password


def test_same_password_hashes_differently_each_time():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    assert h1 != h2


def test_hash_does_not_contain_plaintext():
    h = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in h


def test_verify_roundtrip():
    stored = hash_password("hunter2")
    assert verify_password("hunter2", stored) is True
    assert verify_password("wrong-password", stored) is False
""",
        trap="`hashlib.sha256(password.encode()).hexdigest()` with no salt is deterministic and crackable via rainbow tables",
        tags=["unsalted_password_hash"],
    ),
    BenchmarkTask(
        id="sec_no_eval_template",
        domain="security_boundaries",
        title="Injection-safe string templating",
        prompt=_spec(
            "Injection-safe string templating",
            """
Implement `render_greeting(name)` returning `f"Hello, {name}!"`. It must
treat `name` purely as data: even if `name` contains code-like text, it must
never be evaluated or executed, only inserted literally into the output
string.
""",
            ["def render_greeting(name: str) -> str:"],
        ),
        test_code="""
import os
from solution import render_greeting


def test_basic_greeting():
    assert render_greeting("Ada") == "Hello, Ada!"


def test_adversarial_input_is_not_executed():
    payload = "__import__('os').system('touch pwned_marker')"
    result = render_greeting(payload)
    assert result == f"Hello, {payload}!"
    assert not os.path.exists("pwned_marker")
""",
        trap="using `eval()`/`exec()` to build the templated string executes attacker-controlled input",
        tags=["eval_injection"],
    ),
    BenchmarkTask(
        id="sec_safe_deserialize",
        domain="security_boundaries",
        title="Safe deserialization of untrusted bytes",
        prompt=_spec(
            "Safe deserialization of untrusted bytes",
            """
Implement `deserialize_payload(data)` that deserializes a JSON payload
(bytes) into a dict. Must NOT use `pickle.loads`, which can execute
arbitrary code embedded in untrusted bytes.
""",
            ["def deserialize_payload(data: bytes) -> dict:"],
        ),
        test_code="""
import json
import pickle
import pytest
from solution import deserialize_payload


def test_deserializes_json_bytes():
    payload = json.dumps({"a": 1, "b": [1, 2, 3]}).encode()
    assert deserialize_payload(payload) == {"a": 1, "b": [1, 2, 3]}


def test_rejects_pickle_payload():
    class Exploit:
        def __reduce__(self):
            return (print, ("PWNED-BY-PICKLE",))

    malicious = pickle.dumps(Exploit())
    with pytest.raises(Exception):
        deserialize_payload(malicious)
""",
        trap="`pickle.loads(data)` executes `__reduce__` payloads embedded in attacker-controlled bytes",
        tags=["unsafe_pickle_deserialize"],
    ),
    BenchmarkTask(
        id="sec_param_query",
        domain="security_boundaries",
        title="Parameterized SQL query building",
        prompt=_spec(
            "Parameterized SQL query building",
            """
Implement `build_select_query(table, filters)` returning a `(query, params)`
tuple: a SQL SELECT statement using `?` placeholders for every filter value
(never interpolating values directly into the SQL string), and a list of the
corresponding parameter values in the same order as `filters`. `table` must
be one of the allowed names `"users"` or `"orders"`; raise ValueError for
any other table name (table names cannot be parameterized safely, so they
must be validated against an allowlist instead).
""",
            ["def build_select_query(table: str, filters: dict) -> tuple:"],
        ),
        test_code="""
import sqlite3
import pytest
from solution import build_select_query


def test_builds_parameterized_query_executable_against_sqlite():
    query, params = build_select_query("users", {"id": 5, "name": "bob"})
    assert "5" not in query
    assert "bob" not in query
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (5, 'bob')")
    cur = conn.execute(query, params)
    assert cur.fetchone() == (5, "bob")


def test_rejects_table_name_outside_allowlist():
    with pytest.raises(ValueError):
        build_select_query("users; DROP TABLE users;--", {"id": 1})
""",
        trap="f-string-interpolating filter values into the SQL text is classic SQL injection",
        tags=["sql_injection"],
    ),
    BenchmarkTask(
        id="sec_constant_time_compare",
        domain="security_boundaries",
        title="Timing-safe token comparison",
        prompt=_spec(
            "Timing-safe token comparison",
            """
Implement `verify_token(a, b)` comparing two secret string tokens for
equality using a constant-time comparison (`hmac.compare_digest`), not the
`==` operator, to avoid leaking information via timing side channels.
""",
            ["def verify_token(a: str, b: str) -> bool:"],
        ),
        test_code="""
import pathlib
from solution import verify_token


def test_equal_tokens():
    assert verify_token("supersecrettoken123", "supersecrettoken123") is True


def test_different_tokens():
    assert verify_token("supersecrettoken123", "wrongtoken") is False


def test_uses_constant_time_comparison():
    src = pathlib.Path(__file__).parent.joinpath("solution.py").read_text()
    assert "compare_digest" in src, "expected hmac.compare_digest for timing-safe comparison"
""",
        trap="plain `a == b` is functionally correct but leaks timing information proportional to the matching prefix length",
        tags=["timing_safe_comparison"],
    ),
    BenchmarkTask(
        id="sec_safe_read_file",
        domain="security_boundaries",
        title="Path-traversal-safe file read",
        prompt=_spec(
            "Path-traversal-safe file read",
            """
Implement `read_user_file(base_dir, filename)` that reads and returns the
text content of `filename` located within `base_dir`. Raise ValueError if
`filename` would resolve (via `..` segments or an absolute path) to a
location outside `base_dir`.
""",
            ["def read_user_file(base_dir: str, filename: str) -> str:"],
        ),
        test_code="""
import pytest
from solution import read_user_file


def test_reads_file_within_base(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    assert read_user_file(str(tmp_path), "notes.txt") == "hello"


def test_rejects_traversal_outside_base(tmp_path):
    secret = tmp_path.parent / "abc_secret_probe.txt"
    secret.write_text("TOP SECRET")
    try:
        with pytest.raises(ValueError):
            read_user_file(str(tmp_path), "../abc_secret_probe.txt")
    finally:
        secret.unlink()
""",
        trap="joining base_dir + filename without resolving/validating lets '../' escape the sandboxed directory",
        tags=["path_traversal_read"],
    ),
    BenchmarkTask(
        id="sec_secure_tempfile",
        domain="security_boundaries",
        title="Secure temp file creation",
        prompt=_spec(
            "Secure temp file creation",
            """
Implement `write_temp_report(content)` that writes `content` to a NEW
temporary file with a unique, unpredictable name (using `tempfile`) and
returns the path. Do not write to a fixed, predictable filename such as
"/tmp/report.txt", which is vulnerable to race conditions and symlink
attacks from other processes on a shared machine.
""",
            ["def write_temp_report(content: str) -> str:"],
        ),
        test_code="""
import pathlib
from solution import write_temp_report


def test_writes_content_to_returned_path():
    path = write_temp_report("hello world")
    assert pathlib.Path(path).read_text() == "hello world"


def test_uses_unique_paths_not_a_fixed_name():
    p1 = write_temp_report("a")
    p2 = write_temp_report("b")
    assert p1 != p2
""",
        trap="writing to a fixed path like '/tmp/report.txt' every call is predictable and racy under concurrent/adversarial use",
        tags=["predictable_tempfile"],
    ),
]


# ============================================================================
# Domain 3: concurrency boundaries (asyncio)
# ============================================================================
#
# Test functions are plain `def test_...(): asyncio.run(...)` rather than
# `async def test_...` -- the harness container only installs pytest +
# bandit + pytest-timeout (see docker/harness/Containerfile), not
# pytest-asyncio, so native async test functions would silently no-op.
# Wrapping each test body in asyncio.run() needs nothing beyond the stdlib.

CONCURRENCY_TASKS = [
    BenchmarkTask(
        id="conc_timeout",
        domain="concurrency_boundaries",
        title="Timeout a coroutine",
        prompt=_spec(
            "Timeout a coroutine",
            """
Implement `async def run_with_timeout(coro, timeout)` that awaits `coro`,
but if it does not complete within `timeout` seconds, cancels it and raises
`asyncio.TimeoutError` instead of letting it run forever.
""",
            ["async def run_with_timeout(coro, timeout: float):"],
        ),
        test_code="""
import asyncio
import pytest
from solution import run_with_timeout


async def _fast():
    await asyncio.sleep(0.01)
    return "ok"


async def _slow():
    await asyncio.sleep(1.0)
    return "done"


def test_returns_result_within_timeout():
    assert asyncio.run(run_with_timeout(_fast(), 1.0)) == "ok"


def test_raises_timeout_error_when_too_slow():
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_with_timeout(_slow(), 0.05))
""",
        trap="awaiting the coroutine directly with no wait_for/cancellation just hangs (or eventually returns late) instead of timing out",
        tags=["coroutine_reuse_timeout"],
    ),
    BenchmarkTask(
        id="conc_gather_errors",
        domain="concurrency_boundaries",
        title="Gather without one failure cancelling the rest",
        prompt=_spec(
            "Gather without one failure cancelling the rest",
            """
Implement `async def gather_with_error_handling(coros)` that runs a list of
coroutines concurrently and returns a list of results in the same order,
where a coroutine that raises an exception contributes the exception object
itself (not re-raised) rather than aborting the other coroutines.
""",
            ["async def gather_with_error_handling(coros: list) -> list:"],
        ),
        test_code="""
import asyncio
from solution import gather_with_error_handling


async def _ok():
    return 1


async def _boom():
    raise ValueError("bad")


def test_collects_mixed_results_and_exceptions():
    results = asyncio.run(gather_with_error_handling([_ok(), _boom(), _ok()]))
    assert results[0] == 1
    assert isinstance(results[1], ValueError)
    assert results[2] == 1
""",
        trap="plain `asyncio.gather(*coros)` (without return_exceptions=True) propagates the first exception and cancels the rest",
        tags=["gather_exception_handling"],
    ),
    BenchmarkTask(
        id="conc_semaphore_limit",
        domain="concurrency_boundaries",
        title="Bounded concurrency",
        prompt=_spec(
            "Bounded concurrency",
            """
Implement `async def run_bounded(coros, max_concurrency)` that runs the
given coroutines, but never lets more than `max_concurrency` of them
execute at the same time (use `asyncio.Semaphore`). Return their results as
a list in the original input order.
""",
            ["async def run_bounded(coros: list, max_concurrency: int) -> list:"],
        ),
        test_code="""
import asyncio
from solution import run_bounded


def test_limits_concurrency_and_preserves_order():
    async def _main():
        counter = [0]
        peak = [0]
        lock = asyncio.Lock()

        async def worker(i):
            async with lock:
                counter[0] += 1
                peak[0] = max(peak[0], counter[0])
            await asyncio.sleep(0.05)
            async with lock:
                counter[0] -= 1
            return i

        coros = [worker(i) for i in range(9)]
        results = await run_bounded(coros, 3)
        return results, peak[0]

    results, peak = asyncio.run(_main())
    assert results == list(range(9))
    assert peak <= 3
""",
        trap="running all coroutines via plain `asyncio.gather(*coros)` ignores max_concurrency entirely",
        tags=["bounded_concurrency"],
    ),
    BenchmarkTask(
        id="conc_cancel_on_failure",
        domain="concurrency_boundaries",
        title="Cancel siblings on first failure",
        prompt=_spec(
            "Cancel siblings on first failure",
            """
Implement `async def race_all_or_cancel(coros)` that runs coroutines
concurrently. If any of them raises an exception, cancel all the other
still-running coroutines and re-raise that exception. If none fail, return
a list of their results.
""",
            ["async def race_all_or_cancel(coros: list) -> list:"],
        ),
        test_code="""
import asyncio
import pytest
from solution import race_all_or_cancel


def test_cancels_remaining_tasks_on_failure():
    flag = {"was_cancelled": False}

    async def _boom():
        await asyncio.sleep(0.01)
        raise ValueError("boom")

    async def _long_running():
        try:
            await asyncio.sleep(2.0)
            return "should not finish"
        except asyncio.CancelledError:
            flag["was_cancelled"] = True
            raise

    async def _main():
        with pytest.raises(ValueError):
            await race_all_or_cancel([_boom(), _long_running()])
        # Checked *before* returning from _main -- asyncio.run() cancels any
        # leftover tasks during its own shutdown, so a check made after
        # asyncio.run() returns can't tell "the function cancelled its
        # siblings" apart from "asyncio.run() cleaned up after it didn't".
        await asyncio.sleep(0.05)
        assert flag["was_cancelled"] is True

    asyncio.run(_main())
""",
        trap="`asyncio.gather` without return_exceptions leaves sibling tasks running in the background instead of cancelling them",
        tags=["cancel_siblings_on_failure"],
    ),
    BenchmarkTask(
        id="conc_producer_consumer",
        domain="concurrency_boundaries",
        title="Queue-based item processing",
        prompt=_spec(
            "Queue-based item processing",
            """
Implement `async def process_items(items, worker)` that feeds `items`
through an `asyncio.Queue` to a single consumer which calls `await
worker(item)` for each one, and returns a list of results in the original
input order. Must terminate cleanly (no deadlock) once all items are
processed.
""",
            ["async def process_items(items: list, worker) -> list:"],
        ),
        test_code="""
import asyncio
from solution import process_items


async def _double(x):
    await asyncio.sleep(0.001)
    return x * 2


def test_processes_all_items_in_order():
    result = asyncio.run(process_items([1, 2, 3, 4], _double))
    assert result == [2, 4, 6, 8]


def test_handles_empty_input():
    result = asyncio.run(process_items([], _double))
    assert result == []
""",
        trap="forgetting a sentinel/queue.join() leaves the consumer awaiting `queue.get()` forever -> the test hangs until pytest-timeout kills it",
        tags=["queue_deadlock"],
    ),
    BenchmarkTask(
        id="conc_retry_backoff",
        domain="concurrency_boundaries",
        title="Retry with exponential backoff",
        prompt=_spec(
            "Retry with exponential backoff",
            """
Implement `async def retry_async(coro_fn, retries, base_delay=0.01)` where
`coro_fn` is a zero-argument async callable. Call it; on failure, retry up
to `retries` more times with delay `base_delay * 2**attempt` between
attempts. Re-raise the last exception if all attempts fail. Never swallow
`asyncio.CancelledError` as a retryable failure -- it must propagate
immediately without retrying.
""",
            ["async def retry_async(coro_fn, retries: int, base_delay: float = 0.01):"],
        ),
        test_code="""
import asyncio
import pytest
from solution import retry_async


def test_retries_until_success():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    result = asyncio.run(retry_async(flaky, retries=5, base_delay=0.001))
    assert result == "ok"
    assert calls["n"] == 3


def test_raises_after_exhausting_retries():
    async def always_fails():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        asyncio.run(retry_async(always_fails, retries=2, base_delay=0.001))


def test_does_not_retry_cancelled_error():
    calls = {"n": 0}

    async def cancels():
        calls["n"] += 1
        raise asyncio.CancelledError()

    async def _main():
        with pytest.raises(asyncio.CancelledError):
            await retry_async(cancels, retries=3, base_delay=0.001)

    asyncio.run(_main())
    assert calls["n"] == 1, "CancelledError must propagate immediately, not be retried"
""",
        trap="a bare `except BaseException:` retry loop also catches (and improperly retries/suppresses) CancelledError, unlike `except Exception:` which correctly lets it through",
        tags=["cancelled_error_retry"],
    ),
    BenchmarkTask(
        id="conc_async_lock_counter",
        domain="concurrency_boundaries",
        title="Lock-protected shared counter",
        prompt=_spec(
            "Lock-protected shared counter",
            """
Implement `async def increment_concurrently(n, workers)`: split `n` total
increments evenly across `workers` concurrent async worker coroutines that
share a single counter. Each individual increment MUST be implemented as:
read the current value, `await asyncio.sleep(0)` (simulating a real
I/O-bound read-modify-write cycle), then write back value + 1. Protect the
shared counter with an `asyncio.Lock` around that read-sleep-write sequence
so concurrent workers never lose updates. Return the final counter value,
which must equal `n` exactly.
""",
            ["async def increment_concurrently(n: int, workers: int) -> int:"],
        ),
        test_code="""
import asyncio
from solution import increment_concurrently


def test_no_lost_updates_under_concurrency():
    result = asyncio.run(increment_concurrently(200, 20))
    assert result == 200
""",
        trap="reading and writing the shared counter around an `await` point without a lock loses updates when workers interleave",
        tags=["async_lock_race"],
    ),
    BenchmarkTask(
        id="conc_shield_cleanup",
        domain="concurrency_boundaries",
        title="Shield cleanup from outer cancellation",
        prompt=_spec(
            "Shield cleanup from outer cancellation",
            """
Implement `async def shielded_cleanup(work_coro, cleanup_coro)` that awaits
`work_coro`. If the surrounding task is cancelled while waiting, the
function must still run `cleanup_coro` to completion in the background
(use `asyncio.shield`), and then re-raise `asyncio.CancelledError`.
""",
            ["async def shielded_cleanup(work_coro, cleanup_coro):"],
        ),
        test_code="""
import asyncio
import pytest
from solution import shielded_cleanup


def test_shield_protects_cleanup_from_a_second_cancellation():
    # A single cancellation while awaiting work_coro is not by itself enough
    # to distinguish shielded from unshielded cleanup: a coroutine that has
    # already caught one CancelledError runs its next `await` normally
    # either way. What asyncio.shield actually protects against is a
    # *second* cancellation arriving while cleanup itself is in flight.
    cleanup_ran = {"v": False}

    async def work():
        await asyncio.sleep(0.05)
        return "work-done"

    async def cleanup():
        await asyncio.sleep(0.1)
        cleanup_ran["v"] = True

    async def _main():
        task = asyncio.ensure_future(shielded_cleanup(work(), cleanup()))
        await asyncio.sleep(0.01)
        task.cancel()  # aborts work(), enters the cleanup phase
        await asyncio.sleep(0.03)  # let it actually start awaiting cleanup
        task.cancel()  # second cancellation, arriving mid-cleanup
        with pytest.raises(asyncio.CancelledError):
            await task
        # let a correctly-shielded cleanup finish in the background
        await asyncio.sleep(0.15)

    asyncio.run(_main())
    assert cleanup_ran["v"] is True
""",
        trap="awaiting cleanup_coro directly (without asyncio.shield) lets a second cancellation abort cleanup mid-flight",
        tags=["shield_double_cancel"],
    ),
    BenchmarkTask(
        id="conc_first_to_finish",
        domain="concurrency_boundaries",
        title="Return the first coroutine to finish",
        prompt=_spec(
            "Return the first coroutine to finish",
            """
Implement `async def first_to_finish(coros)` that runs a list of
coroutines concurrently and returns the result of whichever one completes
first, cancelling the rest without letting their cancellation raise an
unhandled exception.
""",
            ["async def first_to_finish(coros: list):"],
        ),
        test_code="""
import asyncio
from solution import first_to_finish


async def _slow():
    await asyncio.sleep(0.3)
    return "slow"


async def _fast():
    await asyncio.sleep(0.01)
    return "fast"


def test_returns_fastest_result():
    result = asyncio.run(first_to_finish([_slow(), _fast()]))
    assert result == "fast"
""",
        trap="`asyncio.gather` waits for every coroutine to finish instead of returning as soon as the first one does",
        tags=["coroutine_to_task_conversion"],
    ),
    BenchmarkTask(
        id="conc_graceful_shutdown",
        domain="concurrency_boundaries",
        title="Graceful shutdown of running tasks",
        prompt=_spec(
            "Graceful shutdown of running tasks",
            """
Implement `async def graceful_shutdown(tasks)` that cancels every task in
`tasks` and awaits all of them. Suppress `asyncio.CancelledError` (expected,
since we just requested cancellation), but if a task had already failed
with a different exception before being cancelled, re-raise that exception.
""",
            ["async def graceful_shutdown(tasks: list):"],
        ),
        test_code="""
import asyncio
import pytest
from solution import graceful_shutdown


def test_cancels_and_awaits_tasks_without_raising():
    async def _sleeper():
        await asyncio.sleep(5)

    async def _main():
        t1 = asyncio.ensure_future(_sleeper())
        t2 = asyncio.ensure_future(_sleeper())
        await asyncio.sleep(0.01)
        await graceful_shutdown([t1, t2])
        assert t1.done() and t2.done()
        assert t1.cancelled() and t2.cancelled()

    asyncio.run(_main())


def test_propagates_a_real_error_from_a_task():
    async def _boom():
        await asyncio.sleep(0.01)
        raise RuntimeError("real failure")

    async def _sleeper():
        await asyncio.sleep(5)

    async def _main():
        t1 = asyncio.ensure_future(_boom())
        t2 = asyncio.ensure_future(_sleeper())
        await asyncio.sleep(0.05)  # let _boom actually fail first
        with pytest.raises(RuntimeError):
            await graceful_shutdown([t1, t2])

    asyncio.run(_main())
""",
        trap="a blanket `except Exception: pass` around each awaited task also swallows real failures, not just CancelledError",
        tags=["exception_suppression_on_shutdown"],
    ),
]

ALL_TASKS: list[BenchmarkTask] = NUMERIC_TASKS + SECURITY_TASKS + CONCURRENCY_TASKS

_BY_ID = {t.id: t for t in ALL_TASKS}
assert len(_BY_ID) == len(ALL_TASKS), "duplicate task id in benchmark bank"


def get_task(task_id: str) -> BenchmarkTask:
    return _BY_ID[task_id]


def get_tasks(domain: Domain | None = None) -> list[BenchmarkTask]:
    if domain is None:
        return list(ALL_TASKS)
    return [t for t in ALL_TASKS if t.domain == domain]
