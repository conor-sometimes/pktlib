"""Editions: pktlib only stamps Packet Tracer releases it knows, and treats
version stamps the way Packet Tracer 8.2.0 does. Tried in the GUI on 25 Oct
2026: stamps 9.0.0.0000 and 8.2.2.0400 are refused ("This file requires Cisco
Packet Tracer version ..."), 8.1.1.0022 opens, "banana" is refused."""

import xml.etree.ElementTree as ET

import pytest
from hypothesis import given
from hypothesis import strategies as st

import pktlib
from pktlib import PktError
from pktlib import _editions as editions
from pktlib._codec import encode
from pktlib._xml import req


def stamped(version: str) -> bytes:
    net = pktlib.new(seed=80)
    net.pc("PC0")
    req(net.root, "VERSION").text = version
    return encode(ET.tostring(net.root))  # straight to bytes: save() would restamp it


def test_new_is_stamped_with_the_edition():
    net = pktlib.new()
    assert net.version == "8.2.0.0162" and net.edition == "8.2" == pktlib.LATEST
    assert pktlib.new(edition="8.2").version == pktlib.EDITIONS["8.2"]


@pytest.mark.parametrize("edition", ["9.0", "8.1", "8", "8.2.0", "", "latest"])
def test_editions_pktlib_has_not_tested_are_refused(edition):
    with pytest.raises(PktError, match="doesn't know Packet Tracer edition"):
        pktlib.new(edition=edition)


@pytest.mark.parametrize("version", ["9.0.0.0000", "8.2.2.0400", "8.3.0.0001", "8.2.0.0163"])
def test_newer_files_are_refused_like_packet_tracer_does(tmp_path, version):
    f = tmp_path / "x.pkt"
    f.write_bytes(stamped(version))
    with pytest.raises(PktError, match="newer than any edition pktlib knows"):
        pktlib.load(f)
    net = pktlib.load(f, strict=False)  # opt in to reading it
    assert net.version == version and net.edition is None
    assert [d.name for d in net.devices] == ["PC0"]


def test_reading_a_newer_file_anyway_keeps_its_stamp(tmp_path):
    f = tmp_path / "x.pkt"
    f.write_bytes(stamped("9.0.0.0000"))
    net = pktlib.load(f, strict=False)
    net.save(tmp_path / "y.pkt")
    assert pktlib.load(tmp_path / "y.pkt", strict=False).version == "9.0.0.0000"


@pytest.mark.parametrize("version", ["banana", "", "8.2", "8.2.0", "8.2.0.0162.1", "v8.2.0.0162"])
def test_stamps_that_are_not_versions_are_refused(tmp_path, version):
    f = tmp_path / "x.pkt"
    f.write_bytes(stamped(version))
    with pytest.raises(PktError, match="isn't a Packet Tracer version"):
        pktlib.load(f)


def test_older_files_open_and_save_as_the_newest_edition(tmp_path):
    """Packet Tracer 8.2 opens an 8.1 file and saves it as 8.2; so does pktlib."""
    f = tmp_path / "old.pkt"
    f.write_bytes(stamped("8.1.1.0022"))
    net = pktlib.load(f)
    assert net.version == "8.1.1.0022" and net.edition is None
    net.save(tmp_path / "new.pkt")
    assert pktlib.load(tmp_path / "new.pkt").version == "8.2.0.0162"


def test_the_sources_and_examples_are_all_8_2():
    from pathlib import Path

    for f in (Path(__file__).parents[1] / "scripts" / "sources").glob("*.pkt"):
        assert pktlib.load(f).edition == "8.2", f.name


def test_version_ordering():
    assert editions.parse("8.2.0.0162") < editions.parse("8.2.0.0163") < editions.parse("8.2.2.0000")
    assert editions.parse("8.10.0.0000") > editions.parse("8.9.9.9999")  # numbers, not text
    assert editions.parse(" 8.2.0.0162 ") == (8, 2, 0, 162)


@given(st.text(max_size=30))
def test_fuzz_parse_never_crashes_with_anything_but_pkterror(s):
    try:
        v = editions.parse(s)
    except PktError:
        return
    assert len(v) == 4 and all(isinstance(n, int) for n in v)


@given(st.tuples(*[st.integers(0, 99)] * 3, st.integers(0, 9999)))
def test_fuzz_newer_means_bigger(t):
    v = ".".join(map(str, t[:3])) + f".{t[3]:04d}"
    assert editions.newer_than_known(v) == (t > (8, 2, 0, 162))


def test_an_older_build_of_the_edition_is_restamped_on_save(tmp_path):
    f = tmp_path / "x.pkt"
    f.write_bytes(stamped("8.2.0.0100"))
    net = pktlib.load(f)
    assert net.edition == "8.2"
    net.save(tmp_path / "y.pkt")
    assert pktlib.load(tmp_path / "y.pkt").version == "8.2.0.0162"


def test_info_reads_any_version(tmp_path, capsys):
    from pktlib._cli import main

    f = tmp_path / "x.pkt"
    f.write_bytes(stamped("9.0.0.0000"))
    main(["info", str(f)])
    assert "Packet Tracer 9.0.0.0000 (an edition pktlib doesn't know)" in capsys.readouterr().out
