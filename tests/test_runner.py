import pytest

import macro_runner


class FakeHID:
    """Keyboard and mouse sharing one call log, so their order is checked.
    Raises OSError ("USB busy") on the Nth call if asked."""

    def __init__(self, fail_on=None, fail_release_all=()):
        self.calls = []
        self.fail_on = fail_on
        self.fail_release_all = fail_release_all  # "kb" and/or "mouse"
        self.keyboard = _Device(self, "kb")
        self.mouse = _Device(self, "mouse")

    def run(self, profile):
        return macro_runner.run_profile(self.keyboard, self.mouse, profile)


class _Device:
    def __init__(self, hid, prefix):
        self.hid, self.prefix = hid, prefix

    def _record(self, *call):
        self.hid.calls.append((self.prefix,) + call)
        if self.hid.fail_on is not None and len(self.hid.calls) == self.hid.fail_on:
            raise OSError("USB busy")

    def press(self, *keys):  # Keyboard: keycodes; Mouse: one button bitmask
        self._record("press", keys)

    def release(self, *keys):
        self._record("release", keys)

    def move(self, x=0, y=0, wheel=0):
        self._record("move", wheel)

    def release_all(self):
        self.hid.calls.append((self.prefix, "release_all"))
        if self.prefix in self.hid.fail_release_all:
            raise OSError("USB busy")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(macro_runner.time, "sleep", lambda s: None)


def profile(*macros):
    return {"delay_between_macros_ms": 0,
            "macros": [{"name": "m", "steps": list(steps)} for steps in macros]}


TWO_MACROS = profile([("tap", (1,), 30)], [("press", (2,)), ("release", (2,))])


def test_all_sent():
    hid = FakeHID()
    assert hid.run(TWO_MACROS) == (True, True)
    assert hid.calls == [("kb", "press", (1,)), ("kb", "release", (1,)),
                         ("kb", "press", (2,)), ("kb", "release", (2,)),
                         ("kb", "release_all")]


def test_first_press_fails():
    hid = FakeHID(fail_on=1)
    assert hid.run(TWO_MACROS) == (False, False)
    assert hid.calls[-1] == ("kb", "release_all")


def test_tap_release_fails_after_key_went_down():
    # The key reached the host, so the skill may have fired.
    assert FakeHID(fail_on=2).run(TWO_MACROS) == (False, True)


def test_later_macro_fails():
    assert FakeHID(fail_on=3).run(TWO_MACROS) == (False, True)


def test_only_release_all_fails():
    assert FakeHID(fail_release_all=("kb",)).run(TWO_MACROS) == (False, True)


def test_waits_only():
    hid = FakeHID()
    assert hid.run(profile([("wait", 10)])) == (True, False)
    assert hid.calls == [("kb", "release_all")]


def test_other_errors_still_release_keys():
    class Boom(Exception):
        pass

    hid = FakeHID()
    hid.keyboard.press = lambda *keys: (_ for _ in ()).throw(Boom())
    with pytest.raises(Boom):
        hid.run(TWO_MACROS)
    assert hid.calls == [("kb", "release_all")]


MOUSE_MACRO = profile([("press", (7,)), ("click", 1, 40), ("release", (7,)),
                       ("mouse_press", 2), ("mouse_release", 2), ("scroll", -3)])


def test_mouse_steps():
    hid = FakeHID()
    assert hid.run(MOUSE_MACRO) == (True, True)
    assert hid.calls == [("kb", "press", (7,)),
                         ("mouse", "press", (1,)), ("mouse", "release", (1,)),
                         ("kb", "release", (7,)),
                         ("mouse", "press", (2,)), ("mouse", "release", (2,)),
                         ("mouse", "move", -3),
                         ("kb", "release_all"), ("mouse", "release_all")]


@pytest.mark.parametrize("macro", [[("click", 1, 30)], [("scroll", 1)]])
def test_click_or_scroll_counts_as_started(macro):
    assert FakeHID().run(profile(macro)) == (True, True)


def test_mouse_release_alone_is_not_started():
    hid = FakeHID()
    assert hid.run(profile([("mouse_release", 1)])) == (True, False)
    assert hid.calls[-1] == ("mouse", "release_all")


def test_failed_click_still_releases_mouse():
    hid = FakeHID(fail_on=1)
    assert hid.run(profile([("click", 4, 30)])) == (False, False)
    assert hid.calls[-2:] == [("kb", "release_all"), ("mouse", "release_all")]


def test_mouse_release_all_fails():
    hid = FakeHID(fail_release_all=("mouse",))
    assert hid.run(profile([("click", 1, 30)])) == (False, True)


def test_keyboard_only_profile_leaves_mouse_alone():
    hid = FakeHID()
    hid.run(TWO_MACROS)
    assert not [c for c in hid.calls if c[0] == "mouse"]
