from timefmt import NS_PER_S, remaining_to_mmss


def test_zero_and_negative_show_ready():
    assert remaining_to_mmss(0) == (0, 0, 0, 0)
    assert remaining_to_mmss(-5 * NS_PER_S) == (0, 0, 0, 0)


def test_rounds_up_partial_seconds():
    assert remaining_to_mmss(1) == (0, 0, 0, 1)
    assert remaining_to_mmss(NS_PER_S) == (0, 0, 0, 1)
    assert remaining_to_mmss(NS_PER_S + 1) == (0, 0, 0, 2)


def test_minutes_and_seconds():
    assert remaining_to_mmss(30 * NS_PER_S) == (0, 0, 3, 0)
    assert remaining_to_mmss(90 * NS_PER_S) == (0, 1, 3, 0)
    assert remaining_to_mmss((12 * 60 + 5) * NS_PER_S) == (1, 2, 0, 5)


def test_clamps_to_99_59():
    assert remaining_to_mmss(100 * 60 * NS_PER_S) == (9, 9, 5, 9)
