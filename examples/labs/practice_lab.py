"""A random routing lab to practise on, plus its answer key.

    uv run python examples/labs/practice_lab.py            # a new lab every time
    uv run python examples/labs/practice_lab.py 42         # lab number 42, same every time

Builds a chain of 3-5 routers (serial links) with a LAN and a PC on each end,
everything cabled, PCs addressed, routers left blank. Configure the routers
in Packet Tracer, save, then check your work:

    uv run pktlib audit practice_lab.pkt
"""

import ipaddress
import random
import sys

import pktlib

seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1000)
rng = random.Random(seed)
n = rng.randint(3, 5)
protocol = rng.choice(["RIP v2", "OSPF area 0", "EIGRP 100", "static routes"])
base = rng.choice(["10.{}.0.0", "172.{}.0.0", "192.168.{}.0"])
nets = [ipaddress.ip_network(base.format(rng.randrange(1, 200) + i) + "/24") for i in range(2 * n + 1)]
it = iter(nets)

net = pktlib.new(seed=seed)
key = [f"Practice lab {seed}: {n} routers, use {protocol}.", ""]
routers = [net.router(f"R{i + 1}", "1841+WIC-2T", at=(200 + i * 220, 360)) for i in range(n)]

for i, r in enumerate(routers):
    if i in (0, n - 1):
        lan = next(it)
        gw, host = list(lan.hosts())[:2]
        sw = net.switch(f"SW{i + 1}", at=(200 + i * 220, 220))
        pc = net.pc(f"PC{i + 1}", at=(200 + i * 220, 90), ip=f"{host}/24", gateway=str(gw))
        pc["fa0"].connect(sw["fa0/1"])
        sw["fa0/2"].connect(r["fa0/0"])
        key.append(f"{r.name} fa0/0  {gw}/24   (LAN with {pc.name} {host})")
for i in range(n - 1):
    wan = next(it)
    a, b = list(wan.hosts())[:2]
    routers[i]["se0/0/0"].connect(routers[i + 1]["se0/0/1"])
    key.append(f"{routers[i].name} se0/0/0 {a}/24 (DCE, clock rate)  <->  {routers[i + 1].name} se0/0/1 {b}/24")

# the ping that proves the lab is done: it fails until you've addressed and routed R1..Rn
net.ping("PC1", f"PC{n}", scenario="End to end: fails until you finish")

net.save("practice_lab.pkt")
with open("practice_lab_answers.txt", "w") as f:
    f.write("\n".join(key) + "\n")
print(key[0])
print("wrote practice_lab.pkt and practice_lab_answers.txt (don't peek)")
