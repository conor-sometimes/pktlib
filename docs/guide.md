# Guide

Everything here is importable from `pktlib`. Each section starts with the common case.

## Files

```python
net = pktlib.new()  # a blank 8.2 workspace
net.save("lab.pkt")
net = pktlib.load("lab.pkt")  # any path or os.PathLike
```

- `pktlib.new(seed=None, edition="8.2")`: `seed` makes MACs and IDs repeatable, so the same
  script writes the same bytes.
- `pktlib.load(path, seed=None, strict=True)`: `strict=False` reads a file from a Packet
  Tracer newer than pktlib knows (see [editions](packet-tracer.md#editions)).
- `net.to_bytes()`, `net.to_xml()`, `Network.from_bytes(...)`, `Network.from_xml(...)`.
- `pktlib.decode(data)` / `pktlib.encode(xml)`: the file's raw XML.
- `net.version`, `net.edition`.

Options after the first argument are keyword-only throughout.

## Devices

```python
r1 = net.router("R1", "2911", at=(300, 200))
sw = net.switch("SW1")  # no at=: the next free spot on a grid
pc = net.pc("PC1", ip="10.0.0.5/24", gateway="10.0.0.1")
ap = net.add_device("AP1", "AccessPoint-PT-AC", at=(500, 200))
```

- Factories: `router`, `switch`, `multilayer`, `pc`, `laptop`, `server`, `printer`,
  `phone(name, power_adapter=False)`, and `add_device(name, model)` for any model.
  `pktlib.models()` lists them. Model names ignore case; a near miss gets a suggestion.
- A network is a collection of devices: `for d in net`, `len(net)`, `net["R1"]`,
  `"R1" in net`, `r1 in net`.
- `net.device(name_or_device)`, `net.remove_device(name_or_device)`. Anything that takes a
  device takes its name too.
- `d.name` (settable; checked like a new name), `d.kind`, `d.model`, `d.xy` (settable),
  `d.hostname`. The name is the label on the workspace; the IOS hostname is separate, so
  renaming a router doesn't change its prompt: `r.config("hostname NEW")` does.
- Two `Device` objects for the same device are equal, so they work in sets and as dict keys.
  The same goes for `Port` and `Link`.

## Ports and cables

```python
pc["fa0"].connect(sw["fa0/1"])  # IOS shorthand works everywhere
link = sw["fa0/1"].link
link.ports  # (Port PC1.FastEthernet0, Port SW1.FastEthernet0/1)
sw["fa0/1"].peer  # Port PC1.FastEthernet0
```

- A device is a collection of ports: `for p in d`, `len(d)`, `"fa0/1" in d`, `d["fa0/1"]`.
- `d.ports` is a read-only mapping of name to Port in IOS order, taking shorthand too.
- `p.connect(other, cable=None)` picks the cable Packet Tracer brings the link up on. Pass
  `cable=` (`"straight"`, `"cross"`, `"serial"`, `"coax"`, `"phone"`) to choose. On a serial
  cable, the port you call `connect` on is the DCE (clock) end.
- `p.disconnect()`, `p.link`, `p.peer`, `p.mac`, `p.module` (the card it's on).
- `net.links`; `link.ports`, `link.other(port)`, `link.cable`, `link.ends` and `link.dce`
  (names, as `End(device, port)`).
- `d.links`, `d.neighbors`.

## Addresses

One format everywhere: `"10.0.0.5/24"`, `"10.0.0.5 255.255.255.0"` or an
`ipaddress.IPv4Interface`.

```python
r1["g0/0"].address = "10.0.0.1/24"  # router: interface, ip address, no shutdown
pc.set_ip("10.0.0.5/24", "10.0.0.1")  # end device: address and gateway
pc.gateway = "10.0.0.254"
pc.dhcp = True  # IP Configuration > DHCP
```

- `p.address`, `p.ip`, `p.mask`, `p.up`.
- `d.set_ip(address, gateway="", port=None)` for end devices. A static address turns DHCP
  off. On a router, set the port's `address` instead.
- `d.use_dhcp(port=None)` for a port other than the first.

## IOS config

```python
r1.config("""
router ospf 1
 network 10.0.0.0 0.0.0.255 area 0
""")
sw.config(["vlan 10", " name SALES"]).config("interface fa0/1\n switchport access vlan 10")
```

`config()` takes the commands you would type after `configure terminal`, as one string or a
list of lines, and returns the device. Packet Tracer replays the saved config when it opens
the file, so pktlib writes it the way IOS saves it:

- commands merge into the existing blocks, in the order Packet Tracer needs;
- tabs count as one space of indent; `exit`, `end` and `conf t` are left out;
- `interface range` is expanded into one block per interface;
- `ip address 10.0.0.1/24` is refused (IOS wants a mask), as is a bad mask;
- on a switch, `vlan N` and `name` go into the VLAN database, `no vlan N` takes N out, and
  `switchport access vlan N` (shorthand too) creates N if it's missing.

Reading:

- `d.running_config` (list of lines), `d.interfaces` (name to `Interface(address, up)`,
  sub-interfaces and SVIs included).
- `p.mode`, `p.access_vlan`, `p.voice_vlan`, `p.setting("clock rate")`.
- `d.interface_config(name)`: an interface's other lines, keyed by the command without its
  value.
- `d.vlans` (number to name, read-only), `d.add_vlan(n, name=None)`, `d.remove_vlan(n)`.
- `d.licenses`, `d.enable_license("securityk9")`.
- `d.generate_rsa_key(1024)` (needs `ip domain-name`), `d.rsa_key` (`RsaKey(name, bits)`).

## Hardware

```python
br = net.router("BR1", "1841")
br.add_module("WIC-2T")  # first free slot that takes it: Serial0/0/0, 0/0/1
```

- `d.slots`, `d.modules`, `d.free_slots(slot_type=None)`, `d.add_module(model, slot=None)`,
  `d.remove_module(slot)`, `pktlib.module_models()`.
- Only modules a model's Physical tab lists, only into a free slot of the right kind, never
  pulling a card with a cable in it. New router ports get the names Packet Tracer gives them.

## Drawings, ping checks, profile

- `net.rectangle(x1, y1, x2, y2, outline="red", fill=None)`, `net.ellipse(...)`,
  `net.note(text, at=)`, `net.around(*devices, shape="ellipse", label=None)`;
  `net.shapes`, `net.notes`. Colours are names (red, blue, green, ...) or `#rrggbb`.
- `net.ping(src, dst, ip=None, scenario=None)` adds a Simple PDU students click in Packet
  Tracer; `net.pdus` lists them as `Pdu(scenario, source, destination, ip)`.
- `net.profile = Profile("A Student", "a@example.com")` (Options > User Profile).

## Checking a network

```python
for problem in pktlib.audit(net):
    print(problem, problem.devices)
```

`pktlib.audit(net)` returns a list of `Problem`s: each is the sentence it prints, plus
`.devices`. It covers duplicate MAC, IPv4 and IPv6 link-local addresses; PC gateways nobody
owns or outside the subnet; cabled router ports left shut; the two ends of a link in
different subnets; serial DCE ends with no clock rate; routers with several networks and no
routing; shared OSPF router-ids; and config Packet Tracer drops on load. It reads the file
only, so still test in Packet Tracer.

Also: `net.duplicate_macs()`, `net.duplicate_link_locals()`,
`pktlib.refused(lines)` (config Packet Tracer drops on load), and
`pktlib.password_matches(stored, password)` for a `password 7 ...` or `secret 5 ...` line.

## Labs

```python
from pktlib.lab import Lab

lab = Lab("Router on a stick", seed=1)
... build the working network on lab.net ...
lab.check("Sales1 is in VLAN 10", lambda n: n["SW1"]["fa0/2"].access_vlan == 10)
lab.fault("Sales2 is in the wrong VLAN",
          brk=lambda n: n["SW1"].config("interface fa0/3\n switchport access vlan 20"),
          fixed=lambda n: n["SW1"]["fa0/3"].access_vlan == 10,
          find="`show vlan brief` on SW1")
lab.build("lab")                        # lab.pkt, lab_solution.pkt, lab_answers.md
for result in lab.grade("handed_in.pkt"):
    print(result.ok, result.name, result.why)
```

`build` writes nothing unless every check passes on the solution, every fault's `fixed`
check fails in the student file, and the audit reports exactly the faults marked
`audit_says=` (`audit=False` skips that part). A check fails when it returns something falsy
or hits a `PktError` (the student deleted a device); any other exception is a bug in the
check and is raised.

## Activities (.pka)

A `.pka` is a Packet Tracer activity: a starting network, an answer network, and a list of
items Packet Tracer compares between them. Students click Check Results and see a percentage
and which items are right. Make one from two networks:

```python
from pktlib.activity import diff_items, load_activity, make_activity


def lan(done):
    net = pktlib.new(seed=1)
    r1 = net.router("R1", "2911")
    pc = net.pc("PC1")
    r1["g0/0"].connect(pc["fa0"])
    if done:
        r1.config("hostname GW")
        r1["g0/0"].address = "10.0.0.1/24"
        pc.set_ip("10.0.0.10/24", gateway="10.0.0.1")
    return net


answer, start = lan(True), lan(False)
act = make_activity(
    answer,
    start,
    ["R1 > Host Name", "R1 > Ports > GigabitEthernet0/0 > IP Address", "PC1 > Default Gateway"],
    "Name the router GW, then address R1 and PC1.",
    tests=[("PC1", "R1")],  # a ping Check Results expects to succeed
)
act.save("lan.pka")

act = load_activity("lan.pka")
print(act.instructions)  # ['Name the router GW, then address R1 and PC1.']
for item, ok in act.score(start):  # grade any network, such as a handed-in .pkt
    print(ok, item)  # False R1 > Host Name = GW, ...
print(diff_items(answer, start))  # every item the two networks differ on
```

Items are paths in the Activity Wizard's tree, device first, as a string with `>` or a
tuple:

- `Host Name`, `Default Gateway` (end devices);
- `Ports > <port> > IP Address`, `Subnet Mask`, `Access VLAN`, `Port Mode`;
- `VLANS > VLAN <n> > VLAN Name`;
- `OSPF > Process ID <n> > Router ID`, `OSPF > Process ID <n> > Networks > Route<k>`;
- `Running Configuration > <line>`, or `> <block header> > <line in it>`, for anything else
  in the config: `("R1", "Running Configuration", "router ospf 1", "network 10.0.0.0
  0.0.0.255 area 0")`.

An item pktlib can't write yet, or one naming a device or port that isn't in both networks,
raises `PktError`. `tests=[(source, destination, should_succeed)]` become ping checks;
`should_succeed=False` passes only if the ping fails (an ACL lab).

A [lab](#labs) becomes an activity with `lab.build("lab", pka=True)`: it writes lab.pka next
to the other three files, grading every item the faults changed. Pass `pka=[items]` to choose
them, and `pka_tests=[...]` for pings. Opened in Packet Tracer 8.2, a student who fixes every
fault gets "You completed the activity".

## Back to code

`pktlib.to_python(net)` (or `pktlib dump`) writes a script that rebuilds the network.
Running it and exporting again gives the same script.

## Errors and warnings

```
PktError (a ValueError)         anything pktlib refuses
├── NotFound (also a KeyError)  no such device, port, slot, VLAN, licence, model, module
└── FileFormatError             not a .pkt pktlib can read: damaged, foreign or too new
    └── TagMismatch             the file's checksum is wrong
PktWarning (a UserWarning)      done, but Packet Tracer may not take it
```

- A wrong type (a port name that isn't a string, a VLAN number given as text) is a
  `TypeError`.
- A refused call leaves the network exactly as it was.
- Messages say what was wrong and what to do: `R1 has no port FastEthernet9/9 (has
  GigabitEthernet0/0, ...)`, `unknown model 'ISR4332' (did you mean ISR4331 or ISR4321?)`.
- `PktWarning` is raised for config Packet Tracer is known to drop on load, and for removing
  a VLAN ports still use.
- The command line prints `pktlib: FILE: message` and exits 1, never a traceback.
