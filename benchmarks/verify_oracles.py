"""Oracle-fidelity audit for the benchmark task bank (benchmarks/tasks.py).

The task specs and pytest suites in tasks.py were authored by an LLM (see
that module's docstring for full provenance). This script is the audit that
makes them trustworthy as ground truth: for every task, a canonical
(known-correct) reference implementation must pass the task's full pytest
suite, and a naive/buggy implementation demonstrating the task's `trap` must
fail it -- specifically on the assertion targeting that edge case. If a
buggy solution ever wrongly passes, the test suite (not the buggy solution)
is the thing that needs fixing.

Runs entirely via LocalSubprocessRunner -- no LLM involved; this only checks
that the oracles themselves discriminate correctly.

Usage:
    .venv/bin/python -m benchmarks.verify_oracles
"""
import sys

from benchmarks.sandbox import LocalSubprocessRunner
from benchmarks.tasks import ALL_TASKS

CORRECT = {
    "num_div_zero": """
import math

def safe_divide(a, b):
    if b == 0.0:
        if a == 0.0:
            return math.nan
        sign = math.copysign(1.0, a) * math.copysign(1.0, b)
        return math.inf if sign > 0 else -math.inf
    return a / b
""",
    "num_neg_zero": """
import math

def is_negative_zero(x):
    return x == 0.0 and math.copysign(1.0, x) == -1.0
""",
    "num_round_half_even": """
from decimal import Decimal, ROUND_HALF_EVEN

def round_half_even(value, ndigits=0):
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_EVEN))
""",
    "num_nearly_equal": """
import math

def nearly_equal(a, b, rel_tol=1e-9):
    if math.isnan(a) or math.isnan(b):
        return False
    if a == b:
        return True
    if math.isinf(a) or math.isinf(b):
        return False
    return abs(a - b) <= rel_tol * max(abs(a), abs(b))
""",
    "num_average_empty": """
import math

def average(nums):
    if not nums:
        return math.nan
    return sum(nums) / len(nums)
""",
    "num_pct_change": """
import math

def percentage_change(old, new):
    if old == 0.0:
        if new > 0:
            return math.inf
        if new < 0:
            return -math.inf
        return 0.0
    return (new - old) / old * 100
""",
    "num_clamp_nan": """
import math

def clamp(value, lo, hi):
    if lo > hi:
        raise ValueError("lo > hi")
    if math.isnan(value):
        return value
    return max(lo, min(hi, value))
""",
    "num_kahan_sum": """
def kahan_sum(nums):
    total = 0.0
    c = 0.0
    for x in nums:
        y = x - c
        t = total + y
        c = (t - total) - y
        total = t
    return total
""",
    "num_currency_cents": """
from decimal import Decimal

def parse_currency_to_cents(amount):
    d = Decimal(amount)
    return int((d * 100).to_integral_value())
""",
    "num_normalize_angle": """
def normalize_angle_degrees(deg):
    return deg % 360.0
""",
    "sec_safe_join": """
import os

def safe_join(base_dir, user_path):
    if os.path.isabs(user_path):
        raise ValueError("absolute path not allowed")
    base = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base, user_path))
    if not (candidate == base or candidate.startswith(base + os.sep)):
        raise ValueError("path traversal detected")
    return candidate
""",
    "sec_list_directory": """
import subprocess

def list_directory(path):
    result = subprocess.run(["ls", "-la", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout
""",
    "sec_yaml_safe": """
import yaml

def load_config(yaml_text):
    return yaml.safe_load(yaml_text)
""",
    "sec_hash_password": """
import hashlib
import os

def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + digest.hex()

def verify_password(password, stored):
    salt_hex, digest_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return expected.hex() == digest_hex
""",
    "sec_no_eval_template": """
def render_greeting(name):
    return f"Hello, {name}!"
""",
    "sec_safe_deserialize": """
import json

def deserialize_payload(data):
    return json.loads(data.decode())
""",
    "sec_param_query": """
def build_select_query(table, filters):
    if table not in ("users", "orders"):
        raise ValueError("unknown table")
    where = " AND ".join(f"{k} = ?" for k in filters)
    query = f"SELECT * FROM {table} WHERE {where}"
    return query, list(filters.values())
""",
    "sec_constant_time_compare": """
import hmac

def verify_token(a, b):
    return hmac.compare_digest(a, b)
""",
    "sec_safe_read_file": """
import os

def read_user_file(base_dir, filename):
    base = os.path.abspath(base_dir)
    candidate = os.path.abspath(os.path.join(base, filename))
    if not (candidate == base or candidate.startswith(base + os.sep)):
        raise ValueError("path traversal detected")
    with open(candidate) as f:
        return f.read()
""",
    "sec_secure_tempfile": """
import tempfile
import os

def write_temp_report(content):
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path
""",
    "conc_timeout": """
import asyncio

async def run_with_timeout(coro, timeout):
    return await asyncio.wait_for(coro, timeout)
""",
    "conc_gather_errors": """
import asyncio

async def gather_with_error_handling(coros):
    return await asyncio.gather(*coros, return_exceptions=True)
""",
    "conc_semaphore_limit": """
import asyncio

async def run_bounded(coros, max_concurrency):
    sem = asyncio.Semaphore(max_concurrency)

    async def bound(c):
        async with sem:
            return await c

    return await asyncio.gather(*(bound(c) for c in coros))
""",
    "conc_cancel_on_failure": """
import asyncio

async def race_all_or_cancel(coros):
    tasks = [asyncio.ensure_future(c) for c in coros]
    try:
        results = []
        for t in asyncio.as_completed(tasks):
            results.append(await t)
        return results
    except Exception:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
""",
    "conc_producer_consumer": """
import asyncio

async def process_items(items, worker):
    if not items:
        return []
    queue = asyncio.Queue()
    for i, item in enumerate(items):
        queue.put_nowait((i, item))
    results = [None] * len(items)

    async def consume():
        while not queue.empty():
            i, item = await queue.get()
            results[i] = await worker(item)
            queue.task_done()

    await consume()
    return results
""",
    "conc_retry_backoff": """
import asyncio

async def retry_async(coro_fn, retries, base_delay=0.01):
    attempt = 0
    while True:
        try:
            return await coro_fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt >= retries:
                raise
            await asyncio.sleep(base_delay * 2 ** attempt)
            attempt += 1
""",
    "conc_async_lock_counter": """
import asyncio

async def increment_concurrently(n, workers):
    counter = [0]
    lock = asyncio.Lock()
    per_worker = n // workers
    remainder = n % workers

    async def do_increments(count):
        for _ in range(count):
            async with lock:
                value = counter[0]
                await asyncio.sleep(0)
                counter[0] = value + 1

    tasks = []
    for w in range(workers):
        count = per_worker + (1 if w < remainder else 0)
        tasks.append(do_increments(count))
    await asyncio.gather(*tasks)
    return counter[0]
""",
    "conc_shield_cleanup": """
import asyncio

async def shielded_cleanup(work_coro, cleanup_coro):
    try:
        return await work_coro
    except asyncio.CancelledError:
        await asyncio.shield(cleanup_coro)
        raise
""",
    "conc_first_to_finish": """
import asyncio

async def first_to_finish(coros):
    tasks = [asyncio.ensure_future(c) for c in coros]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return next(iter(done)).result()
""",
    "conc_graceful_shutdown": """
import asyncio

async def graceful_shutdown(tasks):
    for t in tasks:
        t.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, asyncio.CancelledError):
            continue
        if isinstance(r, BaseException):
            raise r
""",
}

