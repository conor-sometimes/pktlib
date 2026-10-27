"""The .pkt container: known-good files, round trips, and everything that should fail."""

import contextlib
import zlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pktlib
from pktlib._codec import _scramble_outer, _unscramble_outer, _xor_inner
from tests.conftest import SOURCES, examples


def test_known_good_file_decodes(routed_xml):
    assert routed_xml.startswith(b"<PACKETTRACER5>")
    assert b"<VERSION>8.2.0.0162</VERSION>" in routed_xml


@pytest.mark.parametrize("name", ["modules.pkt", "catalogue_network.pkt", "catalogue_end.pkt"])
def test_every_source_file_decodes(name):
    xml = pktlib.decode((SOURCES / name).read_bytes())
    assert xml.startswith(b"<PACKETTRACER5>")


def test_reencode_decodes_to_the_same_xml(routed_xml):
    assert pktlib.decode(pktlib.encode(routed_xml)) == routed_xml


def test_encode_is_deterministic(routed_xml):
    assert pktlib.encode(routed_xml) == pktlib.encode(routed_xml)


@settings(max_examples=examples(40), deadline=None)
@given(st.binary(max_size=3000))
def test_any_bytes_round_trip(blob):
    assert pktlib.decode(pktlib.encode(blob)) == blob


@settings(max_examples=examples(50), deadline=None)
@given(st.binary(max_size=500))
def test_outer_scramble_is_an_involution_pair(blob):
    assert _unscramble_outer(_scramble_outer(blob)) == blob
    assert _xor_inner(_xor_inner(blob)) == blob


@pytest.mark.parametrize("junk", [b"", b"\x00", b"hello", bytes(16), bytes(100), b"<PACKETTRACER5/>"])
def test_garbage_is_rejected(junk):
    with pytest.raises(ValueError):
        pktlib.decode(junk)


@settings(max_examples=examples(60), deadline=None)
@given(st.binary(max_size=400))
def test_fuzz_decode_only_raises_value_errors(blob):
    with contextlib.suppress(ValueError):  # TagMismatch is a ValueError too
        pktlib.decode(blob)


@settings(max_examples=examples(60), deadline=None)
@given(st.binary(max_size=400))
def test_fuzz_decode_without_tag_check_still_only_raises_value_errors(blob):
    with contextlib.suppress(ValueError):
        pktlib.decode(blob, verify=False)


def test_truncated_file_is_rejected(routed_bytes):
    for cut in (1, 16, 100, len(routed_bytes) // 2):
        with pytest.raises(ValueError):
            pktlib.decode(routed_bytes[:-cut])


@pytest.mark.parametrize("where", [0, 1, 100, 5000, -17, -1])
def test_one_flipped_bit_is_rejected(routed_bytes, where):
    b = bytearray(routed_bytes)
    b[where] ^= 0x10
    with pytest.raises(pktlib.TagMismatch):
        pktlib.decode(bytes(b))


def test_wrong_length_header_is_rejected():
    xml = b"<PACKETTRACER5/>"
    packed = (len(xml) + 1).to_bytes(4, "big") + zlib.compress(xml)
    from pktlib._codec import KEY, NONCE
    from pktlib._twofish import eax_encrypt

    data = _scramble_outer(eax_encrypt(KEY, NONCE, _xor_inner(packed)))
    with pytest.raises(ValueError, match="header says"):
        pktlib.decode(data)


@pytest.mark.parametrize("bad", ["text", 123, None, ["b"]])
def test_wrong_types(bad):
    with pytest.raises(TypeError):
        pktlib.decode(bad)
    with pytest.raises(TypeError):
        pktlib.encode(bad)


def test_bytearray_is_fine(routed_bytes):
    assert pktlib.decode(bytearray(routed_bytes)).startswith(b"<PACKETTRACER5>")
