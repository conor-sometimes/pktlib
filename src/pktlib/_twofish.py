"""Twofish block cipher (encrypt direction only), plus EAX mode on top of it.

Pure Python so pktlib has no dependencies. Packet Tracer only ever needs one
128-bit key, and EAX only uses the cipher's encrypt direction, so that is all
that is here. Checked against the Twofish paper's test vectors in tests/.
"""

from __future__ import annotations

from ._errors import TagMismatch

_Q0_T = (
    (0x8, 0x1, 0x7, 0xD, 0x6, 0xF, 0x3, 0x2, 0x0, 0xB, 0x5, 0x9, 0xE, 0xC, 0xA, 0x4),
    (0xE, 0xC, 0xB, 0x8, 0x1, 0x2, 0x3, 0x5, 0xF, 0x4, 0xA, 0x6, 0x7, 0x0, 0x9, 0xD),
    (0xB, 0xA, 0x5, 0xE, 0x6, 0xD, 0x9, 0x0, 0xC, 0x8, 0xF, 0x3, 0x2, 0x4, 0x7, 0x1),
    (0xD, 0x7, 0xF, 0x4, 0x1, 0x2, 0x6, 0xE, 0x9, 0xB, 0x3, 0x0, 0x8, 0x5, 0xC, 0xA),
)
_Q1_T = (
    (0x2, 0x8, 0xB, 0xD, 0xF, 0x7, 0x6, 0xE, 0x3, 0x1, 0x9, 0x4, 0x0, 0xA, 0xC, 0x5),
    (0x1, 0xE, 0x2, 0xB, 0x4, 0xC, 0x3, 0x7, 0x6, 0xD, 0xA, 0x5, 0xF, 0x9, 0x0, 0x8),
    (0x4, 0xC, 0x7, 0x5, 0x1, 0x6, 0x9, 0xA, 0x0, 0xE, 0xD, 0x8, 0x2, 0xB, 0x3, 0xF),
    (0xB, 0x9, 0x5, 0x1, 0xC, 0x3, 0xD, 0xE, 0x6, 0x4, 0x7, 0xF, 0x2, 0x0, 0x8, 0xA),
)
_MDS = ((0x01, 0xEF, 0x5B, 0x5B), (0x5B, 0xEF, 0xEF, 0x01), (0xEF, 0x5B, 0x01, 0xEF), (0xEF, 0x01, 0xEF, 0x5B))
_RS = (
    (0x01, 0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E),
    (0xA4, 0x56, 0x82, 0xF3, 0x1E, 0xC6, 0x68, 0xE5),
    (0x02, 0xA1, 0xFC, 0xC1, 0x47, 0xAE, 0x3D, 0x19),
    (0xA4, 0x55, 0x87, 0x5A, 0x58, 0xDB, 0x9E, 0x03),
)
_M32 = 0xFFFFFFFF


def _ror4(x: int, n: int) -> int:
    return ((x >> n) | (x << (4 - n))) & 0xF


