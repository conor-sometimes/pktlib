"""ISR technology-package licences. Seen in Packet Tracer 8.2 on 25 Oct 2026,
on a 2901: `license boot module c2900 technology-package securityk9`, accept
the EULA, save, reload. PT then saved securityk9 with CURRENT_BOOT and
NEXT_REBOOT 2, "Active, In Use", the `license boot` line in the config, and the
CLI command set 2900_universal_security_15.1. With everything but the command
set, `show version` looked licensed yet every `crypto` line in the file was
dropped on load; with it, they load."""

import pytest

import pktlib
from pktlib import PktError


def test_enable_securityk9_on_a_2901():
    r = pktlib.new(seed=91).router("R1", "2901")
    assert r.licenses["securityk9"] != "Active, In Use"
    assert r.engine.findtext("CURRENT_COMMAND_SET") == "2900_universal_base_15.1"
    r.enable_license("securityk9")
    assert r.licenses["securityk9"] == "Active, In Use"
    assert r.engine.findtext("CURRENT_COMMAND_SET") == "2900_universal_security_15.1"
    assert "license boot module c2900 technology-package securityk9" in r.running_config
    lic = next(l for l in r.engine.iter("LICENSE") if l.findtext("FEATURE_NAME") == "securityk9")
    assert (lic.findtext("CURRENT_BOOT"), lic.findtext("NEXT_REBOOT")) == ("2", "2")


def test_enabling_twice_is_harmless():
    r = pktlib.new(seed=92).router("R1", "2901")
    r.enable_license()
    r.enable_license()
    assert r.running_config.count("license boot module c2900 technology-package securityk9") == 1
    assert r.engine.findtext("CURRENT_COMMAND_SET") == "2900_universal_security_15.1"


def test_licences_survive_a_save():
    net = pktlib.new(seed=93)
    net.router("R1", "2901").enable_license()
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.device("R1").licenses["securityk9"] == "Active, In Use"


def test_unknown_licences_and_models_are_refused():
    net = pktlib.new(seed=94)
    with pytest.raises(PktError, match="has no nosuchk9 licence"):
        net.router("R1", "2901").enable_license("nosuchk9")
    with pytest.raises(PktError, match=r"has no securityk9|doesn't know the licence module"):
        net.router("R2", "1841").enable_license("securityk9")
