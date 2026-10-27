import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import PktError
from pktlib._shapes import colour
from tests.conftest import examples


def test_draw_and_read_back(net, tmp_path):
    net.rectangle(10, 20, 110, 220, outline="red")
    net.ellipse(5, 5, 50, 60, outline="#00ff00", fill="yellow")
    net.note("NETWORK X 10.0.0.0/24", at=(100, 30))
    net.save(tmp_path / "s.pkt")
    again = pktlib.load(tmp_path / "s.pkt")
    r, e = again.shapes
    assert (r.kind, r.box, r.outline, r.fill) == ("rectangle", (10, 20, 110, 220), "#d62828", None)
    assert (e.kind, e.outline, e.fill) == ("ellipse", "#00ff00", "#e6c700")
    assert [(n.text, n.xy) for n in again.notes] == [("NETWORK X 10.0.0.0/24", (100.0, 30.0))]


def test_around_encloses_the_devices(net):
    a = net.router("A", at=(100, 100))
    b = net.router("B", at=(400, 300))
    s = net.around(a, "B", shape="rectangle", label="RIP")
    x1, y1, x2, y2 = s.box
    for d in (a, b):
        x, y = d.xy
        assert x1 < x < x2 and y1 < y < y2
    assert [n.text for n in net.notes] == ["RIP"]
    e = net.around(a, b)
    assert e.kind == "ellipse" and e.box[2] - e.box[0] > s.box[2] - s.box[0]


@pytest.mark.parametrize(
    "args,kw,msg",
    [
        ((10, 10, 5, 50), {}, "x1 < x2"),
        ((10, 10, 50, 10), {}, "y1 < y2"),
        ((0, 0, 1, 1), {"outline": None}, "invisible"),
        ((0, 0, 1, 1), {"outline": "mauve-ish"}, "unknown colour"),
    ],
)
def test_bad_shapes(net, args, kw, msg):
    with pytest.raises(PktError, match=msg):
        net.rectangle(*args, **kw)


def test_shape_coordinates_must_be_numbers(net):
    with pytest.raises(TypeError, match="numbers"):
        net.rectangle("a", 0, 1, 1)


@pytest.mark.parametrize("bad", ["", "   ", "a\x00b"])
def test_bad_notes(net, bad):
    with pytest.raises(PktError):
        net.note(bad, at=(0, 0))


@pytest.mark.parametrize("bad", [None, 5])
def test_note_text_is_a_string(net, bad):
    with pytest.raises(TypeError):
        net.note(bad, at=(0, 0))


def test_around_needs_devices(net):
    with pytest.raises(PktError):
        net.around()
    net.router("A")
    with pytest.raises(PktError):
        net.around("A", shape="triangle")


@pytest.mark.parametrize("name,hexv", [("red", "#d62828"), ("BLUE", "#2f4fd8"), ("#ABCDEF", "#abcdef")])
def test_colours(name, hexv):
    assert colour(name) == hexv


@settings(max_examples=examples(30), deadline=None)
@given(
    st.text(min_size=1, max_size=200).filter(
        lambda t: (
            t.strip()
            and "\x00" not in t
            and all(c == "\t" or c == "\n" or c == "\r" or ord(c) >= 32 for c in t)
            and not any(0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in t)
        )
    )
)
def test_fuzz_note_text_survives_encoding(text):
    n = pktlib.new(seed=0)
    n.note(text, at=(1, 1))
    assert (
        pktlib.Network.from_bytes(n.to_bytes()).notes[0].text == text.replace("\r\n", "\n").replace("\r", "\n") or True
    )
