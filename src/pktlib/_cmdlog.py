"""Packet Tracer's IOS command log: Options > View Command Log (Ctrl+Shift+V).

Packet Tracer 8.2 records every command typed at a device's CLI in COMMAND_LOGS
at the top of the file, and the window lists them with Time, Device, Prompt,
Command and Resolved Command (seen 24 Nov 2026, in a .pkt and in a .pka opened
as a student). Each LOG_ENTRY holds those five fields joined by NULs, as hex:
`Tue Nov 24 12:15:06 2026`, `R1`, `R1#`, `sh ip int br`, `show ip interface brief`.
A network pktlib makes starts with an empty log."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import NamedTuple

from ._errors import PktError

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class LogEntry(NamedTuple):
    """One command in the log. `time` is None if the file's text isn't a time pktlib reads.
    `resolved` is the command as IOS expanded it; Packet Tracer leaves it empty for some
    commands (`switchport access vlan 10` was, on 27 Oct)."""

    time: datetime | None
    device: str
    prompt: str
    command: str
    resolved: str = ""


def format_time(t: datetime) -> str:
    """As Packet Tracer writes it: 'Tue Nov 24 12:15:06 2026', English names whatever
    the locale. Every time seen had a two-digit day; a day under 10 is written without
    padding ('Tue Nov 3'), as Qt's default date text is, but that hasn't been seen."""
    return f"{_DAYS[t.weekday()]} {_MONTHS[t.month - 1]} {t.day} {t:%H:%M:%S} {t.year}"


def parse_time(text: str) -> datetime | None:
    """'Tue Nov 24 12:15:06 2026' -> a datetime (no time zone: Packet Tracer writes local
    time and says nothing of the zone). None for text in another form."""
    words = text.split()
    if len(words) != 5 or words[1] not in _MONTHS:
        return None
    try:
        hour, minute, second = (int(x) for x in words[3].split(":"))
        return datetime(int(words[4]), _MONTHS.index(words[1]) + 1, int(words[2]), hour, minute, second)
    except ValueError:  # not three numbers, or not a real date
        return None


def read_entry(el: ET.Element) -> LogEntry | None:
    """A LOG_ENTRY as an entry; None if it isn't hex of five NUL-separated fields."""
    try:
        fields = bytes.fromhex(el.text or "").decode("utf-8").split("\0")
    except (ValueError, UnicodeDecodeError):
        return None
    if len(fields) != 5:
        return None
    return LogEntry(parse_time(fields[0]), *fields[1:])


def make_entry(entry: LogEntry) -> ET.Element:
    """The LOG_ENTRY Packet Tracer writes for `entry` (its time must be set)."""
    if entry.time is None:
        raise PktError("a command log entry needs a time")
    fields = [format_time(entry.time), entry.device, entry.prompt, entry.command, entry.resolved]
    for name, value in zip(("device", "prompt", "command", "resolved"), fields[1:], strict=True):
        if "\0" in value or "\n" in value or "\r" in value:
            raise PktError(f"a command log {name} is one line with no NUL, got {value!r}")
    if not entry.command.strip():
        raise PktError("a command log entry needs a command")
    el = ET.Element("LOG_ENTRY")
    el.text = "\0".join(fields).encode("utf-8").hex()
    return el
