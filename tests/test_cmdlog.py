"""The command log (Options > View Command Log). Seen in Packet Tracer 8.2 on 24 Nov 2026:
every command typed at a CLI is listed with its time, device, prompt and what IOS made of
it, in a .pkt and in a .pka opened as a student; each LOG_ENTRY is those five fields,
NUL-separated, in hex."""

from datetime import datetime
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pktlib
from pktlib import LogEntry, NotFound, PktError
from pktlib._cli import main
from pktlib._cmdlog import format_time, parse_time, prompted
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


def test_prompts_follow_the_mode_ios_is_in():
    got = prompted(
        "R1",
        ["en", "configure terminal", "int g0/1", " no shut", "interface g0/1.10", "exit", "line con 0", "end"],
    )
    assert [p for p, _ in got] == [
        "R1>",
        "R1#",
        "R1(config)#",
        "R1(config-if)#",
        "R1(config-if)#",
        "R1(config-subif)#",
        "R1(config)#",
        "R1(config-line)#",
    ]
    assert [c for _, c in got][3] == "no shut"  # indentation dropped, as a paste's is
    more = prompted(
        "SW1", ["conf t", "vlan 10", "name X", "ip access-list extended A", "exit", "exit", "disable"], "exec"
    )
    assert [p for p, _ in more] == [
        "SW1#",
        "SW1(config)#",
        "SW1(config-vlan)#",
        "SW1(config-vlan)#",
        "SW1(config-ext-nacl)#",
        "SW1(config)#",
        "SW1#",
    ]
    assert prompted("R1", ["", "!", "en"]) == [("R1>", "en")]
    with pytest.raises(PktError, match="unknown CLI mode"):
        prompted("R1", ["en"], "privileged")


def test_log_commands_paces_and_prompts(tmp_path):
    def build() -> list[LogEntry]:
        r1 = pktlib.new(seed=21).router("R1", "2911")
        return r1.log_commands(["enable", "conf t", "hostname R1", "end"], start=datetime(2026, 11, 24, 9, 0, 0, 5))

    log = build()
    assert [e.prompt for e in log] == ["R1>", "R1#", "R1(config)#", "R1(config)#"]
    assert log[0].time == datetime(2026, 11, 24, 9, 0, 0)  # whole seconds, as Packet Tracer keeps them
    gaps = [(b.time - a.time).total_seconds() for a, b in pairwise(log) if a.time and b.time]
    assert all(30 <= g <= 60 and g == int(g) for g in gaps)
    assert [e.time for e in build()] == [e.time for e in log]  # same seed, same log

    net = pktlib.new(seed=22)
    sw = net.switch("SW1")
    fixed = sw.log_commands("enable\nshow vlan brief", start=datetime(2026, 1, 1), gap=1)
    assert [e.time for e in fixed] == [datetime(2026, 1, 1, 0, 0, 0), datetime(2026, 1, 1, 0, 0, 1)]
    net.save(tmp_path / "log.pkt")
    assert pktlib.load(tmp_path / "log.pkt").command_log == fixed
    for bad in ((60, 30), (-1, 5)):
        with pytest.raises(PktError, match="gap"):
            sw.log_commands(["en"], start=datetime(2026, 1, 1), gap=bad)
    with pytest.raises(PktError, match="gap"):
        sw.log_commands(["en"], start=datetime(2026, 1, 1), gap=-1)


def test_log_commands_can_end_now():
    r1 = pktlib.new(seed=24).router("R1", "2911")
    now = datetime(2026, 11, 24, 15, 0, 0)
    log = r1.log_commands(["enable", "conf t", "end"], end=now)
    assert log[-1].time == now and log[0].time is not None and log[0].time < now
    with pytest.raises(PktError, match="start or an end"):
        r1.log_commands(["en"])
    with pytest.raises(PktError, match="start or an end"):
        r1.log_commands(["en"], start=now, end=now)


@given(st.datetimes(min_value=datetime(1970, 1, 1), max_value=datetime(9999, 12, 31)))
def test_any_time_reads_back_as_written(t):
    t = t.replace(microsecond=0)
    assert parse_time(format_time(t)) == t


_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\0"), min_size=1, max_size=30
).filter(lambda s: s.strip() != "")


@settings(max_examples=50, deadline=None)
@given(st.lists(st.tuples(st.datetimes(min_value=datetime(2000, 1, 1)), _TEXT, _TEXT), min_size=1, max_size=5))
def test_any_log_survives_a_save(tmp_path_factory, entries):
    net = pktlib.new(seed=23)
    r1 = net.router("R1", "2911")
    want = [r1.log_command(cmd, at=t.replace(microsecond=0), prompt=p) for t, p, cmd in entries]
    path = tmp_path_factory.mktemp("log") / "log.pkt"
    net.save(path)
    assert pktlib.load(path).command_log == want
