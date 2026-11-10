"""7-segment character shapes, shared by the display driver and the config
validator. Bits: a=0x01 (top), b=0x02, c=0x04, d=0x08 (bottom), e=0x10,
f=0x20, g=0x40 (middle), clockwise from the top.
"""

DIGITS = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F)
COLON = 0x80  # on the second digit of clock-style modules
WIDTH = 4

# Letters without a recognisable 7-segment shape (K, M, V, W, X, Z) are
# absent on purpose; case matters because many letters exist in only one.
CHARS = {
    " ": 0x00,
    "-": 0x40,
    "_": 0x08,
    "A": 0x77,
    "b": 0x7C,
    "C": 0x39,
    "c": 0x58,
    "d": 0x5E,
    "E": 0x79,
    "F": 0x71,
    "G": 0x3D,
    "H": 0x76,
    "h": 0x74,
    "I": 0x30,
    "J": 0x1E,
    "L": 0x38,
    "n": 0x54,
    "O": 0x3F,
    "o": 0x5C,
    "P": 0x73,
    "q": 0x67,
    "r": 0x50,
    "S": 0x6D,
    "t": 0x78,
    "U": 0x3E,
    "u": 0x1C,
    "y": 0x6E,
}


# CircuitPython dicts don't keep insertion order, so list the letters for
# error messages explicitly.
LETTERS = "AbCcdEFGHhIJLnOoPqrStUuy"


def can_show(ch):
    return ch in CHARS or "0" <= ch <= "9"


def encode(text):
    """Segment bytes for up to WIDTH characters, left-aligned."""
    out = []
    for ch in (text + " " * WIDTH)[:WIDTH]:
        if "0" <= ch <= "9":
            out.append(DIGITS[ord(ch) - ord("0")])
        else:
            out.append(CHARS.get(ch, 0))
    return out
