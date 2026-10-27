# Patterns to start from

Each of these was opened and tested in Packet Tracer 8.2. Copy the closest, don't start blank.

- `examples/labs/router_on_a_stick.py` (one router, one switch, PCs per VLAN). The model for any
  switching lab: one `VLANS` table drives switch ports, sub-interfaces and addresses.
- `examples/labs/ospf_ring.py` (a ring of routers, a LAN each). The model for routing labs; change
  the protocol lines and the rest stays.
- `examples/labs/practice_lab.py` (random chain of routers, routers left blank). The model for a
  seeded lab with an answer key written next to it: same seed, same lab.
- `examples/showcase/enterprise.py` is the big one (HSRP, EtherChannel, NAT, EIGRP and OSPF). Read it
  for how a feature is written, not as a starting size.

Where to look things up:
- `pktlib.models()`: every model you may use. `src/pktlib/spec/devices.json`: each model's
  ports, slots and the modules a slot accepts.
- `docs/packet-tracer.md`, "What Packet Tracer does that pktlib handles for you": the quirks.
- `src/pktlib/iosconfig.py`, `_REFUSED`: config Packet Tracer drops on load.
