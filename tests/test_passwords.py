"""IOS password forms. Values taken from files Packet Tracer 8.2 saved."""

from hypothesis import given
from hypothesis import strategies as st

from pktlib._passwords import decode7, matches, md5_crypt


def test_type7_from_packet_tracer():
    assert decode7("0822455D0A16") == "cisco"
    assert decode7("0822455D0A165445415F59") == "cisco12345"


def test_type5_from_packet_tracer():
    # a lecturer's starter file; its notes say the enable password is class
    assert matches("5 $1$mERr$9cTjUIEqNGurQiFU.ZeCi1", "class")
    assert not matches("5 $1$mERr$9cTjUIEqNGurQiFU.ZeCi1", "cisco")
    # Packet Tracer's own hash of cisco12345
    assert matches("5 $1$mERr$WvpW0n5HghRrqnrwXCUUl.", "cisco12345")


def test_plain_and_typed_forms():
    assert matches("cisco12345", "cisco12345") and matches("0 cisco12345", "cisco12345")
    assert matches("7 0822455D0A16", "cisco") and not matches("7 0822455D0A16", "cisco1")


@given(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=20),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789./", min_size=1, max_size=8),
)
def test_fuzz_md5_crypt_round_trips(password, salt):
    assert matches("5 " + md5_crypt(password, salt), password)
