"""Folders in flash:. `mkdir` is an exec command, so no config line makes one. Seen in Packet
Tracer 8.2 on 6 Nov 2026, on a 2901: a CDirectory entry written into the file lists in `dir flash:`
as `drw-`, size 192, satisfies `ip ips config location flash:ipsdir` (`show ip ips all` has the
location), and behaves as a typed `mkdir` does. The shape and numbering here come from the folders
Packet Tracer itself saved in an 829's c: (scripts/sources/catalogue_network.pkt)."""

from pathlib import Path

import pytest

import pktlib
from pktlib import PktError

SOURCES = Path(__file__).parent.parent / "scripts" / "sources"


def saved_c_drive():
    """The c: file system Packet Tracer saved in an 829's embedded server, with folders in it."""
    net = pktlib.load(SOURCES / "catalogue_network.pkt")
    r = next(d for d in net.devices if d.model == "829")
    return next(f for f in r.engine.iter("FILE") if f.findtext("NAME") == "c:")


def flash_of(device):
    return device.engine.find("FILE_MANAGER/FILE/FILES/FILE[NAME='flash:']")


def names(device):
    return [f.findtext("NAME") for f in flash_of(device).findall("FILES/FILE")]


def test_a_folder_has_the_shape_packet_tracer_saves():
    saved = saved_c_drive().find("FILES/FILE[NAME='software']")
    r = pktlib.new(seed=1).router("R1", "2901")
    r.mkdir("ipsdir")
    made = flash_of(r).find("FILES/FILE[NAME='ipsdir']")
    assert made.attrib == saved.attrib == {"class": "CDirectory"}
    assert [c.tag for c in made] == [c.tag for c in saved]
    assert made.findtext("PERMISSION") == saved.findtext("PERMISSION") == "6"
    assert list(made.find("FILES")) == [] and not made.findtext("FILE_CONTENT")


def test_numbers_come_from_the_file_systems_counter():
    # as saved: c: counts 7 with folders numbered 2 to 7, nested ones from the same counter
    c = saved_c_drive()
    numbers = sorted(int(f.findtext("FILE_NUMBER")) for f in c.iter("FILE") if f is not c)
    assert numbers[-1] == int(c.findtext("FILE_COUNTER")) == 7

    r = pktlib.new(seed=2).router("R1", "2901")
    start = int(flash_of(r).findtext("FILE_COUNTER"))
    r.mkdir("one")
    r.mkdir("two")
    assert flash_of(r).findtext("FILE_COUNTER") == str(start + 2)
    number = {f.findtext("NAME"): f.findtext("FILE_NUMBER") for f in flash_of(r).findall("FILES/FILE")}
    assert (number["one"], number["two"]) == (str(start + 1), str(start + 2))


def test_folders_go_in_the_order_packet_tracer_saves():
    # as saved: byte order by name, numbers aside (caf 4 ahead of downloads 3; Desktop: ahead of c:)
    software = saved_c_drive().find("FILES/FILE[NAME='software']")
    assert [f.findtext("NAME") for f in software.findall("FILES/FILE")] == ["caf", "downloads"]

    r = pktlib.new(seed=3).router("R1", "2901")
    for folder in ("zeta", "ipsdir", "Alpha"):
        r.mkdir(folder)
    assert names(r) == sorted(names(r))
    assert r.flash_folders == ["Alpha", "ipsdir", "zeta"]


def test_flash_prefix_is_the_same_folder_and_a_second_mkdir_changes_nothing():
    net = pktlib.new(seed=4)
    r = net.router("R1", "2901")
    r.mkdir("flash:ipsdir")
    assert r.flash_folders == ["ipsdir"]
    before = net.to_xml()
    r.mkdir("ipsdir")
    assert net.to_xml() == before


@pytest.mark.parametrize("bad", ["", "flash:", "two words", "a/b", "a\\b", "disk0:x", "tab\tbed", "ctl\x01"])
def test_names_a_folder_cant_have_are_refused(bad):
    net = pktlib.new(seed=5)
    r = net.router("R1", "2901")
    before = net.to_xml()
    with pytest.raises(PktError, match="one name"):
        r.mkdir(bad)
    assert net.to_xml() == before


def test_a_name_already_used_by_a_file_is_refused():
    net = pktlib.new(seed=6)
    r = net.router("R1", "2901")
    before = net.to_xml()
    with pytest.raises(PktError, match="already has a file"):
        r.mkdir("sigdef-default.xml")
    assert net.to_xml() == before


def test_a_folder_name_is_a_string():
    with pytest.raises(TypeError):
        pktlib.new(seed=7).router("R1", "2901").mkdir(3)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("model", ["PC-PT", "Linksys-WRT300N", "7960"])
def test_a_device_with_no_flash_has_no_folders(model):
    net = pktlib.new(seed=8)
    d = net.add_device("D", model)
    assert d.flash_folders == []
    with pytest.raises(PktError, match="no flash"):
        d.mkdir("ipsdir")


def test_only_the_devices_own_flash_counts():
    # an 829 also has an embedded AP with a flash: of its own, further down the XML
    net = pktlib.new(seed=9)
    r = net.add_device("R1", "829")
    embedded = next(f for f in r.engine.iter("FILE") if f.findtext("NAME") == "flash:" and f is not flash_of(r))
    before = embedded.findtext("FILE_COUNTER")
    r.mkdir("ipsdir")
    assert r.flash_folders == ["ipsdir"]
    assert embedded.findtext("FILE_COUNTER") == before
    assert embedded.find("FILES/FILE[NAME='ipsdir']") is None


def test_the_ips_location_works_as_the_2901_showed(tmp_path):
    net = pktlib.new(seed=10)
    r = net.router("R3", "2901")
    r.mkdir("ipsdir")
    r.config("ip ips config location flash:ipsdir")
    path = tmp_path / "ips.pkt"
    net.save(path)
    back = pktlib.load(path).device("R3")
    assert back.flash_folders == ["ipsdir"]
    assert "ip ips config location flash:ipsdir" in back.running_config
    assert flash_of(back).findtext("FILE_COUNTER") == flash_of(r).findtext("FILE_COUNTER")


def test_to_python_brings_folders_across(tmp_path):
    net = pktlib.new(seed=11)
    net.router("R1", "2901").mkdir("ipsdir")
    source = pktlib.to_python(net, str(tmp_path / "out.pkt"))
    assert "mkdir('ipsdir')" in source
    exec(compile(source, "export", "exec"), {})
    assert pktlib.load(tmp_path / "out.pkt").device("R1").flash_folders == ["ipsdir"]
