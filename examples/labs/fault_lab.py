"""A troubleshooting lab: router on a stick with two faults to find.

    uv run python examples/labs/fault_lab.py

Writes fault_lab.pkt (for students), fault_lab_solution.pkt,
fault_lab_answers.md and fault_lab.pka (the same lab as a Packet Tracer
activity: Check Results grades what the faults broke, plus two pings).
Nothing is written unless each fault really breaks something in the
student file and the solution passes every check.
Mark a handed-in file:

    uv run python examples/labs/fault_lab.py handed_in.pkt
"""

import ipaddress
import sys

from pktlib.lab import Lab

VLANS = {10: "Sales", 20: "Tech"}

lab = Lab("Router on a stick: find the faults", seed=1)
net = lab.net
r1 = net.router("R1", at=(600, 120))
sw = net.switch("SW1", at=(600, 260))
r1["fa0/0"].connect(sw["fa0/1"])
sw_cfg = ["interface fa0/1", " switchport mode trunk"]
r1_cfg = ["interface fa0/0", " no shutdown"]
lab.notes += ["| Device | Port | Address | VLAN |", "|---|---|---|---|"]
port = 2
for vid, name in VLANS.items():
    lan = ipaddress.ip_network(f"192.168.{vid}.0/24")
    gw, *hosts = lan.hosts()
    sw_cfg += [f"vlan {vid}", f" name {name}"]
    r1_cfg += [f"interface fa0/0.{vid}", f" encapsulation dot1Q {vid}", f" ip address {gw} {lan.netmask}"]
    lab.notes.append(f"| R1 | Fa0/0.{vid} | {gw}/24 | {vid} |")
    for j in range(2):
        pc = net.pc(f"{name}{j + 1}", at=(300 + (port - 2) * 150, 420), ip=f"{hosts[j]}/24", gateway=str(gw))
        sw[f"fa0/{port}"].connect(pc["fa0"])
        sw_cfg += [f"interface fa0/{port}", " switchport mode access", f" switchport access vlan {vid}"]
        lab.notes.append(f"| {pc.name} | SW1 Fa0/{port} | {hosts[j]}/24, gateway {gw} | {vid} |")
        port += 1
sw.config(sw_cfg)
r1.config(r1_cfg)
# ping checks: all succeed in the solution; the faults break the first two in the student file
net.ping("Sales2", "Sales1", scenario="Sales2 to Sales1")
net.ping("Tech1", "Sales1", scenario="Tech1 off its own subnet (needs its gateway)")
net.ping("Sales1", "Tech2", scenario="Sales to Tech (routed on R1)")


for p, vid in (("fa0/2", 10), ("fa0/3", 10), ("fa0/4", 20), ("fa0/5", 20)):
    lab.check(f"SW1 {p} is an access port in VLAN {vid}", lambda n, p=p, vid=vid: n["SW1"][p].access_vlan == vid)
lab.check("Fa0/1 trunks to R1", lambda n: n["SW1"]["fa0/1"].mode == "trunk")

# The faults. Each one's `fixed` check must fail in the student file, or the lab isn't written.
lab.fault(
    "Sales2's switch port is in VLAN 20, not 10",
    brk=lambda n: n.device("SW1").config(["interface fa0/3", " switchport access vlan 20"]),
    fixed=lambda n: n["SW1"]["fa0/3"].access_vlan == 10,
    find="`show vlan brief` on SW1",
)
lab.fault(
    "Tech1's default gateway is 192.168.20.254, not 192.168.20.1",
    brk=lambda n: n.device("Tech1").set_ip("192.168.20.2/24", gateway="192.168.20.254"),
    fixed=lambda n: n.device("Tech1").gateway == "192.168.20.1",
    find="`ipconfig` on Tech1",
    audit_says="Tech1's gateway 192.168.20.254",
)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for result in lab.grade(sys.argv[1]):
            print(f"  {'PASS' if result.ok else 'FAIL'}  {result.name}" + (f"  ({result.why})" if result.why else ""))
    else:
        lab.build("fault_lab", pka=True, pka_tests=[("Sales2", "Sales1"), ("Tech1", "Sales1")])
        print("wrote fault_lab.pkt, fault_lab_solution.pkt, fault_lab_answers.md and fault_lab.pka")
