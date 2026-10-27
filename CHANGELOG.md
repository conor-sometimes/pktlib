# Changelog

## Unreleased

### Added

- Activities grade ACLs, access groups, NAT and DHCP: `ACL > 110`, `Ports > <port> >
  Access-group In` / `Out` / `NAT Mode`, `NAT > Inside Source Static > NAT Source Setting 1`,
  `DHCP Server > Pools > Pool LAN > Default Gateway`, `DHCP Server > Excluded Addresses > ...`.
  `score()` reads them, `make_activity()` writes them as Packet Tracer's wizard does, and
  `diff_items()` (so `Lab.build(pka=True)`) picks them, keeping config lines for what the
  wizard can't grade (static routes, PAT's `overload`).
- `net.note(text, html=True)` writes markup on purpose; `Note.html` is the stored text.

### Fixed

- `net.note()` text shows as written: Packet Tracer renders notes as HTML, so `<n>` in
  `100.64.<n>.0/30` vanished. `&`, `<` and `>` are now escaped (two showcase notes had it).
- A loaded activity's `initial` reads the start network where the wizard left the value
  out (an ACL or pool the start hasn't got).
- `scripts/make_templates.py` no longer deletes the activity template.
- Static routes in `make_activity()` are refused with the reason (the wizard can't grade
  them), not as an unknown item.

## 0.2.1 (27 Oct 2026)

0.2.0 was withdrawn from PyPI; install 0.2.1 instead.

### Fixed

- A new `1841+WIC-2T` starts with every port in Packet Tracer's unconfigured state (powered
  off, no address, clock rate 2000000), as the other models do. The template carried a
  configured router's port state, overridden by the config Packet Tracer replays on open.
- `audit()` reports a PC address that isn't IPv4 (a damaged file) instead of crashing.

## 0.2.0 (27 Oct 2026)

An API pass after a review of how Pythonic pktlib is, and an audit of its error handling,
then Packet Tracer activities (.pka) and the fixes from a day of checks in Packet Tracer. Many
calls changed; files pktlib writes changed only where Fixed says (a golden-output test holds
every example and stress network to the same bytes).

### Changed (breaking)

- `config()` takes a string or a list of lines and returns the device; `configure()` is gone.
- `set_ip(address, gateway="", *, port=None)`: the address is `"10.0.0.5/24"`,
  `"10.0.0.5 255.255.255.0"` or an `IPv4Interface`, the same as `pc(ip=)` and
  `port.address`. It used to be `set_ip(ip, prefix_or_mask=24, gateway, port)`. On a router,
  set the port's `address` instead.
- `net.profile` is a `Profile(name, email, info)` and settable; `set_profile()` is gone.
- Options are keyword-only: `at=`, `seed=`, `edition=`, `strict=`, `verify=`,
  `verified_only=`, `power_adapter=`.
- A device added without `at=` goes in the next cell of a grid, not on top of the last one.
- Exceptions: `NotFound` (a `KeyError` too) for failed lookups, `FileFormatError` for files
  pktlib can't read, `TagMismatch` under it. Wrong argument types raise `TypeError`.
- `examples/audit.py` is now `pktlib.audit()` and `pktlib audit FILE`. `Lab` runs the audit
  itself (`build(stem, audit=False)` to skip), and `Lab.grade()` returns
  `Result(name, ok, why)`.
- A `Lab` check that raises anything other than a `PktError` is a bug in the check and is
  raised; it used to mark every student FAIL.
- `config()` leaves out `exit`, `end` and `conf t`, treats tabs as indent, refuses
  `ip address a/len` and bad masks, and `no vlan N` removes VLAN N.

- Everything public is importable from `pktlib` (and `pktlib.lab`); the other modules are
  private (`pktlib._model`, ...) and may change. Public classes report themselves as
  `pktlib.X`.
- `config()` refuses `interface X` for a physical port the device doesn't have, and a block
  header with nothing after it; a command already in the config isn't added again.
- `remove_module()` refuses to pull a card when that would rename other ports.
- Port-channel blocks are written in number order.
- The audit no longer asks for a default gateway when there's no router in the PC's subnet
  (switch-only labs).

### Added

- Networks, devices and ports are containers: `for d in net`, `net["R1"]`, `len(net)`,
  `"fa0/1" in r1`, `for p in r1`. `Device`, `Port` and `Link` compare equal by identity and
  hash, so they work in sets and as keys.
