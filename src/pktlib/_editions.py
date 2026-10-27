"""Editions: which Packet Tracer a file is for.

A .pkt file carries one version stamp, PACKETTRACER5/VERSION, e.g. 8.2.0.0162
(major.minor.patch.build). Packet Tracer 8.2.0 checks it on open (tried 25 Oct
2026): a newer stamp, even 8.2.2, is refused ("This file requires Cisco Packet
Tracer version ..."), an older one opens, and a stamp that isn't a version is
refused.

pktlib works like Rust editions: a network has an edition, and pktlib only
writes editions it has device templates and tested quirks for. Asking for any
other is an error, so pktlib can't produce a file stamped for a Packet Tracer
nobody has checked it against.
"""

from __future__ import annotations

import re

from ._errors import FileFormatError, PktError

# edition -> the exact stamp Packet Tracer writes. One per release pktlib was
# tested on; add one only with templates and a test run in that release.
EDITIONS: dict[str, str] = {"8.2": "8.2.0.0162"}
LATEST = "8.2"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")


def parse(version: str) -> tuple[int, int, int, int]:
    """'8.2.0.0162' -> (8, 2, 0, 162). Anything else is an error, as it is to
    Packet Tracer."""
    m = _VERSION_RE.fullmatch((version or "").strip())
    if not m:
        raise FileFormatError(f"{version!r} isn't a Packet Tracer version (like 8.2.0.0162)")
    major, minor, patch, build = (int(g) for g in m.groups())
    return major, minor, patch, build


def stamp(edition: str) -> str:
    """The version stamp pktlib writes for an edition."""
    if not isinstance(edition, str):
        raise TypeError(f"an edition is a string like '8.2', got {edition!r}")
    if edition not in EDITIONS:
        raise PktError(
            f"pktlib doesn't know Packet Tracer edition {edition!r} (it knows {', '.join(sorted(EDITIONS))})"
        )
    return EDITIONS[edition]


def edition_of(version: str) -> str | None:
    """The edition a stamp belongs to ('8.2.0.0162' -> '8.2'), or None if pktlib
    doesn't have that release. A later patch of the same minor (8.2.2) isn't
    the 8.2 edition: Packet Tracer 8.2.0 refuses those files."""
    v = parse(version)
    name = f"{v[0]}.{v[1]}"
    return name if name in EDITIONS and v <= parse(EDITIONS[name]) else None


def newer_than_known(version: str) -> bool:
    """True for a file from a Packet Tracer newer than any edition pktlib knows."""
    newest = max(parse(v) for v in EDITIONS.values())
    return parse(version) > newest
