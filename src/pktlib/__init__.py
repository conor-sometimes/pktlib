"""pktlib: read, edit and write Cisco Packet Tracer .pkt files, in plain Python.

import pktlib

net = pktlib.new()
r1 = net.router("R1", "1841+WIC-2T", at=(200, 380))
sw = net.switch("SW0", at=(200, 260))
pc = net.pc("PC0", at=(200, 150), ip="192.168.1.10/24", gateway="192.168.1.1")
pc["fa0"].connect(sw["fa0/1"])
sw["fa0/2"].connect(r1["fa0/0"])
r1["fa0/0"].address = "192.168.1.1/24"
net.save("lab.pkt")

net = pktlib.load("lab.pkt")
print(pktlib.to_python(net))   # any .pkt -> a script that rebuilds it

Everything public is here, at the top level, and in pktlib.lab. Modules whose names
start with an underscore are pktlib's own and may change in any release.
"""

import contextlib as _contextlib
from importlib import metadata as _metadata

from ._audit import Problem, audit
from ._codec import decode, encode
from ._editions import EDITIONS, LATEST
from ._errors import FileFormatError, NotFound, PktError, PktWarning, TagMismatch
from ._export import to_python
from ._iosconfig import refused
from ._model import (
    Address,
    Cable,
    Device,
    End,
    Interface,
    Link,
    Network,
    Pdu,
    Port,
    Ports,
    Profile,
    RsaKey,
    load,
    models,
    new,
)
from ._modules import Slot, module_models
from ._passwords import matches as password_matches
from ._ports import canonical_port
from ._shapes import Note, Shape
from .lab import Fault, Lab, Result

__all__ = [
    "EDITIONS",
    "LATEST",
    "Address",
    "Cable",
    "Device",
    "End",
    "Fault",
    "FileFormatError",
    "Interface",
    "Lab",
    "Link",
    "Network",
    "NotFound",
    "Note",
    "Pdu",
    "PktError",
    "PktWarning",
    "Port",
    "Ports",
    "Problem",
    "Profile",
    "Result",
    "RsaKey",
    "Shape",
    "Slot",
    "TagMismatch",
    "audit",
    "canonical_port",
    "decode",
    "encode",
    "load",
    "models",
    "module_models",
    "new",
    "password_matches",
    "refused",
    "to_python",
]

# Public names say they're pktlib's, not a private module's: pktlib.NotFound in a
# traceback, and help(pktlib.Network) names the right place.
for _name in __all__:
    _obj = globals()[_name]
    if getattr(_obj, "__module__", "").startswith("pktlib."):
        with _contextlib.suppress(AttributeError, TypeError):  # typing aliases (Cable, Address) can't be
            _obj.__module__ = __name__

try:
    __version__ = _metadata.version("pktlib")
except _metadata.PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0+unknown"
