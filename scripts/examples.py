"""Build, audit and index the examples.

    uv run python scripts/examples.py build      # every example into out/examples/, audited
    uv run python scripts/examples.py index      # rewrite examples/README.md from the docstrings

Each example is a script in a folder of examples/ whose docstring starts with a one-line
summary. The index lists them by folder with that line, so it never goes out of date
(tests/test_docs.py fails if it does).
"""

from __future__ import annotations

import ast
import contextlib
import os
import runpy
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FOLDERS = {
    "labs": "Classroom labs: small networks to hand out, with answer keys and grading.",
    "ccna": "One network per CCNA topic, each with ping checks that prove it works.",
    "showcase": "Big, realistic networks that show what pktlib can build.",
    "recipes": "Short scripts for one job each: read a file, check a folder of hand-ins, ...",
}
ARGV = {"practice_lab.py": ["42"]}


def scripts() -> list[Path]:
    return sorted(p for p in EXAMPLES.rglob("*.py") if not p.name.startswith("_"))


def summary(path: Path) -> str:
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    return doc.strip().split("\n")[0].strip() if doc.strip() else "(no docstring)"


def index() -> str:
    out = [
        "# Examples",
        "",
        "Every script builds a network and saves it as a `.pkt` next to where you run it. Each is",
        "built and audited by the tests, and has ping checks you can click in Packet Tracer.",
        "Which ones have been opened in Packet Tracer itself is in",
        "[docs/examples.md](../docs/examples.md).",
        "",
        "```",
        "uv run python examples/labs/ospf_ring.py",
        "```",
        "",
        "This page is generated: `uv run python scripts/examples.py index`.",
    ]
    for folder, blurb in FOLDERS.items():
        found = [p for p in scripts() if p.parent.name == folder]
        if not found:
            continue
        out += ["", f"## {folder}", "", blurb, ""]
        out += [f"- [`{p.name}`]({folder}/{p.name}): {summary(p)}" for p in found]
    return "\n".join(out) + "\n"


def build() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    import pktlib

    for path in scripts():
        work = ROOT / "out" / "examples" / path.parent.name
        work.mkdir(parents=True, exist_ok=True)
        os.chdir(work)
        sys.argv = [str(path), *ARGV.get(path.name, [])]
        sys.path.insert(0, str(path.parent))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", pktlib.PktWarning)
            with contextlib.suppress(SystemExit):
                runpy.run_path(str(path), run_name="__main__")
        sys.path.pop(0)
        for pkt in sorted(work.glob("*.pkt")):
            found = pktlib.audit(pktlib.load(pkt))
            print(f"{path.relative_to(EXAMPLES)} -> {pkt.name}: {len(found)} problem(s)")
            for p in found:
                print("    x", p)
    return 0  # some examples fail the audit on purpose (a student file, Pluto); read the list


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "index"
    if what == "index":
        (EXAMPLES / "README.md").write_text(index(), encoding="utf-8")
        print("wrote examples/README.md")
    elif what == "build":
        sys.exit(build())
    else:
        sys.exit(__doc__)
