"""Countdown formatting for the 4-digit mm:ss display."""

NS_PER_S = 1000000000
MAX_SECONDS = 99 * 60 + 59


def remaining_to_mmss(remaining_ns):
    """Return (m_tens, m_ones, s_tens, s_ones) for the time left.

    Rounds up, so the display shows 00:01 until the cooldown has fully
    elapsed, and clamps to 99:59 (the most four digits can show).
    """
    if remaining_ns <= 0:
        return (0, 0, 0, 0)
    seconds = min(-(-remaining_ns // NS_PER_S), MAX_SECONDS)
    minutes, seconds = divmod(seconds, 60)
    return (minutes // 10, minutes % 10, seconds // 10, seconds % 10)
