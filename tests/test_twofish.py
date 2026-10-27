"""Twofish against the paper's vectors; EAX round trips and tamper detection."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pktlib._twofish import Q0, Q1, TagMismatch, Twofish, _dbl, eax_decrypt, eax_encrypt
from tests.conftest import examples


def test_q_tables_are_permutations():
    assert sorted(Q0) == list(range(256))
    assert sorted(Q1) == list(range(256))


def test_q_table_first_entries_match_the_paper():
    assert Q0[:3] == (0xA9, 0x67, 0xB3)
    assert Q1[:2] == (0x75, 0xF3)


def test_zero_key_zero_block():
    assert Twofish(bytes(16)).encrypt_block(bytes(16)).hex().upper() == "9F589F5CF6122C32B6BFEC2F2AE8C35A"


def test_paper_iterated_vectors_128bit():
    """The paper's 'ecb_tbl' chain: KEY(i+1) = PT(i), PT(i+1) = CT(i)."""
    key, pt = bytes(16), bytes(16)
    seen = {}
    for i in range(1, 50):
        ct = Twofish(key).encrypt_block(pt)
        seen[i] = (key.hex().upper(), pt.hex().upper(), ct.hex().upper())
        key, pt = pt, ct
    assert seen[2][2] == "D491DB16E7B1C39E86CB086B789F5419"
    assert seen[3][2] == "019F9809DE1711858FAAC3A3BA20FBC3"
    assert seen[49] == (
        "BCA724A54533C6987E14AA827952F921",
        "6B459286F3FFD28D49F15B1581B08E42",
        "5D9D4EEFFA9151575524F115815A12E0",
    )


@pytest.mark.parametrize("bad", [b"", bytes(15), bytes(17), bytes(24), bytes(32)])
def test_only_128_bit_keys(bad):
    with pytest.raises(ValueError):
        Twofish(bad)


def test_dbl_carries_into_0x87():
    assert _dbl(bytes(16)) == bytes(16)
    assert _dbl(b"\x80" + bytes(15)) == bytes(15) + b"\x87"
    assert _dbl(bytes(15) + b"\x01") == bytes(15) + b"\x02"


@settings(max_examples=examples(40), deadline=None)
@given(
    st.binary(min_size=16, max_size=16),
    st.binary(min_size=0, max_size=32),
    st.binary(max_size=200),
    st.binary(max_size=40),
)
def test_eax_round_trip(key, nonce, msg, header):
    sealed = eax_encrypt(key, nonce, msg, header)
    assert len(sealed) == len(msg) + 16
    assert eax_decrypt(key, nonce, sealed, header) == msg


@settings(max_examples=examples(30), deadline=None)
@given(st.binary(min_size=1, max_size=100), st.data())
def test_eax_any_bit_flip_is_caught(msg, data):
    key, nonce = b"k" * 16, b"n" * 16
    sealed = bytearray(eax_encrypt(key, nonce, msg))
    i = data.draw(st.integers(0, len(sealed) - 1))
    sealed[i] ^= 1 << data.draw(st.integers(0, 7))
    with pytest.raises(TagMismatch):
        eax_decrypt(key, nonce, bytes(sealed))


def test_eax_wrong_header_or_nonce_or_key_is_caught():
    sealed = eax_encrypt(b"k" * 16, b"n" * 16, b"hello", b"hdr")
    for key, nonce, hdr in (
        (b"K" * 16, b"n" * 16, b"hdr"),
        (b"k" * 16, b"N" * 16, b"hdr"),
        (b"k" * 16, b"n" * 16, b"x"),
    ):
        with pytest.raises(TagMismatch):
            eax_decrypt(key, nonce, sealed, hdr)


def test_eax_too_short():
    with pytest.raises(TagMismatch):
        eax_decrypt(b"k" * 16, b"n" * 16, bytes(15))


def test_eax_verify_false_skips_the_tag():
    sealed = bytearray(eax_encrypt(b"k" * 16, b"n" * 16, b"hello"))
    sealed[-1] ^= 1
    assert eax_decrypt(b"k" * 16, b"n" * 16, bytes(sealed), verify=False) == b"hello"