BUGGY = {
    "num_div_zero": "def safe_divide(a, b):\n    return a / b\n",
    "num_neg_zero": "def is_negative_zero(x):\n    return x < 0\n",
    "num_round_half_even": "def round_half_even(value, ndigits=0):\n    return float(int(value * 10**ndigits + 0.5)) / 10**ndigits\n",
    "num_nearly_equal": "def nearly_equal(a, b, rel_tol=1e-9):\n    return abs(a - b) < rel_tol\n",
    "num_average_empty": "def average(nums):\n    return sum(nums) / len(nums)\n",
    "num_pct_change": "def percentage_change(old, new):\n    return (new - old) / old * 100\n",
    "num_clamp_nan": "def clamp(value, lo, hi):\n    return max(lo, min(hi, value))\n",
    "num_kahan_sum": "def kahan_sum(nums):\n    total = 0.0\n    for x in nums:\n        total += x\n    return total\n",
    "num_currency_cents": "def parse_currency_to_cents(amount):\n    return int(float(amount) * 100)\n",
    "num_normalize_angle": "import math\ndef normalize_angle_degrees(deg):\n    return math.fmod(deg, 360.0)\n",
    "sec_safe_join": "import os\ndef safe_join(base_dir, user_path):\n    return os.path.join(base_dir, user_path)\n",
    "sec_list_directory": "import subprocess\ndef list_directory(path):\n    return subprocess.run(f'ls -la {path}', shell=True, capture_output=True, text=True).stdout\n",
    "sec_yaml_safe": "import yaml\ndef load_config(yaml_text):\n    return yaml.load(yaml_text, Loader=yaml.Loader)\n",
    "sec_hash_password": "import hashlib\ndef hash_password(password):\n    return hashlib.sha256(password.encode()).hexdigest()\ndef verify_password(password, stored):\n    return hash_password(password) == stored\n",
    "sec_no_eval_template": "def render_greeting(name):\n    return eval(f'\"Hello, \" + {name} + \"!\"')\n",
    "sec_safe_deserialize": "import pickle\ndef deserialize_payload(data):\n    return pickle.loads(data)\n",
    "sec_param_query": "def build_select_query(table, filters):\n    where = ' AND '.join(f\"{k} = '{v}'\" for k, v in filters.items())\n    return f'SELECT * FROM {table} WHERE {where}', []\n",
    "sec_constant_time_compare": "def verify_token(a, b):\n    return a == b\n",
    "sec_safe_read_file": "import os\ndef read_user_file(base_dir, filename):\n    with open(os.path.join(base_dir, filename)) as f:\n        return f.read()\n",
    "sec_secure_tempfile": "def write_temp_report(content):\n    path = '/tmp/report.txt'\n    with open(path, 'w') as f:\n        f.write(content)\n    return path\n",
    "conc_timeout": "import asyncio\nasync def run_with_timeout(coro, timeout):\n    return await coro\n",
    "conc_gather_errors": "import asyncio\nasync def gather_with_error_handling(coros):\n    return await asyncio.gather(*coros)\n",
    "conc_semaphore_limit": "import asyncio\nasync def run_bounded(coros, max_concurrency):\n    return await asyncio.gather(*coros)\n",
    "conc_cancel_on_failure": "import asyncio\nasync def race_all_or_cancel(coros):\n    return await asyncio.gather(*coros)\n",
    "conc_producer_consumer": "import asyncio\nasync def process_items(items, worker):\n    queue = asyncio.Queue()\n    for item in items:\n        queue.put_nowait(item)\n    results = []\n    while True:\n        item = await queue.get()\n        results.append(await worker(item))\n",  # deadlocks: no termination condition
    "conc_retry_backoff": "import asyncio\nasync def retry_async(coro_fn, retries, base_delay=0.01):\n    attempt = 0\n    while True:\n        try:\n            return await coro_fn()\n        except BaseException:\n            if attempt >= retries:\n                raise\n            attempt += 1\n",
    "conc_async_lock_counter": "import asyncio\nasync def increment_concurrently(n, workers):\n    counter = [0]\n    per_worker = n // workers\n    async def do_increments(count):\n        for _ in range(count):\n            value = counter[0]\n            await asyncio.sleep(0)\n            counter[0] = value + 1\n    await asyncio.gather(*(do_increments(per_worker) for _ in range(workers)))\n    return counter[0]\n",
    "conc_shield_cleanup": "import asyncio\nasync def shielded_cleanup(work_coro, cleanup_coro):\n    try:\n        return await work_coro\n    except asyncio.CancelledError:\n        await cleanup_coro\n        raise\n",
    "conc_first_to_finish": "import asyncio\nasync def first_to_finish(coros):\n    results = await asyncio.gather(*coros)\n    return results[0]\n",
    "conc_graceful_shutdown": "import asyncio\nasync def graceful_shutdown(tasks):\n    for t in tasks:\n        t.cancel()\n    for t in tasks:\n        try:\n            await t\n        except Exception:\n            pass\n",
}

