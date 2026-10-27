"""Five data centres, every one linked to every other.

    uv run python examples/showcase/datacentres.py          # writes datacentres.pkt

  interconnect  a full mesh of serial links between the five border routers
                (2911s with two HWIC-2T cards each): ten links, OSPF area 0
  each site     OSPF area <n>, so every border router is an ABR; two 3650
                cores with an LACP channel, rapid PVST and HSRP gateways; two
                2960 leaves trunked to both cores; a web and a database
                server on each leaf, in VLANs WEB and DB
  addresses     site n: WEB 10.n.10.0/24, DB 10.n.20.0/24, border to cores
                10.n.255.0/30 and .4/30; the mesh link between sites a < b
                is 172.16.<10a+b>.0/30

Change SITES and run it again.
"""

import itertools
import math

import pktlib

SITES = ["DUBLIN", "LONDON", "PARIS", "FRANKFURT", "AMSTERDAM"]
VLANS = {10: "WEB", 20: "DB"}
SERIALS = ["se0/0/0", "se0/0/1", "se0/1/0", "se0/1/1"]
CX, CY, R = 1500, 1100, 520

net = pktlib.new()


def out(angle: float, dist: float, side: float = 0) -> tuple[float, float]:
    """A point `dist` out from the centre along `angle`, `side` to one side."""
    ox, oy = math.cos(angle), math.sin(angle)
    return CX + dist * ox - side * oy, CY + dist * oy + side * ox


borders, angles = {}, {}
for n, site in enumerate(SITES, 1):
    a = 2 * math.pi * (n - 1) / len(SITES) - math.pi / 2
    angles[site] = a
    b = net.router(f"{site}-BR", "2911", at=out(a, R))
    b.add_module("HWIC-2T", slot=(0, 0))
    b.add_module("HWIC-2T", slot=(0, 1))
    b.config(
        f"interface loopback 0\n ip address 10.{n}.254.1 255.255.255.255\n"
        f"router ospf 1\n router-id 10.{n}.254.1\n network 10.{n}.254.1 0.0.0.0 area {n}"
    )
    borders[site] = b

    # the site: two cores, two leaves, four servers
    cores = [net.multilayer(f"{site}-CORE{c}", "3650-24PS", at=out(a, R + 170, 110 * (2 * c - 3))) for c in (1, 2)]
    for c, core in enumerate(cores, 1):
        link = f"10.{n}.255.{4 * (c - 1)}"
        b[f"g0/{c - 1}"].connect(core["g1/0/1"])
        b[f"g0/{c - 1}"].address = f"10.{n}.255.{4 * (c - 1) + 1}/30"
        b.config(f"router ospf 1\n network {link} 0.0.0.3 area {n}")
        cfg = [
            "ip routing",
            "spanning-tree mode rapid-pvst",
            f"spanning-tree vlan 10,20 priority {4096 * c}",
            "interface range g1/0/23 - 24",
            " switchport mode trunk",
            " channel-group 1 mode active",
            "interface port-channel 1",
            " switchport mode trunk",
            "interface range g1/0/2 - 3",
            " switchport mode trunk",
            "interface g1/0/1",
            " no switchport",
            f" ip address 10.{n}.255.{4 * (c - 1) + 2} 255.255.255.252",
            "router ospf 1",
            f" router-id 10.{n}.254.{1 + c}",
            f" network {link} 0.0.0.3 area {n}",
        ]
        for vid, name in VLANS.items():
            cfg += [
                f"vlan {vid}",
                f" name {name}",
                f"interface vlan {vid}",
                f" ip address 10.{n}.{vid}.{1 + c} 255.255.255.0",
                f" standby 1 ip 10.{n}.{vid}.1",
                f" standby 1 priority {110 if c == 1 else 100}",
                " standby 1 preempt",
                "router ospf 1",
                f" network 10.{n}.{vid}.0 0.0.0.255 area {n}",
            ]
        core.config(cfg)
    cores[0]["g1/0/23"].connect(cores[1]["g1/0/23"])
    cores[0]["g1/0/24"].connect(cores[1]["g1/0/24"])

    for l in (1, 2):
        leaf = net.switch(f"{site}-LEAF{l}", at=out(a, R + 330, 130 * (2 * l - 3)))
        leaf.config("interface range g0/1 - 2\n switchport mode trunk")
        for c, core in enumerate(cores):
            leaf[f"g0/{c + 1}"].connect(core[f"g1/0/{1 + l}"])
        for k, (vid, role) in enumerate(VLANS.items()):
            host = 10 + l  # WEB1 .11, WEB2 .12 ...
            srv = net.server(
                f"{site}-{role}{l}",
                at=out(a, R + 470, 130 * (2 * l - 3) + 55 * (2 * k - 1)),
                ip=f"10.{n}.{vid}.{host}/24",
                gateway=f"10.{n}.{vid}.1",
            )
            leaf[f"fa0/{k + 1}"].connect(srv["fa0"])
            leaf.config(f"interface fa0/{k + 1}\n switchport mode access\n switchport access vlan {vid}")

    site_devs = [b, *cores] + [d for d in net.devices if d.name.startswith(f"{site}-") and d not in (b, *cores)]
    net.around(*site_devs, shape="rectangle", outline="blue", label=f"{site}: OSPF area {n}", pad=45)

# the mesh: every pair of sites, DCE at the lower-numbered end
used = dict.fromkeys(SITES, 0)
for (i, sa), (j, sb) in itertools.combinations(enumerate(SITES, 1), 2):
    pa, pb = SERIALS[used[sa]], SERIALS[used[sb]]
    used[sa] += 1
    used[sb] += 1
    subnet = f"172.16.{10 * i + j}"
    borders[sa][pa].connect(borders[sb][pb])
    borders[sa][pa].address = f"{subnet}.1/30"
    borders[sb][pb].address = f"{subnet}.2/30"
    for b in (borders[sa], borders[sb]):
        b.config(f"router ospf 1\n network {subnet}.0 0.0.0.3 area 0")

net.around(*borders.values(), shape="ellipse", outline="red", label="INTERCONNECT: OSPF area 0, full mesh", pad=60)

# ping checks across the mesh, listed under the workspace
net.ping("DUBLIN-WEB1", "PARIS-WEB1", scenario="Dublin to Paris")
net.ping("DUBLIN-WEB1", "AMSTERDAM-DB2", scenario="Dublin to Amsterdam")
net.ping("LONDON-DB1", "FRANKFURT-WEB2", scenario="London to Frankfurt")

net.save("datacentres.pkt")
print(f"datacentres.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.shapes)} shapes")
