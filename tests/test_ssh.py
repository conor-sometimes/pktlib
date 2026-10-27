"""RSA keys for SSH: Packet Tracer keeps them in ENGINE/SECURITY, not in the
config, so `crypto key generate rsa` has to be done by pktlib directly."""

import pytest

import pktlib
from pktlib import PktError


def test_a_key_is_named_after_the_host_and_domain():
    r = pktlib.new(seed=101).router("R1", "2901")
    assert r.rsa_key is None
    r.config("ip domain-name contoso.com")
    r.generate_rsa_key(1024)
    assert r.rsa_key == ("R1.contoso.com", 1024)
    sec = r.engine.find("SECURITY")
    assert sec.findtext("TEMP_KEY_NAME") == "R1.contoso.com.server"
    rows = sec.findtext("RSA_KEY").split("\n")
    assert len(rows) == 3 and all(len(w) == 8 for w in rows[0].split())
    assert sec.findtext("RSA_KEY") != sec.findtext("TEMP_RSA_KEY")


def test_no_domain_no_key():
    r = pktlib.new(seed=102).router("R1", "2901")
    with pytest.raises(PktError, match="ip domain-name"):
        r.generate_rsa_key()


@pytest.mark.parametrize("bits", [359, 2049])
def test_the_modulus_is_range_checked(bits):
    r = pktlib.new(seed=103).router("R1", "2901")
    r.config("ip domain-name contoso.com")
    with pytest.raises(PktError, match="360 to 2048"):
        r.generate_rsa_key(bits)


def test_keys_survive_a_save():
    net = pktlib.new(seed=104)
    sw = net.switch("S1", "2960-24TT")
    sw.config("ip domain-name contoso.com")
    sw.generate_rsa_key(2048)
    again = pktlib.Network.from_bytes(net.to_bytes())
    assert again.device("S1").rsa_key == ("S1.contoso.com", 2048)
