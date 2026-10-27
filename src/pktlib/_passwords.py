"""IOS password forms, so a config can be checked against the password it
should hold: `password 7 0822455D0A16` (type 7, reversible) and
`secret 5 $1$salt$hash` (type 5, MD5-crypt, checked by hashing again)."""

from __future__ import annotations

import hashlib

# Cisco's fixed type 7 key
_XLAT = b"dsfd;kfoA,.iyewrkldJKDHSUBsgvca69834ncxv9873254k;fg87"
_ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def decode7(encoded: str) -> str:
    """'0822455D0A16' -> 'cisco'."""
    seed = int(encoded[:2])
    data = bytes.fromhex(encoded[2:])
    return "".join(chr(b ^ _XLAT[(seed + i) % len(_XLAT)]) for i, b in enumerate(data))


def md5_crypt(password: str, salt: str) -> str:
    """The `$1$salt$hash` an IOS type 5 secret holds for `password`."""
    pw, salt_b = password.encode(), salt.encode()[:8]
    alt = hashlib.md5(pw + salt_b + pw).digest()
    h = hashlib.md5(pw + b"$1$" + salt_b)
    for i in range(len(pw)):
        h.update(alt[i % 16 : i % 16 + 1])
    i = len(pw)
    while i:
        h.update(b"\0" if i & 1 else pw[:1])
        i >>= 1
    final = h.digest()
    for r in range(1000):
        h = hashlib.md5()
        h.update(pw if r & 1 else final)
        if r % 3:
            h.update(salt_b)
        if r % 7:
            h.update(pw)
        h.update(final if r & 1 else pw)
        final = h.digest()
    out = ""
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = (final[a] << 16) | (final[b] << 8) | final[c]
        for _ in range(4):
            out += _ITOA64[v & 0x3F]
            v >>= 6
    v = final[11]
    for _ in range(2):
        out += _ITOA64[v & 0x3F]
        v >>= 6
    return f"$1${salt}${out}"


def matches(stored: str, password: str) -> bool:
    """Whether a password as it appears in a config ('cisco12345',
    '7 0822455D0A16', '5 $1$mERr$...', or the same without the type) is
    `password`."""
    parts = stored.split()
    kind, value = (parts[0], parts[-1]) if len(parts) > 1 else ("0", parts[0])
    if kind == "7":
        return decode7(value) == password
    if kind == "5" or value.startswith("$1$"):
        salt = value.split("$")[2]
        return md5_crypt(password, salt) == value
    return value == password
