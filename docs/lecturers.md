# For lecturers

**Write labs as scripts.** Addresses come from one table, so changing the number of routers
or VLANs gives a new, correctly numbered network. `examples/labs/router_on_a_stick.py` and
`examples/labs/ospf_ring.py` are good starting sizes.

**Troubleshooting labs with an answer key.** `pktlib.lab` holds the working network, the
checks it must pass, and the faults for the student file. A fault has to fail: the build
writes nothing if a fault breaks nothing, or if the audit gives away a fault you meant to
hide. You get three files: the student file, the solution and the answer key.
`lab.grade("handed_in.pkt")` then runs the same checks on each submission and says why each
failed one failed. `lab.build("lab", pka=True)` also writes lab.pka, the same lab as a Packet
Tracer activity: Check Results grades students on everything the faults changed, so they can
check their own work in Packet Tracer. See `examples/labs/fault_lab.py` and the
[guide](guide.md#labs).

**Packet Tracer activities (.pka).** Build the answer network and the starting network
with one script, then name the items to grade:

```python
from pktlib.activity import make_activity


def lan(done):
    net = pktlib.new()
    r1 = net.router("R1", "2911")
    pc = net.pc("PC1")
    r1["g0/0"].connect(pc["fa0"])
    if done:
        r1["g0/0"].address = "10.0.0.1/24"
        pc.set_ip("10.0.0.10/24", gateway="10.0.0.1")
    return net


items = ["R1 > Ports > GigabitEthernet0/0 > IP Address", "PC1 > Default Gateway"]
make_activity(lan(True), lan(False), items, "Address R1 and PC1.").save("lab.pka")
```

Students open lab.pka in Packet Tracer and Check Results grades them, with no script
needed. `load_activity("lab.pka")` reads an existing activity (instructions, both networks,
the assessed items), and `act.score(pktlib.load("handed_in.pkt"))` checks a plain .pkt
against it. Items: host names, default gateways, port addresses and masks, access VLANs and
port modes, VLAN names, OSPF router IDs and networks, and running-config lines
(`("R1", "Running Configuration", "router ospf 1", "network 10.0.12.0 0.0.0.3 area 0")`).
`tests=[("PC1", "SERVER")]` adds connectivity tests: pings Check Results expects to succeed
(or, with a third value False, to fail).

**Ping checks inside the file.** `net.ping(src, dst)` adds a Simple PDU. Students (or you,
marking) click it in Packet Tracer and see Successful or Failed.

**Old starter files.** A file saved by an older Packet Tracer, such as 6.2, opens with
`pktlib.load` and saves as 8.2, config intact. To add devices, open it in 8.2 and save it
once first.

**With an AI agent.** `.claude/skills/packet-tracer-lab/` is a skill for Claude Code. It asks
what the lab is for, scripts it with pktlib, audits it until it's clean, and hands over the
student file, the solution and an answer key.

Whichever way it's built, open the file in Packet Tracer and run the lab's key ping before
students see it.
