import pytest

import pktlib
from pktlib._cli import main
from tests.conftest import ROUTED


def test_decode_encode_round_trip(tmp_path):
    assert main(["decode", str(ROUTED), str(tmp_path / "x.xml")]) == 0
    assert (tmp_path / "x.xml").read_bytes().startswith(b"<PACKETTRACER5>")
    assert main(["encode", str(tmp_path / "x.xml"), str(tmp_path / "y.pkt")]) == 0
    assert pktlib.decode((tmp_path / "y.pkt").read_bytes()) == pktlib.decode(ROUTED.read_bytes())


def test_info(capsys):
    assert main(["info", str(ROUTED)]) == 0
    out = capsys.readouterr().out
    assert "R1  Router 1841" in out and "Serial0/0/0 10.0.12.1/30  -> R2.Serial0/0/0 (serial)" in out
    assert "gateway 10.1.0.1" in out


def test_dump_writes_runnable_python(tmp_path):
    assert main(["dump", str(ROUTED), str(tmp_path / "routed.py")]) == 0
    src = (tmp_path / "routed.py").read_text()
    assert "net.save('routed.pkt')" in src
    compile(src, "routed.py", "exec")


@pytest.mark.parametrize("argv", [["decode", "missing.pkt"], ["info", "missing.pkt"], ["dump", "missing.pkt"]])
def test_missing_file(argv, capsys):
    assert main(argv) == 1
    assert "pktlib:" in capsys.readouterr().err


def test_not_a_pkt(tmp_path, capsys):
    bad = tmp_path / "bad.pkt"
    bad.write_bytes(b"definitely not packet tracer")
    assert main(["info", str(bad)]) == 1


def test_usage():
    with pytest.raises(SystemExit):
        main([])


def test_audit_several_files_in_process(tmp_path, capsys):
    clean = tmp_path / "clean.pkt"
    pktlib.new(seed=1).save(clean)
    damaged = tmp_path / "damaged.pkt"
    damaged.write_bytes(b"not a pkt")
    assert main(["audit", str(clean), str(damaged), str(tmp_path / "missing.pkt")]) == 1
    out, err = capsys.readouterr()
    assert "clean.pkt: nothing found" in out and "1 of 3 files clean" in out
    assert "damaged.pkt" in err and "missing.pkt" in err
    assert main(["audit", str(clean)]) == 0
