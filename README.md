# pktlib

[![PyPI](https://img.shields.io/pypi/v/pktlib)](https://pypi.org/project/pktlib/)
[![Python](https://img.shields.io/pypi/pyversions/pktlib)](https://pypi.org/project/pktlib/)
[![CI](https://github.com/conor-sometimes/pktlib/actions/workflows/ci.yml/badge.svg)](https://github.com/conor-sometimes/pktlib/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/conor-sometimes/pktlib/blob/main/LICENSE)

Read, edit and write Cisco Packet Tracer `.pkt` files (and `.pka` activities) from Python. Build a network in code,
open it in Packet Tracer, and it works.

Tested on **Packet Tracer 8.2.0** (build 8.2.0.0162). Plain Python 3.10+, no dependencies.
MIT licensed. Not affiliated with Cisco.

```python
import pktlib

net = pktlib.new()
r1 = net.router("R1", "2911", at=(300, 200))
sw = net.switch("SW1", at=(300, 320))
pc = net.pc("PC1", at=(300, 440), ip="192.168.1.10/24", gateway="192.168.1.1")

pc["fa0"].connect(sw["fa0/1"])  # the right cable is picked for you
sw["fa0/2"].connect(r1["g0/0"])
r1["g0/0"].address = "192.168.1.1/24"  # interface, ip address, no shutdown
r1.config("""
router ospf 1
 network 192.168.1.0 0.0.0.255 area 0
""")
net.save("lab.pkt")
```

## Installation

pktlib is [on PyPI](https://pypi.org/project/pktlib/):

```
pip install pktlib
```

In a uv project, `uv add pktlib`. To use only the command line (`pktlib audit lab.pkt`,
`pktlib info`, `pktlib dump`) without installing anything into a project:

```
pipx install pktlib
# or run it once with uv
uvx pktlib audit lab.pkt
```

The latest unreleased version: `pip install git+https://github.com/conor-sometimes/pktlib`.

## What it does

- **Build** routers, switches, PCs, phones and any of the 64 models in the 8.2 palette;
  cable them, address them, configure them with IOS text, fit modules, draw labels.
- **Read** any `.pkt`: devices, ports, cables, addresses, VLANs, config. Files from older
  Packet Tracers (6.2 and up) load and save as 8.2.
- **Activities** (`.pka`, `pktlib.activity`): read one, score a network against it, or write
  a new one from two networks that Packet Tracer grades with Check Results.
- **Check** a file before handing it in: `pktlib audit lab.pkt` finds duplicate addresses,
  wrong gateways, shut ports, missing clock rates and config Packet Tracer drops.
- **Teach** with it: troubleshooting labs with planted faults, an answer key and grading
  (`pktlib.lab`); ping checks students click in Packet Tracer.
- **Round-trip**: `pktlib dump lab.pkt` turns any file into a script that rebuilds it.

Every behaviour was seen in Packet Tracer before pktlib relied on it. Where Packet Tracer
does something surprising, pktlib handles it; [docs/packet-tracer.md](https://github.com/conor-sometimes/pktlib/blob/main/docs/packet-tracer.md)
lists what and how we know.

## Command line

| Command | What it does |
|---|---|
| `pktlib info lab.pkt` | devices, links and addresses (a `.pka`: its items and tests too) |
| `pktlib audit lab.pkt` | problems you can see without running the simulation; exit code 1 if any (a `.pka`: its answer network) |
| `pktlib dump lab.pkt [out.py]` | a Python script that rebuilds the file |
| `pktlib decode lab.pkt [out.xml]` / `encode in.xml out.pkt` | the raw XML |

## Documentation

- [Guide](https://github.com/conor-sometimes/pktlib/blob/main/docs/guide.md): the API, with errors and warnings
- [For students](https://github.com/conor-sometimes/pktlib/blob/main/docs/students.md) and [for lecturers](https://github.com/conor-sometimes/pktlib/blob/main/docs/lecturers.md)
- [Packet Tracer notes](https://github.com/conor-sometimes/pktlib/blob/main/docs/packet-tracer.md): editions, device models, the quirks pktlib
  handles, the file format
- [Examples](https://github.com/conor-sometimes/pktlib/blob/main/examples/README.md): every example, by folder; [which were opened in Packet Tracer](https://github.com/conor-sometimes/pktlib/blob/main/docs/examples.md)
- [Changelog](https://github.com/conor-sometimes/pktlib/blob/main/CHANGELOG.md)

## Development

```
uv sync
just check     # ruff, the type checkers, then the tests (about a minute)
just soak 3    # every random test on every core but two for 3 hours, counted
```

[CLAUDE.md](https://github.com/conor-sometimes/pktlib/blob/main/CLAUDE.md) has the project's rules, starting with the main one: Packet Tracer is
the source of truth.