def _make_q(t: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    out = []
    for x in range(256):
        a, b = x >> 4, x & 0xF
        a, b = a ^ b, (a ^ _ror4(b, 1) ^ (8 * a)) & 0xF
        a, b = t[0][a], t[1][b]
        a, b = a ^ b, (a ^ _ror4(b, 1) ^ (8 * a)) & 0xF
        a, b = t[2][a], t[3][b]
        out.append((b << 4) | a)
    return tuple(out)


Q0, Q1 = _make_q(_Q0_T), _make_q(_Q1_T)


def _gf_mul(a: int, b: int, poly: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= poly
        b >>= 1
    return r


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & _M32


def _ror(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & _M32


def _sbox_bytes(y: list[int], l0: int, l1: int) -> list[int]:
    """The q-box layers of h() for a 128-bit key (k = 2): L = (l0, l1)."""
    b0 = [(l0 >> (8 * i)) & 0xFF for i in range(4)]
    b1 = [(l1 >> (8 * i)) & 0xFF for i in range(4)]
    return [
        Q1[Q0[Q0[y[0]] ^ b1[0]] ^ b0[0]],
        Q0[Q0[Q1[y[1]] ^ b1[1]] ^ b0[1]],
        Q1[Q1[Q0[y[2]] ^ b1[2]] ^ b0[2]],
        Q0[Q1[Q1[y[3]] ^ b1[3]] ^ b0[3]],
    ]


def _mds(y: list[int]) -> int:
    z = 0
    for i in range(4):
        v = 0
        for j in range(4):
            v ^= _gf_mul(_MDS[i][j], y[j], 0x169)
        z |= v << (8 * i)
    return z


def _h(x: int, l0: int, l1: int) -> int:
    return _mds(_sbox_bytes([(x >> (8 * i)) & 0xFF for i in range(4)], l0, l1))


class Twofish:
    """Twofish with a 128-bit key. Only `encrypt_block` (all EAX needs)."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 16:
            raise ValueError("pktlib's Twofish only does 128-bit keys")
        m = [int.from_bytes(key[4 * i : 4 * i + 4], "little") for i in range(4)]
        me, mo = (m[0], m[2]), (m[1], m[3])
        s = []
        for i in range(2):
            chunk = key[8 * i : 8 * i + 8]
            word = 0
            for r in range(4):
                v = 0
                for c in range(8):
                    v ^= _gf_mul(_RS[r][c], chunk[c], 0x14D)
                word |= v << (8 * r)
            s.append(word)
        sl0, sl1 = s[1], s[0]  # L = (S1, S0) for the g function
        rho = 0x01010101
        k = []
        for i in range(20):
            a = _h((2 * i * rho) & _M32, me[0], me[1])
            b = _rol(_h(((2 * i + 1) * rho) & _M32, mo[0], mo[1]), 8)
            k.append((a + b) & _M32)
            k.append(_rol((a + 2 * b) & _M32, 9))
        self._k = k
        # g(X) = T0[x0] ^ T1[x1] ^ T2[x2] ^ T3[x3]: fold key, q-boxes and MDS into four tables.
        tables = []
        for j in range(4):
            col = []
            for x in range(256):
                y = [0, 0, 0, 0]
                y[j] = x
                sb = _sbox_bytes(y, sl0, sl1)[j]
                col.append(sum(_gf_mul(_MDS[i][j], sb, 0x169) << (8 * i) for i in range(4)))
            tables.append(tuple(col))
        self._t = tables

    def _g(self, x: int) -> int:
        t0, t1, t2, t3 = self._t
        return t0[x & 0xFF] ^ t1[(x >> 8) & 0xFF] ^ t2[(x >> 16) & 0xFF] ^ t3[x >> 24]

    def encrypt_block(self, block: bytes) -> bytes:
        """Encrypt one 16-byte block."""
        k, g = self._k, self._g
        r = [int.from_bytes(block[4 * i : 4 * i + 4], "little") ^ k[i] for i in range(4)]
        r0, r1, r2, r3 = r
        for rnd in range(16):
            t0 = g(r0)
            t1 = g(_rol(r1, 8))
            f0 = (t0 + t1 + k[2 * rnd + 8]) & _M32
            f1 = (t0 + 2 * t1 + k[2 * rnd + 9]) & _M32
            r2, r3 = _ror(r2 ^ f0, 1), _rol(r3, 1) ^ f1
            r0, r1, r2, r3 = r2, r3, r0, r1
        out = (r2 ^ k[4], r3 ^ k[5], r0 ^ k[6], r1 ^ k[7])
        return b"".join(w.to_bytes(4, "little") for w in out)


# --- EAX mode (Bellare, Rogaway, Wagner), as Crypto++ implements it ---------


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=False))


def _dbl(block: bytes) -> bytes:
    n = int.from_bytes(block, "big") << 1
    if n >> 128:
        n = (n & ((1 << 128) - 1)) ^ 0x87
    return n.to_bytes(16, "big")


def _cmac(cipher: Twofish, msg: bytes) -> bytes:
    k1 = _dbl(cipher.encrypt_block(bytes(16)))
    k2 = _dbl(k1)
    if msg and len(msg) % 16 == 0:
        last = _xor(msg[-16:], k1)
        body = msg[:-16]
    else:
        tail = msg[len(msg) - len(msg) % 16 :]
        last = _xor(tail + b"\x80" + bytes(15 - len(tail)), k2)
        body = msg[: len(msg) - len(tail)]
    x = bytes(16)
    for i in range(0, len(body), 16):
        x = cipher.encrypt_block(_xor(x, body[i : i + 16]))
    return cipher.encrypt_block(_xor(x, last))


def _omac(cipher: Twofish, t: int, msg: bytes) -> bytes:
    return _cmac(cipher, bytes(15) + bytes([t]) + msg)


def _ctr(cipher: Twofish, counter: bytes, data: bytes) -> bytes:
    n = int.from_bytes(counter, "big")
    out = bytearray()
    for i in range(0, len(data), 16):
        ks = cipher.encrypt_block(n.to_bytes(16, "big"))
        out += _xor(data[i : i + 16], ks)
        n = (n + 1) & ((1 << 128) - 1)
    return bytes(out)


def eax_encrypt(key: bytes, nonce: bytes, plaintext: bytes, header: bytes = b"") -> bytes:
    """Return ciphertext followed by the 16-byte tag."""
    c = Twofish(key)
    n = _omac(c, 0, nonce)
    h = _omac(c, 1, header)
    ct = _ctr(c, n, plaintext)
    tag = _xor(_xor(n, h), _omac(c, 2, ct))
    return ct + tag


def eax_decrypt(key: bytes, nonce: bytes, data: bytes, header: bytes = b"", *, verify: bool = True) -> bytes:
    """`data` is ciphertext followed by the 16-byte tag."""
    if len(data) < 16:
        raise TagMismatch("too short to be a .pkt")
    c = Twofish(key)
    ct, tag = data[:-16], data[-16:]
    n = _omac(c, 0, nonce)
    if verify:
        h = _omac(c, 1, header)
        if _xor(_xor(n, h), _omac(c, 2, ct)) != tag:
            raise TagMismatch("not a .pkt Packet Tracer saved, or damaged (its checksum doesn't match)")
    return _ctr(c, n, ct)
