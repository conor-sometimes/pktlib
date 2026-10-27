"""A starship, as a network: decks on VLANs, twin cores, shuttles that dock on serial, and a starbase far away. For fun.

    uv run python examples/showcase/starship.py             # writes starship.pkt

cores      PORT-CORE and STARBOARD-CORE (3650s): an SVI per deck with an
           HSRP gateway, so the ship keeps routing with one core shot away;
           an LACP channel between them and OSPF area 0
decks      BRIDGE, ENGINEERING, SICKBAY, QUARTERS and CARGO, a 2960 each,
           trunked to both cores
airlock    an ACL on CARGO's gateway: cargo bots reach the quarters and the
           sickbay, never the bridge or engineering
hangar     a 2911 routed to both cores; two shuttles (1841s) docked on
           serial links, each with a pilot on board, and a long serial
           "subspace relay" to STARBASE and its archive server
addresses  deck VLAN n is 10.47.n.0/24 (gateway .1); shuttle n flies
           10.48.n.0/24; the starbase is 10.99.0.0/24

Check in Packet Tracer:
  PORT-CORE# show standby brief        -> Active on every deck
  PORT-CORE# show etherchannel summary -> Po1(SU)
  HANGAR# show ip ospf neighbor        -> both cores, both shuttles and STARBASE FULL
  CAPTAIN ping 10.99.0.10 (ARCHIVE)    -> to the starbase over the relay
  CARGO-BOT1 ping 10.47.10.10 (CAPTAIN) -> fails at the airlock
  Pull the cable between HANGAR and PORT-CORE: pings still work through STARBOARD-CORE.
  Or click the ping scenarios under the workspace.
"""

import pktlib

DECKS = {
    10: ("BRIDGE", ["CAPTAIN", "HELM", "SCIENCE"]),
    20: ("ENGINEERING", ["CHIEF-ENGINEER", "WARP-MONITOR"]),
    30: ("SICKBAY", ["DOCTOR", "BIOBED"]),
    40: ("QUARTERS", ["CREW1", "CREW2", "CREW3"]),
    50: ("CARGO", ["CARGO-BOT1", "CARGO-BOT2"]),
}
COLOURS = {10: "blue", 20: "red", 30: "teal", 40: "green", 50: "orange"}

net = pktlib.new()

# the hull, drawn first so everything sits on top of it
net.ellipse(60, 160, 1500, 760, outline="grey")
net.note("STARSHIP PACKET TRACER  (NCC-8200)", at=(620, 780))

# --- twin cores -----------------------------------------------------------------
cores = [
    net.multilayer("PORT-CORE", "3650-24PS", at=(560, 300)),
    net.multilayer("STARBOARD-CORE", "3650-24PS", at=(960, 300)),
]
for c, core in enumerate(cores, 1):
    cfg = [
        "ip routing",
        "spanning-tree mode rapid-pvst",
        f"spanning-tree vlan {','.join(map(str, DECKS))} priority {4096 * c}",
        "interface range g1/0/23 - 24",
        " switchport mode trunk",
        " channel-group 1 mode active",
        "interface port-channel 1",
        " switchport mode trunk",
        "interface g1/0/1",
        " no switchport",
        f" ip address 10.47.255.{4 * c - 2} 255.255.255.252",
        "interface range g1/0/2 - 6",
        " switchport mode trunk",
        "ip access-list extended AIRLOCK",
        " deny ip any 10.47.10.0 0.0.0.255",
        " deny ip any 10.47.20.0 0.0.0.255",
        " permit ip any any",
        "router ospf 1",
        f" router-id 10.47.254.{c}",
        f" network 10.47.255.{4 * (c - 1)} 0.0.0.3 area 0",
    ]
    for vid, (deck, _) in DECKS.items():
        cfg += [
            f"vlan {vid}",
            f" name {deck}",
            f"interface vlan {vid}",
            f" ip address 10.47.{vid}.{1 + c} 255.255.255.0",
            f" standby 1 ip 10.47.{vid}.1",
            f" standby 1 priority {110 if c == 1 else 100}",
            " standby 1 preempt",
            *([" ip access-group AIRLOCK in"] if deck == "CARGO" else []),
            "router ospf 1",
            f" network 10.47.{vid}.0 0.0.0.255 area 0",
        ]
    core.config(cfg)
cores[0]["g1/0/23"].connect(cores[1]["g1/0/23"])
cores[0]["g1/0/24"].connect(cores[1]["g1/0/24"])

