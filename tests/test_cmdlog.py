"""The command log (Options > View Command Log). Seen in Packet Tracer 8.2 on 24 Nov 2026:
every command typed at a CLI is listed with its time, device, prompt and what IOS made of
it, in a .pkt and in a .pka opened as a student; each LOG_ENTRY is those five fields,
NUL-separated, in hex."""

from datetime import datetime
from pathlib import Path

import pytest

import pktlib
from pktlib import LogEntry, NotFound, PktError
from pktlib._cli import main
from pktlib._cmdlog import format_time, parse_time
from pktlib._xml import req

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_the_log_packet_tracer_saved():
    net = pktlib.load(FIXTURES / "rich2-answer.pkt")
    log = net.command_log
    assert len(log) == 11
    assert log[0] == LogEntry(datetime(2026, 10, 27, 15, 50, 36), "ISP", "ISP>", "enable", "enable")
    assert log[2].command == "interface fa0/3" and log[2].resolved == "interface FastEthernet0/3"
    assert log[3].resolved == ""  # `switchport access vlan 10`: Packet Tracer left it empty
    assert net.device("ISP").command_log == log and net.device("R1").command_log == []


def test_a_new_network_has_an_empty_log():
    assert pktlib.new(seed=1).command_log == []


def test_time_reads_and_writes_as_packet_tracer_does():
    t = datetime(2026, 11, 24, 12, 15, 6)
    assert format_time(t) == "Tue Nov 24 12:15:06 2026"
    assert parse_time("Tue Nov 24 12:15:06 2026") == t
    assert format_time(datetime(2026, 11, 3, 9, 5, 1)) == "Tue Nov 3 09:05:01 2026"
    assert parse_time("Tue Nov  3 09:05:01 2026") == datetime(2026, 11, 3, 9, 5, 1)
    assert parse_time("yesterday") is None and parse_time("Tue Foo 24 12:15:06 2026") is None


def test_log_command_writes_what_packet_tracer_writes(tmp_path):
    net = pktlib.load(FIXTURES / "rich2-answer.pkt")
    r1 = net.device("R1")
    entry = r1.log_command("sh ip int br", at=datetime(2026, 11, 24, 12, 15, 6), resolved="show ip interface brief")
    # the bytes of the entry Packet Tracer wrote when this was typed on 24 Nov
    want = (
        "547565204e6f762032342031323a31353a30362032303236005231005231230073682069"
        "7020696e742062720073686f7720697020696e74657266616365206272696566"
    )
    assert req(net.root, "COMMAND_LOGS")[-1].text == want
    assert entry == LogEntry(datetime(2026, 11, 24, 12, 15, 6), "R1", "R1#", "sh ip int br", "show ip interface brief")
    net.save(tmp_path / "out.pkt")
    back = pktlib.load(tmp_path / "out.pkt")
    assert back.command_log == [*pktlib.load(FIXTURES / "rich2-answer.pkt").command_log, entry]


def test_log_command_defaults_and_refusals():
    net = pktlib.new(seed=2)
    r1 = net.router("R1", "2911")
    e = r1.log_command("enable", at=datetime(2026, 1, 2, 3, 4, 5), prompt="R1>")
    assert (e.prompt, e.resolved) == ("R1>", "enable")
    assert r1.log_command("show run", at=datetime(2026, 1, 2, 3, 4, 6)).prompt == "R1#"
    with pytest.raises(NotFound):
        net.log_command("R9", "enable", at=datetime(2026, 1, 2), prompt="R9>")
    for bad in ("", "   ", "two\nlines", "nul\0here"):
        with pytest.raises(PktError):
            r1.log_command(bad, at=datetime(2026, 1, 2))
    assert len(net.command_log) == 2


def test_clear_empties_the_log_and_keeps_the_element():
    net = pktlib.load(FIXTURES / "rich2-answer.pkt")
    net.clear_command_log()
    assert net.command_log == [] and net.root.find("COMMAND_LOGS") is not None
    pktlib.new(seed=3).clear_command_log()  # nothing there: fine


def test_cli_log(capsys):
    assert main(["log", str(FIXTURES / "rich2-answer.pkt")]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "2026-10-27 15:50:36  ISP  ISP>enable"
    assert out[2] == "2026-10-27 15:50:36  ISP  ISP(config)#interface fa0/3  (interface FastEthernet0/3)"
    assert out[-1] == "11 command(s)"
    assert main(["log", str(FIXTURES / "routed.pkt")]) == 0
    assert "the command log is empty" in capsys.readouterr().out
