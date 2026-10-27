"""Run pktlib's random tests on every core for as long as you like, and count them.

    uv run python scripts/soak.py --hours 3              # every core but two
    uv run python scripts/soak.py --minutes 10 --workers 4

Each worker runs one suite over and over with a fresh random seed each time and
PKTLIB_SCALE examples per test: the state machine (random networks built through the
whole API), the damaged-file fuzzer, or the property tests. Hypothesis prints a failing
case as the steps that reproduce it; a worker that hits one saves the log and stops, and
the case is in the shared example database, so `uv run pytest` replays it next time.

Progress and a final tally go to soak/summary.json; logs to soak/<worker>-<run>.log.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = {  # name: (test paths, API calls per example at most: a state machine example is a sequence)
    "state machine": (["tests/test_stateful.py"], 50),
    "damaged files": (["tests/test_fuzz_files.py"], 1),
    "properties": (["tests/test_properties.py", "tests/test_iosconfig.py", "tests/test_codec.py"], 1),
}
ORDER = ["state machine", "damaged files", "properties", "state machine", "damaged files"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--minutes", type=float, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--scale", type=int, default=40, help="PKTLIB_SCALE for each run (default 40)")
    ap.add_argument("--out", default=str(ROOT / "soak"))
    args = ap.parse_args()
    seconds = args.hours * 3600 + args.minutes * 60 or 600
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    deadline = time.time() + seconds
    env = {**os.environ, "PKTLIB_SCALE": str(args.scale)}

    running: dict[int, tuple[subprocess.Popen[bytes], str, Path, float]] = {}
    runs = dict.fromkeys(range(args.workers), 0)
    stopped: set[int] = set()
    tally: dict[str, dict[str, float]] = {s: {"runs": 0, "cases": 0, "steps": 0, "seconds": 0} for s in SUITES}
    failures: list[dict[str, str]] = []

    def start(w: int) -> None:
        suite = ORDER[(w + runs[w]) % len(ORDER)]
        log = out / f"w{w}-{runs[w]}.log"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "--hypothesis-show-statistics",
            *SUITES[suite][0],
        ]
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log.open("wb"), stderr=subprocess.STDOUT)
        running[w] = (proc, suite, log, time.time())
        runs[w] += 1

    def report(final: bool = False) -> None:
        total = sum(t["cases"] for t in tally.values())
        steps = sum(t["steps"] for t in tally.values())
        summary = {
            "finished": final,
            "workers": args.workers,
            "scale": args.scale,
            "elapsed_minutes": round((time.time() - (deadline - seconds)) / 60, 1),
            "test_cases": int(total),
            "api_calls_checked_at_most": int(steps),
            "suites": tally,
            "failures": failures,
        }
        (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")

    for w in range(args.workers):
        start(w)
    while running:
        time.sleep(2)
        for w, (proc, suite, log, began) in list(running.items()):
            if proc.poll() is None:
                if time.time() > deadline:
                    proc.terminate()  # a run cut short by the deadline isn't counted
                continue
            del running[w]
            text = log.read_text(errors="replace")
            if proc.returncode == 0:
                # Hypothesis's own count of the examples each test ran and passed
                cases = sum(int(n) for n in re.findall(r"(\d+) passing, \d+ failing", text))
                tally[suite]["runs"] += 1
                tally[suite]["cases"] += cases
                tally[suite]["steps"] += cases * SUITES[suite][1]
                tally[suite]["seconds"] += round(time.time() - began)
                log.unlink()
            elif time.time() <= deadline:
                failures.append({"suite": suite, "log": str(log)})
                stopped.add(w)
                print(f"FAILURE in {suite}: {log}", flush=True)
            if w not in stopped and time.time() < deadline:
                start(w)
        report()
    report(final=True)
    s = json.loads((out / "summary.json").read_text())
    print(
        f"{s['test_cases']:,} test cases (up to {s['api_calls_checked_at_most']:,} API calls checked) in "
        f"{s['elapsed_minutes']} min on {args.workers} workers; {len(failures)} failure(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