# --- decks ---------------------------------------------------------------------
# the bridge up front (left), engineering at the back, the rest along the hull
PLACES = {10: (150, 420), 20: (1200, 420), 30: (420, 560), 40: (700, 560), 50: (980, 560)}
for d, (vid, (deck, crew)) in enumerate(DECKS.items()):
    x, y = PLACES[vid]
    sw = net.switch(f"{deck}-SW", at=(x + 40 * (len(crew) - 1), y))
    for c, core in enumerate(cores):
        sw[f"g0/{c + 1}"].connect(core[f"g1/0/{2 + d}"])
    sw.config("spanning-tree mode rapid-pvst\ninterface range g0/1 - 2\n switchport mode trunk")
    members = [sw]
    for i, name in enumerate(crew):
        make = net.laptop if deck == "QUARTERS" else net.pc
        h = make(name, at=(x + 80 * i, y + 110), ip=f"10.47.{vid}.{10 + i}/24", gateway=f"10.47.{vid}.1")
        sw[f"fa0/{i + 1}"].connect(h["fa0"])
        sw.config(f"interface fa0/{i + 1}\n switchport mode access\n switchport access vlan {vid}")
        members.append(h)
    net.around(*members, shape="rectangle", outline=COLOURS[vid], label=f"{deck} (VLAN {vid})", pad=25)

# --- hangar, shuttles and the starbase -----------------------------------------------
hangar = net.router("HANGAR", "2911", at=(760, 190))
hangar.add_module("HWIC-2T", slot=(0, 0))  # the shuttles
hangar.add_module("HWIC-2T", slot=(0, 1))  # the subspace relay
for c, core in enumerate(cores, 1):
    hangar[f"g0/{c - 1}"].connect(core["g1/0/1"])
    hangar[f"g0/{c - 1}"].address = f"10.47.255.{4 * c - 3}/30"
hangar.config("""
router ospf 1
 router-id 10.47.254.10
 network 10.47.255.0 0.0.0.7 area 0
 network 10.48.255.0 0.0.0.255 area 0
""")

shuttles = []
for n in (1, 2):
    sh = net.router(f"SHUTTLE{n}", "1841+WIC-2T", at=(1650, 80 + 200 * (n - 1)))
    pilot = net.laptop(f"PILOT{n}", at=(1830, 80 + 200 * (n - 1)), ip=f"10.48.{n}.10/24", gateway=f"10.48.{n}.1")
    hangar[f"se0/0/{n - 1}"].connect(sh["se0/0/0"])  # docked: the hangar is the DCE end
    hangar[f"se0/0/{n - 1}"].address = f"10.48.255.{4 * n - 3}/30"
    sh["se0/0/0"].address = f"10.48.255.{4 * n - 2}/30"
    sh["fa0/0"].connect(pilot["fa0"])
    sh["fa0/0"].address = f"10.48.{n}.1/24"
    sh.config(f"""
router ospf 1
 router-id 10.48.254.{n}
 network 10.48.255.{4 * n - 4} 0.0.0.3 area 0
 network 10.48.{n}.0 0.0.0.255 area 0
""")
    shuttles += [sh, pilot]

starbase = net.router("STARBASE", "1841+WIC-2T", at=(300, -20))
archive = net.server("ARCHIVE", at=(100, -20), ip="10.99.0.10/24", gateway="10.99.0.1")
hangar["se0/1/0"].connect(starbase["se0/0/0"])
hangar["se0/1/0"].address = "10.48.255.9/30"
starbase["se0/0/0"].address = "10.48.255.10/30"
starbase["fa0/0"].connect(archive["fa0"])
starbase["fa0/0"].address = "10.99.0.1/24"
starbase.config("""
router ospf 1
 router-id 10.99.254.1
 network 10.48.255.8 0.0.0.3 area 0
 network 10.99.0.0 0.0.0.255 area 0
""")

# --- drawings --------------------------------------------------------------------
net.around(*cores, hangar, shape="ellipse", outline="purple", label="WARP CORE: HSRP + OSPF", pad=30)
net.around(*shuttles, shape="rectangle", outline="grey", label="SHUTTLES (docked on serial)", pad=35)
net.around(starbase, archive, shape="ellipse", outline="yellow", label="STARBASE, many parsecs away", pad=40)
net.note("CARGO is behind the AIRLOCK ACL:\nno bots on the bridge.", at=(1150, 680))

# --- ping checks -------------------------------------------------------------------
for deck, crew in DECKS.values():
    if deck != "BRIDGE":
        net.ping("CAPTAIN", crew[0], scenario="Bridge to every deck")
net.ping("PILOT1", "CAPTAIN", scenario="Shuttles to the bridge")
net.ping("PILOT2", "CHIEF-ENGINEER", scenario="Shuttles to the bridge")
net.ping("PILOT1", "PILOT2", scenario="Shuttles to the bridge")
net.ping("CAPTAIN", "ARCHIVE", scenario="Ship to starbase")
net.ping("DOCTOR", "ARCHIVE", scenario="Ship to starbase")
net.ping("CARGO-BOT1", "CREW1", scenario="Cargo bay to quarters")
net.ping("CARGO-BOT1", "CAPTAIN", scenario="Cargo bay to bridge and engineering: should FAIL")
net.ping("CARGO-BOT2", "WARP-MONITOR", scenario="Cargo bay to bridge and engineering: should FAIL")

net.save("starship.pkt")
print(f"starship.pkt: {len(net.devices)} devices, {len(net.links)} links, {len(net.pdus)} ping checks")
