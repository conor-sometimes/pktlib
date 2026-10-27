"""Build tests/fixtures/routed.pkt, the routed network the reading tests use.

    uv run python scripts/sources/routed.py

Four 1841s: R1, R2 and R3 in a serial chain (the DCE ends are R1 Se0/0/0 and
R2 Se0/0/1), R4 on R2's Fa0/0 with a crossover cable, a PC on R4 with another.
R1 and R3 each have a LAN through a 2960. RIP v2 on every router. R1 Fa0/1 is
left unconfigured. Three notes and three shapes on the workspace.
"""

from pathlib import Path

import pktlib

OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "routed.pkt"

net = pktlib.new(seed=7)
r1 = net.router("R1", "1841+WIC-2T", at=(200, 200))
r2 = net.router("R2", "1841+WIC-2T", at=(450, 200))
r3 = net.router("R3", "1841+WIC-2T", at=(700, 200))
r4 = net.router("R4", "1841", at=(450, 420))
s1 = net.switch("S1", at=(200, 420))
s3 = net.switch("S3", at=(700, 420))
pc1 = net.pc("PC1", at=(200, 600), ip="10.1.0.10/24", gateway="10.1.0.1")
pc3 = net.pc("PC3", at=(700, 600), ip="10.3.0.10/24", gateway="10.3.0.1")
pc4 = net.pc("PC4", at=(450, 600), ip="10.4.0.10/24", gateway="10.4.0.1")

LINKS = [  # (a, port, b, port, a's address, b's address); serial: a is the DCE end
    (r1, "se0/0/0", r2, "se0/0/0", "10.0.12.1/30", "10.0.12.2/30"),
    (r2, "se0/0/1", r3, "se0/0/0", "10.0.23.1/30", "10.0.23.2/30"),
    (r2, "fa0/0", r4, "fa0/0", "10.0.24.1/30", "10.0.24.2/30"),
]
for a, ap, b, bp, aa, ba in LINKS:
    a[ap].connect(b[bp])
    a[ap].address = aa
    b[bp].address = ba
r1["fa0/0"].connect(s1["fa0/1"])
r1["fa0/0"].address = "10.1.0.1/24"
s1["fa0/2"].connect(pc1["fa0"])
r3["fa0/0"].connect(s3["fa0/1"])
r3["fa0/0"].address = "10.3.0.1/24"
s3["fa0/2"].connect(pc3["fa0"])
r4["fa0/1"].connect(pc4["fa0"])
r4["fa0/1"].address = "10.4.0.1/24"
r1.config("interface se0/0/0\n clock rate 64000")
r2.config("interface se0/0/1\n clock rate 64000")

for r in (r1, r2, r3, r4):
    r.config("router rip\n version 2\n network 10.0.0.0\n no auto-summary")

net.note("RIP v2", at=(420, 120))
net.note("LAN 1 10.1.0.0/24", at=(120, 660))
net.note("LAN 3 10.3.0.0/24", at=(640, 660))
net.ellipse(150, 380, 260, 650)
net.ellipse(650, 380, 760, 650)
net.rectangle(160, 150, 750, 250)

if __name__ == "__main__":
    net.save(OUT)
    print("wrote", OUT, pktlib.audit(net) or "audit: clean")
