"""Audit a folder of handed-in .pkt files and print one table row per student.

    uv run python examples/recipes/audit_folder.py           # makes handins/ with five samples
    uv run python examples/recipes/audit_folder.py ~/marking/lab3

Shows: `pktlib.load` on every file in a folder, `net.profile` (the name a student
set under Options > User Profile), and `pktlib.audit`, whose problems name the
devices involved. A file pktlib can't read (damaged, not a .pkt) gets a row too,
from the `pktlib.FileFormatError` it raises.
"""

import sys
from pathlib import Path

import pktlib


def sample(folder: Path) -> None:
    """Five hand-ins of one lab (two PCs, a switch, a router), each with its own slip."""
    folder.mkdir(exist_ok=True)
    slips = {
        "aoife": None,  # a clean one
        "bryan": "duplicate",
        "ciara": "gateway",
        "dmitri": "shut",
        "eve": "damaged",
    }
    for student, slip in slips.items():
        if slip == "damaged":  # not a .pkt at all, as when a hand-in is cut off
            (folder / f"{student}.pkt").write_bytes(b"this is not a packet tracer file")
            continue
        net = pktlib.new(seed=len(student))
        net.profile = pktlib.Profile(student.title(), f"{student}@example.com")
        r1 = net.router("R1", "1941", at=(300, 100))
        sw = net.switch("SW1", at=(300, 220))
        sw["g0/1"].connect(r1["g0/0"])
        if slip != "shut":  # forgetting the address leaves the port shut down
            r1["g0/0"].address = "192.168.1.1/24"
        for i in (1, 2):
            ip = "192.168.1.10" if slip == "duplicate" else f"192.168.1.{9 + i}"
            gw = "192.168.1.254" if slip == "gateway" and i == 2 else "192.168.1.1"
            pc = net.pc(f"PC{i}", at=(200 * i, 340), ip=f"{ip}/24", gateway=gw)
            sw[f"fa0/{i}"].connect(pc["fa0"])
        net.ping("PC1", "PC2", ip="192.168.1.11", scenario="PC1 to PC2")
        net.save(folder / f"{student}.pkt")


if len(sys.argv) > 1:
    folder = Path(sys.argv[1]).expanduser()
else:
    folder = Path("handins")
    sample(folder)

print(f"{'file':20} {'student':10} {'devices':>7} {'problems':>8}  first problem")
for path in sorted(folder.glob("*.pkt")):
    try:
        net = pktlib.load(path, strict=False)  # strict=False: read files from a newer Packet Tracer too
    except pktlib.FileFormatError as e:
        print(f"{path.name:20} {'?':10} {'':>7} {'':>8}  can't read it: {e}")
        continue
    problems = pktlib.audit(net)
    first = problems[0] if problems else "nothing found"
    print(f"{path.name:20} {net.profile.name or '?':10} {len(net):>7} {len(problems):>8}  {first}")