def main() -> int:
    runner = LocalSubprocessRunner(test_timeout=15)
    runner.start()

    failures = []
    try:
        for task in ALL_TASKS:
            good = CORRECT.get(task.id)
            if good is None:
                failures.append((task.id, "NO CORRECT REF"))
                continue
            result = runner.send_pulse({"solution.py": good, "test_solution.py": task.test_code})
            ok = result.exit_code == 0 and result.bandit_high == 0
            status = "OK" if ok else "FAIL"
            print(f"[correct ] {task.id:28s} {status}")
            if not ok:
                failures.append((
                    task.id,
                    f"correct solution did not pass: exit={result.exit_code} "
                    f"bandit_high={result.bandit_high}\n{result.stdout[-2000:]}\n{result.stderr[-1000:]}",
                ))

            bad = BUGGY.get(task.id)
            if bad is None:
                continue
            result2 = runner.send_pulse({"solution.py": bad, "test_solution.py": task.test_code})
            bad_ok = result2.exit_code == 0 and result2.bandit_high == 0
            status2 = "correctly FAILED" if not bad_ok else "WRONGLY PASSED"
            print(f"[buggy   ] {task.id:28s} {status2}")
            if bad_ok:
                failures.append((
                    task.id,
                    f"buggy solution wrongly passed (test doesn't catch the trap)\n{result2.stdout[-1500:]}",
                ))
    finally:
        runner.stop()

    print("\n=== SUMMARY ===")
    if failures:
        for tid, msg in failures:
            print(f"\n--- {tid} ---\n{msg}")
        print(f"\n{len(failures)} problem(s) found")
        return 1

    print("All tasks verified: correct solutions pass, buggy solutions correctly fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
