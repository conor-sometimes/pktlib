"""ElementTree helpers shared by the model: lookups that must find something.

`find()` returns None when an element is missing. Packet Tracer always writes
these, so a missing one means a damaged or foreign file: say which element,
rather than fail later with an AttributeError on None.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from ._errors import FileFormatError


def req(el: ET.Element, path: str) -> ET.Element:
    """el.find(path), or a FileFormatError naming what's missing."""
    found = el.find(path)
    if found is None:
        raise FileFormatError(f"no <{path}> under <{el.tag}>")
    return found


def req_text(el: ET.Element, path: str) -> str:
    """The text of el.find(path) ('' if the element is empty); an error if it's missing."""
    return req(el, path).text or ""


def req_attr(el: ET.Element, name: str) -> str:
    """el.get(name), or a FileFormatError naming what's missing."""
    value = el.get(name)
    if value is None:
        raise FileFormatError(f"<{el.tag}> has no {name}=")
    return value


def req_float(el: ET.Element, path: str) -> float:
    """The number at path: a FileFormatError if it's missing or isn't a finite number."""
    raw = req_text(el, path)
    try:
        v = float(raw)
    except ValueError:
        raise FileFormatError(f"<{path}> under <{el.tag}> should be a number, got {raw!r}") from None
    if not math.isfinite(v):
        raise FileFormatError(f"<{path}> under <{el.tag}> should be a finite number, got {raw!r}")
    return v


def req_int(el: ET.Element, path: str) -> int:
    """The whole number at path: a FileFormatError if it's missing or isn't one."""
    raw = req_text(el, path)
    try:
        return int(raw)
    except ValueError:
        raise FileFormatError(f"<{path}> under <{el.tag}> should be a whole number, got {raw!r}") from None


def req_int_attr(el: ET.Element, name: str) -> int:
    """el.get(name) as a whole number: a FileFormatError if it's missing or isn't one."""
    raw = req_attr(el, name)
    try:
        return int(raw)
    except ValueError:
        raise FileFormatError(f"<{el.tag} {name}=...> should be a whole number, got {raw!r}") from None


def text(el: ET.Element, path: str, default: str = "") -> str:
    """The text at path ("" if empty), or `default` when the element is missing."""
    v = el.findtext(path)
    return default if v is None else v


def fmt_num(v: float) -> str:
    """A coordinate as Packet Tracer writes one: plain decimal (591.5, 100),
    6 significant digits, never an exponent (1234567.8, not 1.23457e+06)."""
    s = f"{v:g}"
    if "e" in s:
        s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s


def set_text(el: ET.Element, path: str, value: str) -> None:
    """Set the text of an element that must already exist."""
    req(el, path).text = value