- Anything that names a device takes the `Device` too.
- `d.ports` is a read-only mapping that takes IOS shorthand; `d.vlans` and `d.licenses` are
  read-only.
- `link.ports`, `link.other(port)`, `port.peer`, `d.links`, `d.neighbors`.
- `port.mode`, `port.access_vlan`, `port.voice_vlan`, `port.setting(command)`.
- Named records: `Interface`, `Pdu`, `RsaKey`, `End`, `Profile`; readable reprs for
  `Network`, `Ports`, `Shape` and `Note`.
- Settable `d.gateway` and `d.dhcp`.
- `pktlib audit` takes several files and says how many are clean.
- `pktlib.refused(lines)`, `pktlib.password_matches(stored, password)`, and `Lab`, `Result`,
  `Fault` at the top level.
- `CITATION.cff`, for citing pktlib in teaching or research.
- `PktWarning` for config Packet Tracer is known to drop and for removing a VLAN in use.
- `pktlib.Cable` and other `Literal` types; the type hints are checked (ty) and true.
- `pktlib.activity`: Packet Tracer activities (.pka). `load_activity()` reads one (its
  initial and answer networks, instructions and assessment items) and `score()` checks a
  network against the items. `make_activity(answer, initial, items, instructions)` writes a
  new one that Packet Tracer opens and grades with Check Results. Items: host names, default
  gateways, port addresses and masks, access VLANs and port modes, VLAN names, OSPF router IDs
  and network statements, and running-config lines; plus connectivity tests (pings that
  should succeed or fail). `diff_items(answer, start)` lists the items that tell two networks
  apart.
- `Lab.build(stem, pka=True)` also writes STEM.pka: students start from the student file and
  Check Results grades them against the solution on everything the faults changed (or on
  `pka=[items]`), with `pka_tests` as connectivity tests.
- The audit flags a router port given its subnet's network or broadcast address; Packet
  Tracer drops either and the port ends up with no address.

### Fixed

- Wrong types (a VLAN name given as an int, say) got into the XML and made every later save
  fail. They are refused before anything is written.
- Refused calls no longer leave half-done changes: `pc()` with a bad address, a bad VLAN in
  the middle of `config()`, `around()` with a bad label, a bad `at=`.
- Renaming a device to a taken or invalid name was accepted.
- `"fa0/1" in device` raised; `device in net` was always False.
- An ` exit` line in a block put later lines in global config on replay.
- Shorthand like `sw acc vlan 30` didn't create the VLAN.
- A static address after DHCP left both on.
- Damaged files raised `ValueError`, `IndexError` or `ParseError`; they raise
  `FileFormatError` naming what is wrong. The command line names the file and never shows a
  traceback.
- Coordinates of a million or more were written with an exponent.

- `to_python` left out fitted cards, and exported a model's default config blocks whole, so
  replaying them repeated their lines. Every model, with every card it takes, now
  round-trips. It also dropped ping checks, the user profile, VLAN databases, DHCP on end
  devices, a shut switch port, and settings like `spanning-tree mode rapid-pvst` and
  `no ip cef`; every example now rebuilds with all of them (a test exports all 50).
- The audit took a home router's LAN address (a Linksys's 192.168.0.1) for nobody's.
- `Lab.grade()` labels a fault's check `fault: <name>` (it said `fixed:`).
- A 2620XM or 2621XM's onboard WIC serials are Serial0/0 to 0/3, as Packet Tracer names
  them; pktlib wrote Serial0/0/0, and a cable to that made Packet Tracer refuse the file.
- A Hub-PT's ports are named after their card's slot (FastEthernet0, 1, 3 with slot 2
  empty), as Packet Tracer names them; pktlib counted, so pulling a middle card was refused.
- The CCNA ipv6 example gave R3 its /30's broadcast address, so two of its pings failed; the
  fault lab's Tech1 ping stayed on its own subnet, so it couldn't show the gateway fault.

### Development

- `just check` (ruff, ty, tests), `just soak` (random networks through the whole API),
  GitHub Actions on Linux and Windows, Python 3.10 and 3.14.
- Tests: golden output for every example and stress network; a Hypothesis state machine;
  the code in the docs runs.

## 0.1.0

First version.
