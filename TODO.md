# pktlib: what's open (28 Oct 2026)

```
uv run pytest                  # everything; must pass before a commit
just examples                  # rebuild and audit the examples into out/
```

## To check in Packet Tracer

- `examples/fault_lab.py`: open `fault_lab.pkt`, confirm Sales2 can't reach Sales1 (wrong
  VLAN) and Tech1 can't reach its gateway; then `fault_lab_solution.pkt` pings clean.
- `examples/enterprise.py`: `ipconfig` on STAFF1. Its link-local should be
  FE80::202:BAFF:FE64:6A24, not the template's FE80::290:CFF:FEC7:8E5A. The fix for cloned
  link-locals hasn't been seen in the GUI yet.

## Limits checked in Packet Tracer (round 1, 27 Oct)

Done: pktlib refuses, warns or audits each silent drop (VLAN name in use, 2960 port
address, a cable within one device, 7960 config, Bluetooth address, network or broadcast or
overlapping router addresses). Accepted by Packet Tracer, so left alone: 200-character and
spaced VLAN names, renaming VLAN 1, device names differing only in case, control
characters, odd PC addresses (network, broadcast, /32, the gateway's own; the network one
still pinged), a 1000-bit RSA key (SSH works). Coordinates clamp to about x 100-3900, y from 100. Still open:

- Is it `include-connected` Packet Tracer drops under `ipv6 router eigrp`, or any
  `redistribute ospf` there? stress/routing/rt05 now writes it without; check V6-B still has
  D routes and the far side EX routes.

## Config: a block entered twice

- Since 27 Oct a command entered twice in a flat block (interface, router ospf, line) is kept
  once, as IOS shows it. That dropped one duplicate line each from stress/routing/rt02 (STB1's
  second `network 10.11.8.0 0.0.0.255 area 1`) and rt05 (V6-B's second `no auto-summary`).
  Re-open both in Packet Tracer to confirm the routes still come up.

- A block header outside `_MERGEABLE` entered a second time (`ipv6 router ospf 1`, then later
  `ipv6 router ospf 1` again) gets a second copy before `end`; IOS would merge it into the first.
  stress/routing/rt05 relies on the second-copy form and was checked in Packet Tracer that way
  (OSPFv3 routes learned). Merging is one line in `merge_config` (found by the idempotence
  property in tests/test_properties.py, 27 Oct); do it once rt05 rebuilt with merging has been
  opened in Packet Tracer and its routes still come up.

## Bugs and rough edges

- `add_module` writes `clock rate` on every new serial port, the DTE end too (harmless, untidy).
- Interface blocks for added modules land after `line vty`; Packet Tracer's own saves keep IOS
  order. Works today; check nothing else is order-sensitive the way Port-channel was.
- Grow `refused()` as more silent refusals turn up. Only add what Packet Tracer was seen
  rejecting.
- End devices are IPv4 only (`set_ip` raises for IPv6).

## Ideas, not started

- `scripts/hover_rig.py`: one file with every model, to read port names off the hover table
  when a new edition lands.
- Physical view (wiring closets, buildings, wireless range). Not until a lab needs it.

## Before publishing

- No coursework in the repo or the package: every sample is listed with its origin in
  `tests/fixtures/README.md`, and a test fails on one that isn't.
