"""pktlib's exceptions. Catch PktError for anything pktlib refuses.

PktError (a ValueError)
├── NotFound (also a KeyError): no such device, port, slot, VLAN, model...
└── FileFormatError: the bytes or XML aren't a .pkt pktlib can read
    └── TagMismatch: the file's checksum (its EAX tag) is wrong

PktWarning (a UserWarning): done, but Packet Tracer may not take it
"""

from __future__ import annotations


class PktError(ValueError):
    """Something asked of pktlib doesn't fit the network or the file."""


class NotFound(PktError, KeyError):
    """A lookup found nothing: `net["R9"]`, `r1["fa9/9"]`, a VLAN, a slot, a
    model name. It is a KeyError too, so code written for dicts catches it."""

    def __str__(self) -> str:
        # KeyError's own __str__ quotes the message as if it were a key
        return str(self.args[0]) if self.args else ""


class FileFormatError(PktError):
    """The data isn't a .pkt pktlib can read: damaged, truncated, not Packet
    Tracer's, or from a release pktlib refuses (see strict=False)."""


class TagMismatch(FileFormatError):
    """The EAX tag didn't verify: the file is damaged or isn't a .pkt."""


class PktWarning(UserWarning):
    """pktlib did what was asked, but Packet Tracer may not: a config line it
    is known to drop, a VLAN still in use, and the like."""
