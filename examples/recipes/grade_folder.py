"""Grade a folder of submissions against a `pktlib.Lab` and print a mark sheet.

    uv run python examples/recipes/grade_folder.py           # makes submissions/ with four samples
    uv run python examples/recipes/grade_folder.py ~/marking/lab4

Shows: defining a lab once (the working network, its checks, the faults in the
student file), `lab.build()` to write the files you hand out, and
`lab.grade(path)` on every submission, which runs the checks plus each
fault's "fixed" check and says why each failed one failed.
"""

import sys
from pathlib import Path

import pktlib

# --- the lab: the same script that made the hand-out marks it -------------------
lab = pktlib.Lab("Two VLANs on a stick", seed=7)
net = lab.net
r1 = net.router("R1", "2911", at=(400, 100))
sw = net.switch("SW1", at=(400, 220))
r1["g0/0"].connect(sw["g0/1"])
r1.config(
    "interface g0/0\n no shutdown\n"
    + "".join(f"interface g0/0.{v}\n encapsulation dot1Q {v}\n ip address 10.0.{v}.1 255.255.255.0\n" for v in (10, 20))
)
sw.config("interface g0/1\n switchport mode trunk")
for i, (name, vid) in enumerate((("SALES1", 10), ("SALES2", 10), ("TECH1", 20)), 1):
    pc = net.pc(name, at=(150 + 200 * (i - 1), 340), ip=f"10.0.{vid}.{10 + i}/24", gateway=f"10.0.{vid}.1")
    sw[f"fa0/{i}"].connect(pc["fa0"])
    sw.config(f"interface fa0/{i}\n switchport mode access\n switchport access vlan {vid}")
net.ping("SALES1", "TECH1", scenario="Sales to tech, through R1")

lab.check("SW1 Gi0/1 trunks to R1", lambda n: n["SW1"]["g0/1"].mode == "trunk")
lab.check("SALES2 is cabled to SW1 Fa0/2", lambda n: n["SALES2"]["fa0"].peer == n["SW1"]["fa0/2"])
lab.check("R1 routes VLAN 20", lambda n: n["R1"].interfaces["GigabitEthernet0/0.20"].address == "10.0.20.1/24")
lab.fault(
    "SALES2's switch port is in VLAN 20",
    brk=lambda n: n["SW1"].config("interface fa0/2\n switchport access vlan 20"),
    fixed=lambda n: n["SW1"]["fa0/2"].access_vlan == 10,
    find="`show vlan brief` on SW1",
)
lab.fault(
    "TECH1's gateway is 10.0.20.254",
    brk=lambda n: n["TECH1"].set_ip("10.0.20.13/24", "10.0.20.254"),
    fixed=lambda n: n["TECH1"].gateway == "10.0.20.1",
    find="`ipconfig` on TECH1",
    audit_says="TECH1's gateway 10.0.20.254",
)


def sample(folder: Path) -> None:
    """Four submissions: every fault fixed, one fixed, none fixed, and one that deleted a PC."""
    lab.build("lab")  # lab.pkt, lab_solution.pkt, lab_answers.md: what you hand out
    folder.mkdir(exist_ok=True)
    for student in ("niamh", "oisin", "padraig", "roisin"):
        work = lab.student()  # the hand-out, in memory, as the student got it
        if student in ("niamh", "oisin"):
            work["SW1"].config("interface fa0/2\n switchport access vlan 10")
        if student == "niamh":
            work["TECH1"].gateway = "10.0.20.1"
        if student == "roisin":
            work.remove_device("SALES2")
        work.save(folder / f"{student}.pkt")


if len(sys.argv) > 1:
    folder = Path(sys.argv[1]).expanduser()
else:
    folder = Path("submissions")
    sample(folder)

total = len(lab.checks) + len(lab.faults)
for path in sorted(folder.glob("*.pkt")):
    try:
        results = lab.grade(path)
    except pktlib.FileFormatError as e:
        print(f"{path.stem}: can't read it ({e})")
        continue
    passed = sum(r.ok for r in results)
    print(f"{path.stem}: {passed}/{total}")
    for r in results:
        if not r.ok:
            print(f"    FAIL  {r.name}" + (f"  ({r.why})" if r.why else ""))
