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
| `pktlib info lab.pkt` | devices, links and addresses (a `.pka`: its items and tests; `--answers` adds the values) |
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

## Legal and ethical use

- **Not Cisco's.** pktlib is an independent project, not affiliated with or endorsed by
  Cisco. Cisco and Packet Tracer are Cisco's trademarks.
- **No Cisco code.** The file format comes from published work by the projects below, and
  was checked by opening files in Packet Tracer. The device templates in the package are
  copied from files Packet Tracer 8.2 saved. To open what pktlib writes, you need your own
  copy of Packet Tracer from Cisco Networking Academy.
- **Coursework.** Follow your course's rules. Anyone holding a `.pka` can read its answer
  network and graded items: `pktlib info --answers` lists them, and the activity password
  only locks Packet Tracer's Activity Wizard. Don't use pktlib to read the answers to an
  activity you're being graded on. And if you set activities, don't count on a `.pka` to
  keep its answers secret.
- **No course material here.** This repo holds no lecturer or NetAcad files. Every sample
  file says where it came from in
  [tests/fixtures/README.md](https://github.com/conor-sometimes/pktlib/blob/main/tests/fixtures/README.md).

## Related projects

- [pka2xml](https://github.com/mircodz/pka2xml) (BSD-2-Clause, 2020): the first public
  description of the encryption. pktlib's codec re-implements it in Python.
- [packet-tracer-pkt-format](https://github.com/aacanadaa/packet-tracer-pkt-format)
  (GPL-3.0): a full format reference, covering files from Packet Tracer 4.1 to 9.0.1. Read
  its FORMAT.md if you want to know exactly how a `.pkt` is built. pktlib uses none of its
  code.

## Development

```
uv sync
just check     # ruff, the type checkers, then the tests (about a minute)
just soak 3    # every random test on every core but two for 3 hours, counted
```

[CLAUDE.md](https://github.com/conor-sometimes/pktlib/blob/main/CLAUDE.md) has the project's rules, starting with the main one: Packet Tracer is
the source of truth.
