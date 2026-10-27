"""Generate N random subnetting labs, each with a student file, a solution and an answer key.

    uv run python examples/recipes/random_labs.py            # 5 labs in practice/
    uv run python examples/recipes/random_labs.py 30         # one per student

Each lab is one router with three LANs of random sizes and a random /24 to
carve up with VLSM. The student file is cabled but unaddressed; the solution
has every address in; the answer key has the subnet table. Lab n is built
from `random.Random(n)` and `pktlib.new(seed=n)`, so the same number always
gives the same lab: hand lab 7 to a student and mark it against lab 7.

Shows: one function that builds a lab from a seed, and `Network.from_bytes`
to copy the student file and fill the answers into the copy.
"""

import ipaddress
import random
import sys
from pathlib import Path

import pktlib

DEPARTMENTS = ["SALES", "TECH", "ADMIN", "LAB", "GUEST", "HR", "STORES", "STUDIO"]


def vlsm(base: ipaddress.IPv4Network, needs: dict[str, int]) -> dict[str, ipaddress.IPv4Network]:
    """Biggest LAN first, each the smallest subnet that fits its hosts plus network and broadcast."""
    out, start = {}, int(base.network_address)
    for name, hosts in sorted(needs.items(), key=lambda kv: -kv[1]):
        prefix = 32 - (hosts + 1).bit_length()
        out[name] = ipaddress.IPv4Network(f"{ipaddress.IPv4Address(start)}/{prefix}")
        start += out[name].num_addresses
    return out


def build(n: int) -> tuple[pktlib.Network, pktlib.Network, list[str]]:
    rng = random.Random(n)
    base = ipaddress.IPv4Network(f"192.168.{rng.randrange(1, 255)}.0/24")
    lans = rng.sample(DEPARTMENTS, 3)
    needs = {lan: rng.choice([5, 10, 12, 20, 25, 30, 50, 60, 100]) for lan in lans}
    while sum(2 ** (h + 1).bit_length() for h in needs.values()) > 256:  # keep it inside one /24
        needs = {lan: max(5, h // 2) for lan, h in needs.items()}
    plan = vlsm(base, needs)

    student = pktlib.new(seed=n)  # cabled, nothing addressed
    r1 = student.router("R1", "2911", at=(400, 100))
    key = [f"Lab {n}: split {base} with VLSM for {', '.join(f'{lan} ({needs[lan]} hosts)' for lan in lans)}.", ""]
    key.append(f"{'LAN':8} {'needs':>5}  {'subnet':18} {'mask':16} {'gateway (R1)':14} PC")
    answers = {}
    for i, lan in enumerate(lans):
        subnet = plan[lan]
        gw, pc_ip = next(subnet.hosts()), subnet.broadcast_address - 1  # PC on the last usable address
        sw = student.switch(f"{lan}-SW", at=(150 + 250 * i, 230))
        pc = student.pc(f"{lan}-PC", at=(150 + 250 * i, 360))
        sw["g0/1"].connect(r1[f"g0/{i}"])
        sw["fa0/1"].connect(pc["fa0"])
        answers[lan] = (f"g0/{i}", f"{gw}/{subnet.prefixlen}", f"{pc_ip}/{subnet.prefixlen}", str(gw))
        key.append(f"{lan:8} {needs[lan]:>5}  {subnet!s:18} {subnet.netmask!s:16} {gw!s:14} {pc_ip}")
    first, last = lans[0], lans[-1]
    student.ping(f"{first}-PC", f"{last}-PC", ip=answers[last][2].split("/")[0], scenario=f"{first} to {last}")

    solution = pktlib.Network.from_bytes(student.to_bytes(), seed=n)  # a copy, then the answers in it
    for lan, (port, router_ip, pc_ip, gw) in answers.items():
        solution["R1"][port].address = router_ip
        solution[f"{lan}-PC"].set_ip(pc_ip, gw)
    return student, solution, key


count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
out = Path("practice")
out.mkdir(exist_ok=True)
for n in range(1, count + 1):
    student, solution, key = build(n)
    student.save(out / f"lab{n:02}.pkt")
    solution.save(out / f"lab{n:02}_solution.pkt")
    (out / f"lab{n:02}_answers.txt").write_text("\n".join(key) + "\n")
    print(key[0])
print(f"wrote {count} labs into {out}/")
