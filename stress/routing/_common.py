"""Shared bits for the routing stress scripts.

Not a test of anything on its own. `attempt()` runs one natural step and, if
pktlib refuses it, prints the PktError as a FINDING and carries on, so one
refusal doesn't hide the rest of the scenario.
"""

import ipaddress
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pktlib  # noqa: E402, F401  (the rt scripts import it from here)
from pktlib._ports import PktError  # noqa: E402

FINDINGS: list[str] = []


def attempt(label: str, fn, *args, **kwargs):
    """Run fn(*args, **kwargs); on PktError (or any crash) record it and return None."""
    try:
        return fn(*args, **kwargs)
    except PktError as e:
        msg = f"PktError at [{label}]: {e}"
    except Exception as e:  # noqa: BLE001  a crash is a finding too
        msg = f"CRASH at [{label}]: {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
    FINDINGS.append(msg)
    print("  FINDING", msg)
    return None


def note(msg: str) -> None:
    """An API gap or a thing only Packet Tracer can confirm."""
    FINDINGS.append("GAP: " + msg)
    print("  GAP", msg)


def nw(cidr: str) -> ipaddress.IPv4Network:
    return ipaddress.IPv4Network(cidr)


def host(cidr: str, n: int) -> str:
    """'10.0.0.0/30', 1 -> '10.0.0.1/30'."""
    n_ = nw(cidr)
    return f"{n_.network_address + n}/{n_.prefixlen}"


def plain(cidr: str, n: int) -> str:
    return str(nw(cidr).network_address + n)


def wild(cidr: str) -> str:
    n_ = nw(cidr)
    return f"{n_.network_address} {n_.hostmask}"


def mask(cidr: str) -> str:
    n_ = nw(cidr)
    return f"{n_.network_address} {n_.netmask}"


def wire(a, ap: str, b, bp: str, cidr: str, clock: int | None = 64000):
    """Cable a.ap to b.bp (a is DCE on serial), address .1 and .2, set a clock rate."""
    link = a[ap].connect(b[bp])
    a[ap].address = host(cidr, 1)
    b[bp].address = host(cidr, 2)
    if link.cable == "serial" and clock:
        a.config(f"interface {a[ap].name}\n clock rate {clock}")
    return link


def finish(net, name: str) -> Path:
    path = HERE / f"{name}.pkt"
    net.save(path)
    print(f"{path.name}: {len(net.devices)} devices, {len(net.links)} links")
    print(f"{len(FINDINGS)} finding(s)")
    return path
