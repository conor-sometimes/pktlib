"""Turn .pkt / .pka bytes into Packet Tracer's XML and back.

The layers (Packet Tracer 6 onwards, worked out by the pka2xml project):

1. the whole file is byte-reversed and XORed with (L - i*L) & 0xFF, L = file length
2. Twofish-EAX, key sixteen 0x89 bytes, nonce sixteen 0x10 bytes, 16-byte tag at the end
3. the plaintext is XORed with (n - i) & 0xFF, n = plaintext length
4. what is left is Qt's qCompress: a 4-byte big-endian length, then a zlib stream
"""

from __future__ import annotations

import zlib

from ._errors import FileFormatError
from ._twofish import eax_decrypt, eax_encrypt

KEY = b"\x89" * 16
NONCE = b"\x10" * 16


def _unscramble_outer(data: bytes) -> bytes:
    n = len(data)
    return bytes(data[n - 1 - i] ^ ((n - i * n) & 0xFF) for i in range(n))


def _scramble_outer(data: bytes) -> bytes:
    n = len(data)
    out = bytearray(n)
    for i in range(n):
        out[n - 1 - i] = data[i] ^ ((n - i * n) & 0xFF)
    return bytes(out)


def _xor_inner(data: bytes) -> bytes:
    n = len(data)
    return bytes(b ^ ((n - i) & 0xFF) for i, b in enumerate(data))


def decode(data: bytes | bytearray, *, verify: bool = True) -> bytes:
    """Encrypted .pkt bytes -> XML bytes."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("decode() wants bytes")
    plain = eax_decrypt(KEY, NONCE, _unscramble_outer(bytes(data)), verify=verify)
    packed = _xor_inner(plain)
    if len(packed) < 4:
        raise FileFormatError("too short to be a .pkt")
    size = int.from_bytes(packed[:4], "big")
    try:
        xml = zlib.decompress(packed[4:])
    except zlib.error as e:
        raise FileFormatError(f"not a .pkt (zlib: {e})") from None
    if len(xml) != size:
        raise FileFormatError(f"header says {size} bytes, zlib gave {len(xml)}")
    return xml


def encode(xml: bytes, level: int = 9) -> bytes:
    """XML bytes -> encrypted .pkt bytes Packet Tracer will open."""
    if not isinstance(xml, (bytes, bytearray)):
        raise TypeError("encode() wants bytes")
    xml = bytes(xml)
    packed = len(xml).to_bytes(4, "big") + zlib.compress(xml, level)
    return _scramble_outer(eax_encrypt(KEY, NONCE, _xor_inner(packed)))
