"""A lab: a working network, the checks that prove it works, and faults the
student has to fix.

    from pktlib.lab import Lab

    lab = Lab("Router on a stick")
    sw = lab.net.switch("SW1", at=(600, 260))      # build the WORKING network
    ...
    lab.check("Sales1 is in VLAN 10", lambda n: vlan(n, "fa0/2") == "10")
    lab.fault("Sales2 is in the wrong VLAN",
              brk=lambda n: n.device("SW1").config(["interface fa0/3", " switchport access vlan 20"]),
              fixed=lambda n: vlan(n, "fa0/3") == "10",
              find="`show vlan brief` on SW1: Fa0/3 is under VLAN 20")
    lab.build("lab")         # lab.pkt, lab_solution.pkt, lab_answers.md
    for result in lab.grade("handed_in.pkt"):
        print(result.ok, result.name, result.why)

A fault is a "should fail": `build` refuses to write anything unless every
check passes on the solution, and every fault's `fixed` check FAILS on the
student file. So a fault that breaks nothing, or a break that doesn't do
what the lecturer thinks, is caught before a student sees it. The audit
(pktlib.audit) runs too: it must report exactly the faults marked
`audit_says`, so you know which ones a student can find in one command.
`grade` then runs the same checks on what the student hands back.

A check fails when it returns something falsy, or when it looks up a device
or port the student deleted (a NotFound or other PktError). Any other
exception is a bug in the check itself, and is raised, not marked FAIL.

The faults live in the script and the answer key, never in the .pkt, which
a student could decode.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from ._audit import audit as run_audit
from ._errors import PktError
from ._model import Network, load, new
from .activity import diff_items, make_activity

Check = Callable[[Network], object]  # truthy passes


class Result(NamedTuple):
    """One graded check: its name, whether it passed, and why not ('' if it did)."""

    name: str
    ok: bool
    why: str = ""


@dataclass
class Fault:
    """Something broken in the student file; see Lab.fault()."""

    name: str
    brk: Callable[[Network], object]
    fixed: Check
    find: str = ""
    audit_says: str | None = None  # a line the audit gives for it, or None if the audit can't see it


@dataclass
class Lab:
    """A lab: the working network (`net`), the checks it must pass and the faults
    in the student file. See the module docstring."""

    title: str
    seed: int | None = None
    net: Network = field(init=False)
    checks: list[tuple[str, Check]] = field(default_factory=list)
    faults: list[Fault] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # extra answer key lines: the addressing table, say

    def __post_init__(self) -> None:
        self.net = new(seed=self.seed)

    def check(self, name: str, ok: Check) -> None:
        """Something the finished lab must do; it has to pass on the solution."""
        self.checks.append((name, ok))

    def fault(
        self, name: str, brk: Callable[[Network], object], fixed: Check, find: str = "", audit_says: str | None = None
    ) -> None:
        """Something broken in the student file. `brk` breaks it, `fixed` says
        whether it has been put right, `find` is how a student finds it.
        If the audit reports it, give a piece of that line as `audit_says`."""
        self.faults.append(Fault(name, brk, fixed, find, audit_says))

    def student(self) -> Network:
        """A copy of the solution with every fault applied."""
        net = Network.from_bytes(self.net.to_bytes(), seed=self.seed)
        for f in self.faults:
            f.brk(net)
        return net

    def verify(self, *, audit: bool = True) -> tuple[Network, list[str]]:
        """Build the student network and prove the lab is sound. Returns it with
        the problems found; an empty list means the lab is fit to hand out."""
        problems = [
            f"solution fails: {r.name} ({r.why})"
            for r in (_run(name, ok, self.net) for name, ok in self.checks)
            if not r.ok
        ]
        problems += [
            f"solution fails: {f.name}, its fixed check ({r.why})"
            for f in self.faults
            if not (r := _run(f.name, f.fixed, self.net)).ok
        ]
        student = self.student()
        problems += [
            f"should fail but passes in the student file: {f.name}"
            for f in self.faults
            if _run(f.name, f.fixed, student).ok
        ]
        if audit:
            problems += [f"audit, solution: {line}" for line in run_audit(self.net)]
            said = run_audit(student)
            for f in self.faults:
                if f.audit_says and not any(f.audit_says in line for line in said):
                    problems.append(f"audit doesn't report {f.name!r} (expected {f.audit_says!r})")
            expected = [f.audit_says for f in self.faults if f.audit_says]
            problems += [
                f"audit, student file, not a planned fault: {line}"
                for line in said
                if not any(e in line for e in expected)
            ]
        return student, problems

    def build(
        self,
        stem: str | Path = "lab",
        *,
        audit: bool = True,
        pka: bool | Iterable[str | Sequence[str]] = False,
        pka_tests: Iterable[tuple[str, str] | tuple[str, str, bool]] = (),
    ) -> None:
        """Write STEM.pkt (student), STEM_solution.pkt and STEM_answers.md, or
        raise PktError listing why the lab isn't sound. audit=False skips
        the audit's part of the checks.

        pka=True also writes STEM.pka, a Packet Tracer activity: students start
        from the student file and Check Results grades them against the
        solution, on every item the faults changed (pktlib.activity.diff_items).
        Pass a list of items instead to choose them (see pktlib.activity), and
        pka_tests for connectivity tests (source, destination[, should succeed])."""
        student, problems = self.verify(audit=audit)
        activity = None
        if pka is not False:
            items = diff_items(self.net, student) if pka is True else list(pka)
            if not items:
                problems.append("the faults change nothing a .pka can grade; pass pka=[items] to choose them")
            else:
                text = f"{self.title}. Find and fix what's wrong." if self.faults else self.title
                activity = make_activity(self.net, student, items, text, tests=pka_tests)
        if problems:
            raise PktError("lab not written:\n  " + "\n  ".join(problems))
        stem = Path(stem)
        student.save(stem.with_suffix(".pkt"))
        self.net.save(stem.with_name(stem.name + "_solution.pkt"))
        stem.with_name(stem.name + "_answers.md").write_text(self.answers(audited=audit), encoding="utf-8")
        if activity is not None:
            activity.save(stem.with_suffix(".pka"))

    def answers(self, *, audited: bool = True) -> str:
        """The answer key as Markdown: notes, faults and how to find them, checks."""
        out = [f"# {self.title}: answer key", ""]
        if self.notes:
            out += self.notes + [""]
        if self.faults:
            out += ["## Faults in the student file", ""]
            for i, f in enumerate(self.faults, 1):
                seen = (
                    f'The audit reports it: "{f.audit_says}".'
                    if f.audit_says
                    else "The audit doesn't see it."
                    if audited
                    else ""
                )
                out.append(
                    f"{i}. {f.name}." + (f" Found with {f.find}." if f.find else "") + (f" {seen}" if seen else "")
                )
            out.append("")
        if self.checks:
            out += ["## What the finished lab must do", ""] + [f"- {name}" for name, _ in self.checks] + [""]
        return "\n".join(out)

    def grade(self, path: str | Path) -> list[Result]:
        """Run every check and every fault's fixed check on a handed-in file."""
        net = load(path, strict=False)
        results = [_run(name, ok, net) for name, ok in self.checks]
        results += [_run(f"fault: {f.name}", f.fixed, net) for f in self.faults]  # ok: it's been fixed
        return results


def _run(name: str, ok: Check, net: Network) -> Result:
    """A check that looks up something the student deleted fails, with why.
    Any other exception is a bug in the check, and goes up to the lecturer."""
    try:
        return Result(name, ok=True) if ok(net) else Result(name, ok=False, why="check returned false")
    except PktError as e:
        return Result(name, ok=False, why=str(e))
