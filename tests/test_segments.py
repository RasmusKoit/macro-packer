from segments import CHARS, DIGITS, LETTERS, can_show, encode


def test_letters_list_matches_table():
    assert sorted(LETTERS) == sorted(c for c in CHARS if c.isalpha())


def test_encode_pads_and_truncates():
    assert encode("P001") == [CHARS["P"], DIGITS[0], DIGITS[0], DIGITS[1]]
    assert encode("Sor") == [CHARS["S"], CHARS["o"], CHARS["r"], 0]
    assert encode("bArbS") == encode("bArb")
    assert encode("K1") == [0, DIGITS[1], 0, 0]  # undrawable letters are blank


def test_unshowable_letters():
    for ch in "KMVWXZkmvwxz":
        assert not can_show(ch)
    for ch in "dIAb0123456789 -_":
        assert can_show(ch)
