"""pktlib.lab: faults must really fail in the student file ("should fail"),
the solution must pass, and grading runs the same checks on a handed-in file."""

import runpy
import sys
from pathlib import Path

import pytest

import pktlib
from pktlib import audit
from pktlib.lab import Lab

EXAMPLES = Path(__file__).parents[1] / "examples"


def example(name: str) -> Path:
    """An example script by file name, whichever folder of examples/ it's in."""
    (found,) = EXAMPLES.rglob(name)
    return found


def small_lab() -> Lab:
    lab = Lab("two PCs", seed=3)
    r1 = lab.net.router("R1", at=(100, 0))
    sw = lab.net.switch("SW1", at=(100, 100))
    r1["fa0/0"].connect(sw["fa0/3"])
    r1.config(["interface fa0/0", " ip address 10.0.0.254 255.255.255.0", " no shutdown"])
    for i in (1, 2):
        pc = lab.net.pc(f"PC{i}", at=(100 * i, 200), ip=f"10.0.0.{i}/24", gateway="10.0.0.254")
        pc["fa0"].connect(sw[f"fa0/{i}"])
    return lab


def port_up(n, port):
    return n.device("SW1").interfaces[pktlib.canonical_port(port)][1]


def test_fault_is_applied_to_the_student_copy_only(tmp_path):
    lab = small_lab()
    lab.fault(
        "PC2's port is shut",
        lambda n: n.device("SW1").config(["interface fa0/2", " shutdown"]),
        fixed=lambda n: port_up(n, "fa0/2"),
    )
    lab.build(tmp_path / "lab")
    assert not port_up(pktlib.load(tmp_path / "lab.pkt"), "fa0/2")
    assert port_up(pktlib.load(tmp_path / "lab_solution.pkt"), "fa0/2")
    assert "PC2's port is shut" in (tmp_path / "lab_answers.md").read_text()


def test_a_fault_that_breaks_nothing_stops_the_build(tmp_path):
    lab = small_lab()
    lab.fault("does nothing", lambda n: None, fixed=lambda n: port_up(n, "fa0/2"))
    with pytest.raises(pktlib.PktError, match="should fail but passes"):
        lab.build(tmp_path / "lab")
    assert not (tmp_path / "lab.pkt").exists()


def test_a_check_the_solution_fails_stops_the_build(tmp_path):
    lab = small_lab()
    lab.check("PC3 exists", lambda n: n.device("PC3"))  # raises: counts as a fail
    with pytest.raises(pktlib.PktError, match="solution fails: PC3 exists"):
        lab.build(tmp_path / "lab")


def test_audit_must_report_exactly_the_planned_faults(tmp_path):
    lab = small_lab()
    lab.fault(
        "PC2's gateway is wrong",
        lambda n: n.device("PC2").set_ip("10.0.0.2/24", gateway="10.0.0.99"),
        fixed=lambda n: n.device("PC2").gateway == "10.0.0.254",
    )
    # the audit reports a gateway nobody owns, and this fault didn't say it would
    with pytest.raises(pktlib.PktError, match="not a planned fault"):
        lab.build(tmp_path / "lab")
    lab.faults[0].audit_says = "PC2's gateway"
    lab.build(tmp_path / "lab")
    lab.faults[0].audit_says = "something else"
    with pytest.raises(pktlib.PktError, match="audit doesn't report"):
        lab.build(tmp_path / "lab")


def test_grade_a_fixed_file(tmp_path):
    lab = small_lab()
    lab.fault(
        "PC2's port is shut",
        lambda n: n.device("SW1").config(["interface fa0/2", " shutdown"]),
        fixed=lambda n: port_up(n, "fa0/2"),
    )
    lab.build(tmp_path / "lab")
    assert lab.grade(tmp_path / "lab.pkt") == [("fault: PC2's port is shut", False, "check returned false")]
    student = pktlib.load(tmp_path / "lab.pkt")
    student.device("SW1").config(["interface fa0/2", " no shutdown"])
    student.save(tmp_path / "handed_in.pkt")
    assert lab.grade(tmp_path / "handed_in.pkt") == [("fault: PC2's port is shut", True, "")]


def test_a_deleted_device_fails_with_why_but_a_broken_check_raises(tmp_path):
    lab = small_lab()
    lab.check("PC2 is there", lambda n: n.device("PC2"))
    lab.build(tmp_path / "lab", audit=False)
    student = pktlib.load(tmp_path / "lab.pkt")
    student.remove_device("PC2")
    student.save(tmp_path / "handed_in.pkt")
    (result,) = lab.grade(tmp_path / "handed_in.pkt")
    assert not result.ok and "no device called 'PC2'" in result.why
    lab.check("typo in the check", lambda n: n.devcie("PC2"))  # ty: ignore[unresolved-attribute]
    with pytest.raises(AttributeError):
        lab.grade(tmp_path / "handed_in.pkt")


def test_fault_lab_example(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["fault_lab.py"])
    runpy.run_path(str(example("fault_lab.py")), run_name="__main__")
    assert audit(pktlib.load(tmp_path / "fault_lab_solution.pkt")) == []
    said = audit(pktlib.load(tmp_path / "fault_lab.pkt"))
    assert len(said) == 1 and "Tech1's gateway" in said[0]


def test_build_writes_a_pka_grading_what_the_faults_broke(tmp_path):
    """Checked in Packet Tracer 8.2 (27 Oct 2026) with examples/labs/fault_lab.py: the
    .pka opened with the two faults as its items and both pings as connectivity tests,
    all Incorrect; after fixing Fa0/3's VLAN on SW1's CLI and Tech1's gateway in its IP
    Configuration, Check Results said "You completed the activity"."""
    from pktlib.activity import load_activity

    lab = small_lab()
    lab.fault(
        "PC2's gateway is wrong",
        lambda n: n.device("PC2").set_ip("10.0.0.2/24", gateway="10.0.0.99"),
        fixed=lambda n: n.device("PC2").gateway == "10.0.0.254",
    )
    lab.build(tmp_path / "lab", audit=False, pka=True, pka_tests=[("PC1", "PC2")])
    act = load_activity(tmp_path / "lab.pka")
    assert [(i.path, i.expected, i.initial) for i in act.items] == [
        (("PC2", "Default Gateway"), "10.0.0.254", "10.0.0.99")
    ]
    assert act.tests == [("PC1", "PC2", True)]
    assert act.instructions == ["two PCs. Find and fix what's wrong."]
    assert [ok for _, ok in act.score(pktlib.load(tmp_path / "lab_solution.pkt"))] == [True]
    assert [ok for _, ok in act.score(pktlib.load(tmp_path / "lab.pkt"))] == [False]


def test_build_pka_with_chosen_items_or_none(tmp_path):
    from pktlib.activity import load_activity

    lab = small_lab()
    lab.build(tmp_path / "lab", audit=False, pka=["PC1 > Ports > FastEthernet0 > IP Address"])
    assert [i.expected for i in load_activity(tmp_path / "lab.pka").items] == ["10.0.0.1"]
    # no faults and nothing chosen: there's nothing to grade, so nothing is written
    with pytest.raises(pktlib.PktError, match=r"nothing a \.pka can grade"):
        small_lab().build(tmp_path / "empty", audit=False, pka=True)
    assert not (tmp_path / "empty.pkt").exists()
