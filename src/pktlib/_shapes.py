"""Drawings on the logical workspace: rectangles, ellipses and text notes."""

from __future__ import annotations

import math
import random
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ._errors import FileFormatError, PktError
from ._xml import fmt_num, req_float, req_int

COLOURS = {
    "red": "#d62828",
    "blue": "#2f4fd8",
    "green": "#2e9e44",
    "orange": "#f08c00",
    "purple": "#7b3fbf",
    "black": "#000000",
    "grey": "#808080",
    "gray": "#808080",
    "yellow": "#e6c700",
    "teal": "#11867f",
}


def colour(value: str) -> str:
    """'red' or '#d62828' -> '#d62828'."""
    if not isinstance(value, str):
        raise TypeError(f"a colour is a name or '#rrggbb', got {value!r}")
    v = COLOURS.get(value.lower(), value)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        raise PktError(f"unknown colour {value!r} (names: {', '.join(COLOURS)}, or '#rrggbb')")
    return v.lower()


@dataclass(eq=False)
class Shape:
    """A rectangle or ellipse. Coordinates are the workspace's, the same as
    device positions."""

    el: ET.Element

    def __repr__(self) -> str:
        x1, y1, x2, y2 = self.box
        how = ", ".join(f"{k} {v}" for k, v in (("outline", self.outline), ("fill", self.fill)) if v)
        return f"<Shape {self.kind} ({fmt_num(x1)}, {fmt_num(y1)})-({fmt_num(x2)}, {fmt_num(y2)}) {how}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Shape) and other.el is self.el

    def __hash__(self) -> int:
        return id(self.el)

    @property
    def kind(self) -> str:
        return "rectangle" if self.el.tag == "RECTANGLE" else "ellipse"

    @property
    def box(self) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = (req_float(self.el, t) for t in ("TopLeftX", "TopLeftY", "BottomRightX", "BottomRightY"))
        return x1, y1, x2, y2

    @property
    def outline(self) -> str | None:
        f = self.el.find("Filled")
        return f.get("OUTLINECOLOR") if f is not None and f.get("OUTLINED") == "true" else None

    @property
    def fill(self) -> str | None:
        if self.el.findtext("Filled") != "1":
            return None
        r, g, b = (req_int(self.el, f"Color/{c}") for c in ("Red", "Green", "Blue"))
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise FileFormatError(f"a shape's fill colour should be 0-255 per channel, got {(r, g, b)}")
        return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(eq=False)
class Note:
    """A text label on the workspace."""

    el: ET.Element

    def __repr__(self) -> str:
        x, y = self.xy
        return f"<Note {self.text!r} at ({fmt_num(x)}, {fmt_num(y)})>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Note) and other.el is self.el

    def __hash__(self) -> int:
        return id(self.el)

    @property
    def text(self) -> str:
        return self.el.findtext("TEXT") or ""

    @property
    def xy(self) -> tuple[float, float]:
        return req_float(self.el, "X"), req_float(self.el, "Y")


def _num(v: float) -> str:
    return fmt_num(v)


def make_shape(
    tag: str,
    box: tuple[float, float, float, float],
    outline: str | None,
    fill: str | None,
    mem_addr: str,
    rng: random.Random,
) -> ET.Element:
    """The XML for a rectangle or ellipse; see Network.rectangle()."""
    x1, y1, x2, y2 = box
    for v in box:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"shape coordinates are numbers, got {v!r}")
        if not math.isfinite(v):
            raise PktError(f"shape coordinates must be finite, got {box}")
    # checked as written: Packet Tracer stores whole numbers
    if round(x2) <= round(x1) or round(y2) <= round(y1):
        raise PktError(f"a shape needs x1 < x2 and y1 < y2 (in whole units), got {box}")
    if outline is None and fill is None:
        raise PktError("a shape with no outline and no fill would be invisible")
    el = ET.Element(tag, uuid=f"{{{uuid.UUID(int=rng.getrandbits(128), version=4)}}}")
    for t, v in zip(("TopLeftX", "TopLeftY", "BottomRightX", "BottomRightY"), box, strict=True):
        ET.SubElement(el, t).text = _num(round(v))
    c = ET.SubElement(el, "Color")
    rgb = colour(fill) if fill else "#000000"
    for name, i in (("Red", 1), ("Green", 3), ("Blue", 5)):
        ET.SubElement(c, name).text = str(int(rgb[i : i + 2], 16))
    f = ET.SubElement(el, "Filled")
    f.text = "1" if fill else "0"
    f.set("OUTLINED", "true" if outline else "false")
    f.set("OUTLINECOLOR", colour(outline) if outline else "#000000")
    ET.SubElement(el, "RECTCLUSTERID" if tag == "RECTANGLE" else "ELLIPSECLUSTERID").text = "1-1"
    ET.SubElement(el, "MEM_ADDR").text = mem_addr
    return el


def check_note_text(text: object) -> str:
    """A note's text, checked: a non-blank string with no NUL."""
    if not isinstance(text, str):
        raise TypeError(f"a note's text is a string, got {type(text).__name__}")
    if not text.strip():
        raise PktError("a note needs some text")
    if "\x00" in text:
        raise PktError("a note can't hold a NUL character")
    return text


def make_note(text: str, xy: tuple[float, float], z: int, mem_addr: str, rng: random.Random) -> ET.Element:
    """The XML for a text note; see Network.note()."""
    check_note_text(text)
    for v in xy:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(f"a note's position is two numbers, got {xy!r}")
        if not math.isfinite(v):
            raise PktError(f"a note's position must be finite, got {xy!r}")
    el = ET.Element("NOTE", uuid=f"{{{uuid.UUID(int=rng.getrandbits(128), version=4)}}}")
    ET.SubElement(el, "X").text = _num(round(xy[0]))
    ET.SubElement(el, "Y").text = _num(round(xy[1]))
    ET.SubElement(el, "Z").text = str(z)
    t = ET.SubElement(el, "TEXT")
    t.set("translate", "true")
    t.text = text
    ET.SubElement(el, "NOTECLUSTERID").text = "1-1"
    ET.SubElement(el, "MEM_ADDR").text = mem_addr
    return el
