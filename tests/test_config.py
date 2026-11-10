import copy
import os

import pytest

import macro_config
from macro_config import ConfigError, make_resolver, parse

EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "firmware", "macros.json")


class FakeKeycode:
    """Stand-in for adafruit_hid.keycode.Keycode with a few real values."""

    A = 0x04
    E = 0x08
    Q = 0x14
    ONE = 0x1E
    TWO = 0x1F
    THREE = 0x20
    FOUR = 0x21
    FIVE = 0x22
    SPACEBAR = 0x2C
    F1 = 0x3A
    LEFT_CONTROL = 0xE0
    LEFT_SHIFT = 0xE1
    BOGUS = "not a keycode"  # exercises the type check in the resolver
    _PRIVATE = 1  # exercises the underscore guard

    @staticmethod
    def modifier_bit(keycode):
        return 0


resolve = make_resolver(FakeKeycode)


def minimal():
    return {
        "version": 1,
        "profiles": [
            {
                "number": 1,
                "name": "p",
                "cooldown_ms": 1000,
                "macros": [{"name": "m", "steps": [{"tap": "1"}]}],
            }
        ],
    }


def expect_error(data, fragment):
    with pytest.raises(ConfigError) as info:
        parse(data, resolve)
    assert fragment in str(info.value)


def test_example_file_is_valid():
    config = macro_config.load(EXAMPLE_PATH, resolve)
    profile = config["profiles"][config["active"]]
    assert profile["name"] == "diablo"
    assert profile["cooldown_ms"] == 30000
    assert config["hardware"]["profile_button_pin"] == "GP3"
    assert [p["name"] for p in config["profiles"]] == ["diablo", "burst"]
    assert profile["macros"][3]["steps"] == [
        ("press", (FakeKeycode.LEFT_SHIFT,)),
        ("tap", (FakeKeycode.E,), 50),
        ("release", (FakeKeycode.LEFT_SHIFT,)),
    ]


def test_defaults_applied():
    config = parse(minimal(), resolve)
    assert config["hide_drive"] is False
    assert config["hardware"] == macro_config.DEFAULT_HARDWARE
    assert config["active"] == 0
    profile = config["profiles"][0]
    assert profile["delay_between_macros_ms"] == macro_config.DEFAULT_DELAY_BETWEEN_MACROS_MS
    assert profile["macros"][0]["steps"] == [("tap", (FakeKeycode.ONE,), macro_config.DEFAULT_HOLD_MS)]


def test_resolver_aliases_and_case():
    assert resolve("shift") == FakeKeycode.LEFT_SHIFT
    assert resolve("Ctrl") == FakeKeycode.LEFT_CONTROL
    assert resolve("space") == FakeKeycode.SPACEBAR
    assert resolve("f1") == FakeKeycode.F1
    assert resolve("a") == FakeKeycode.A
    assert resolve("  a ") == FakeKeycode.A
    assert resolve("MODIFIER_BIT") is None
    assert resolve("bogus") is None
    assert resolve("_private") is None
    assert resolve("__class__") is None


def test_chord_and_wait():
    data = minimal()
    data["profiles"][0]["macros"][0]["steps"] = [{"tap": ["CTRL", "Q"]}, {"wait": 40}]
    steps = parse(data, resolve)["profiles"][0]["macros"][0]["steps"]
    assert steps == [("tap", (FakeKeycode.LEFT_CONTROL, FakeKeycode.Q), 30), ("wait", 40)]


def add_profile(data, name, number):
    profile = copy.deepcopy(data["profiles"][0])
    profile["name"] = name
    profile["number"] = number
    data["profiles"].append(profile)


def test_active_profile_selects_by_name():
    data = minimal()
    add_profile(data, "second", 2)
    data["active_profile"] = "second"
    assert parse(data, resolve)["active"] == 1


def test_profiles_sorted_by_number():
    data = minimal()
    data["profiles"][0]["number"] = 7
    add_profile(data, "three", 3)
    add_profile(data, "five", 5)
    data["active_profile"] = "p"
    config = parse(data, resolve)
    assert [p["number"] for p in config["profiles"]] == [3, 5, 7]
    assert config["profiles"][config["active"]]["name"] == "p"


def test_unknown_key_reports_location():
    data = minimal()
    data["profiles"][0]["macros"][0]["steps"].append({"tap": "SHFT"})
    expect_error(data, 'profiles[0].macros[0].steps[1].tap: unknown key "SHFT"')


def test_missing_fields():
    data = minimal()
    del data["profiles"][0]["cooldown_ms"]
    expect_error(data, 'profiles[0]: missing field "cooldown_ms"')
    expect_error({"version": 1}, 'missing field "profiles"')


def test_bad_step_shapes():
    data = minimal()
    data["profiles"][0]["macros"][0]["steps"] = [{"Tap": "1"}]
    expect_error(data, 'steps[0]: unknown field "Tap"')
    data["profiles"][0]["macros"][0]["steps"] = [{}]
    expect_error(data, "needs exactly one of")
    data["profiles"][0]["macros"][0]["steps"] = [{"hold_ms": 5}]
    expect_error(data, "needs exactly one of")
    data["profiles"][0]["macros"][0]["steps"] = [{"tap": "1", "wait": 5}]
    expect_error(data, "needs exactly one of")
    data["profiles"][0]["macros"][0]["steps"] = [{"press": "1", "hold_ms": 5}]
    expect_error(data, 'unknown field "hold_ms"')


def with_steps(*macros):
    data = minimal()
    data["profiles"][0]["macros"] = [{"name": "m%d" % i, "steps": s} for i, s in enumerate(macros)]
    return data


SIX_KEYS = ["A", "E", "Q", "1", "2", "3"]


def test_held_keys_limit():
    # Modifiers don't count towards the six.
    parse(with_steps([{"tap": ["CTRL", "SHIFT"] + SIX_KEYS}]), resolve)
    expect_error(with_steps([{"tap": SIX_KEYS + ["4"]}]),
                 "macros[0].steps[0]: this would hold 7 keys")
    # Pressed keys stay down for later steps...
    expect_error(with_steps([{"press": SIX_KEYS}, {"tap": "4"}]),
                 "macros[0].steps[1]: this would hold 7 keys")
    # ...and later macros, until released.
    expect_error(with_steps([{"press": SIX_KEYS}], [{"tap": "4"}]),
                 "macros[1].steps[0]: this would hold 7 keys")
    parse(with_steps([{"press": SIX_KEYS}, {"release": "A"}, {"tap": "4"}]), resolve)
    # Tapped keys are released straight away; re-pressing a held key is fine.
    parse(with_steps([{"tap": SIX_KEYS}, {"tap": SIX_KEYS}]), resolve)
    parse(with_steps([{"press": SIX_KEYS}, {"tap": "A"}]), resolve)
    # Tapping a held key releases it too (that's what the runner does).
    parse(with_steps([{"press": SIX_KEYS}, {"tap": "A"}, {"tap": "4"}]), resolve)
    # Releasing a key that isn't held is harmless; held modifiers never count.
    parse(with_steps([{"release": "4"}, {"press": "SHIFT"}], [{"tap": SIX_KEYS}]), resolve)


def test_mouse_steps():
    steps = parse(with_steps([
        {"press": "SHIFT"}, {"click": "left"}, {"release": "SHIFT"},
        {"click": ["LEFT", " right "], "hold_ms": 80},
        {"mouse_press": "MIDDLE"}, {"mouse_release": ["middle"]},
        {"click": "BACK"}, {"click": "FORWARD"},
        {"scroll": 3}, {"scroll": -127},
    ]), resolve)["profiles"][0]["macros"][0]["steps"]
    assert steps == [
        ("press", (FakeKeycode.LEFT_SHIFT,)), ("click", 1, 30), ("release", (FakeKeycode.LEFT_SHIFT,)),
        ("click", 3, 80), ("mouse_press", 4), ("mouse_release", 4),
        ("click", 8, 30), ("click", 16, 30), ("scroll", 3), ("scroll", -127),
    ]


def test_mouse_buttons_dont_count_as_held_keys():
    parse(with_steps([{"press": SIX_KEYS}, {"mouse_press": "LEFT"}, {"click": "RIGHT"},
                      {"scroll": 1}]), resolve)


@pytest.mark.parametrize("step, fragment", [
    ({"click": "LEFT_BUTTON"}, 'click: unknown mouse button "LEFT_BUTTON" (use LEFT, RIGHT'),
    ({"click": []}, "click: must be a mouse button name or a non-empty list"),
    ({"click": 1}, "click: must be a mouse button name"),
    ({"mouse_press": [1]}, "mouse_press: mouse button names must be strings, got 1"),
    ({"click": "LEFT", "hold_ms": 0}, "hold_ms: must be between 1 and 60000"),
    ({"mouse_press": "LEFT", "hold_ms": 5}, 'unknown field "hold_ms"'),
    ({"scroll": 0}, "scroll: must not be 0"),
    ({"scroll": 128}, "scroll: must be between -127 and 127"),
    ({"scroll": 1.5}, "scroll: must be a whole number"),
    ({"scroll": "up"}, "scroll: must be a whole number"),
    ({"click": "LEFT", "tap": "1"}, "needs exactly one of"),
    ({"Click": "LEFT"}, 'unknown field "Click"'),
    ({"tap": "LEFT_CLICK"}, 'for mouse buttons use a "click" step'),
    ({"press": "mouse1"}, 'for mouse buttons use a "click" step'),
])
def test_rejects_bad_mouse_steps(step, fragment):
    expect_error(with_steps([step]), "steps[0]")
    expect_error(with_steps([step]), fragment)


def test_hide_drive_flag():
    assert parse(dict(minimal(), hide_drive=True), resolve)["hide_drive"] is True
    expect_error(dict(minimal(), hide_drive="yes"), "hide_drive: must be true or false")
    expect_error(dict(minimal(), hide_drive=1), "hide_drive: must be true or false")


def test_display_name():
    data = minimal()
    assert parse(data, resolve)["profiles"][0]["display_name"] is None
    data["profiles"][0]["display_name"] = "nEcr"
    assert parse(data, resolve)["profiles"][0]["display_name"] == "nEcr"
    data["profiles"][0]["display_name"] = "Necr"
    expect_error(data, "profiles[0].display_name: \"N\" can't be shown")
    data["profiles"][0]["display_name"] = "bArbs"
    expect_error(data, "longer than 4 characters")
    data["profiles"][0]["display_name"] = ""
    expect_error(data, "must be a non-empty string")
    data["profiles"][0]["display_name"] = "    "
    expect_error(data, "must not be only spaces")


def test_number_validation():
    data = minimal()
    data["profiles"][0]["cooldown_ms"] = 30.5
    expect_error(data, "must be a whole number")
    data["profiles"][0]["cooldown_ms"] = True
    expect_error(data, "must be a whole number")
    data["profiles"][0]["cooldown_ms"] = 100 * 60 * 1000
    expect_error(data, "must be between")
    data["profiles"][0]["cooldown_ms"] = None
    expect_error(data, "must be a whole number, got null")


def test_profile_level_errors():
    data = minimal()
    data["active_profile"] = "nope"
    expect_error(data, 'no profile named "nope"')
    data = minimal()
    add_profile(data, "p", 2)
    expect_error(data, "duplicate profile name")
    data = minimal()
    add_profile(data, "other", 1)
    expect_error(data, "profiles[1].number: duplicate profile number 1")
    data = minimal()
    del data["profiles"][0]["number"]
    expect_error(data, 'missing field "number"')
    data = minimal()
    data["profiles"][0]["number"] = 1000
    expect_error(data, "profiles[0].number: must be between 0 and 999")
    expect_error(dict(minimal(), version=2), "version: expected 1")
    expect_error(dict(minimal(), version=True), "version: expected 1, got true")
    expect_error(dict(minimal(), version=1.0), "version: expected 1, got 1.0")
    expect_error(dict(minimal(), hardware={"buton_pin": "GP2"}), 'unknown field "buton_pin"')


def test_hardware_pins():
    config = parse(dict(minimal(), hardware={"button_pin": " gp7 "}), resolve)
    assert config["hardware"]["button_pin"] == "GP7"
    expect_error(dict(minimal(), hardware={"button_pin": "GP4"}),
                 'hardware.display_clk: pin "GP4" is already used by hardware.button_pin')
    expect_error(dict(minimal(), hardware={"display_brightness": 8}),
                 "hardware.display_brightness: must be between 0 and 7")


@pytest.mark.parametrize("change, fragment", [
    (lambda d: d.update(extra=1), 'config: unknown field "extra"'),
    (lambda d: d.update(profiles=[]), "profiles: must be a non-empty list"),
    (lambda d: d.update(profiles={}), "profiles: must be a non-empty list"),
    (lambda d: d.update(hardware=[]), "hardware: must be an object"),
    (lambda d: d.update(active_profile=1), "active_profile: must be a non-empty string"),
    (lambda d: d["profiles"][0].update(macros=[]), "profiles[0].macros: must be a non-empty list"),
    (lambda d: d["profiles"][0].update(name=""), "profiles[0].name: must be a non-empty string"),
    (lambda d: d["profiles"][0].update(delay_between_macros_ms=-1),
     "delay_between_macros_ms: must be between 0 and 60000"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=[]), "steps: must be a non-empty list"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=["1"]), "steps[0]: must be an object"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=[{"tap": []}]),
     "steps[0].tap: must be a key name or a non-empty list"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=[{"tap": [1]}]),
     "steps[0].tap: key names must be strings, got 1"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=[{"tap": "1", "hold_ms": 0}]),
     "steps[0].hold_ms: must be between 1 and 60000"),
    (lambda d: d["profiles"][0]["macros"][0].update(steps=[{"wait": 60001}]),
     "steps[0].wait: must be between 0 and 60000"),
])
def test_rejects_bad_input(change, fragment):
    data = minimal()
    change(data)
    expect_error(data, fragment)


def test_load_reports_bad_json(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text('{\n  "version": 1,\n  // profiles\n}')
    with pytest.raises(ConfigError, match="not valid JSON.*line 3: comments aren't allowed"):
        macro_config.load(str(path), resolve)
    path.write_bytes(b'{"version": 1, "x": "\xff"}')
    with pytest.raises(ConfigError, match="not valid UTF-8"):
        macro_config.load(str(path), resolve)
    with pytest.raises(ConfigError, match="cannot read"):
        macro_config.load(str(tmp_path / "missing.json"), resolve)


def test_hostile_input_only_raises_config_error(tmp_path):
    # Found by fuzzing: none of these may escape as anything but ConfigError.
    path = tmp_path / "macros.json"
    for text in ["[" * 5000,
                 '{"version": ' + "[" * 2990 + "]" * 2990 + "}",
                 '{"version": 1, "profiles": "' + "x" * 100000 + '"}']:
        path.write_text(text)
        with pytest.raises(ConfigError):
            macro_config.load(str(path), resolve)


def test_long_names_and_messages():
    assert resolve("A" * 300) is None  # CircuitPython's getattr would raise
    data = minimal()
    data["profiles"][0]["macros"][0]["steps"] = [{"tap": "A" * 300}]
    expect_error(data, "unknown key")
    for bad in (" ", "GP" + "1" * 300):
        expect_error(dict(minimal(), hardware={"button_pin": bad}),
                     "hardware.button_pin: must be a pin name like GP2")
    data = minimal()
    data["profiles"][0]["display_name"] = "b" * 100000
    with pytest.raises(ConfigError) as info:
        parse(data, resolve)
    assert len(str(info.value)) <= macro_config.MAX_MESSAGE_LEN
    expect_error(dict(minimal(), version=[1]), "version: expected 1, got a list")


def test_load_hardware_survives_broken_config(tmp_path):
    path = tmp_path / "macros.json"
    path.write_text('{"hardware": {"display_clk": "GP10", "display_dio": "GP11"},'
                    ' "profiles": "broken"}')
    hw = macro_config.load_hardware(str(path))
    assert (hw["display_clk"], hw["display_dio"]) == ("GP10", "GP11")
    path.write_text("{ not json")
    assert macro_config.load_hardware(str(path)) == macro_config.DEFAULT_HARDWARE
    assert macro_config.load_hardware(str(tmp_path / "missing.json")) == macro_config.DEFAULT_HARDWARE


def test_load_accepts_utf8_bom(tmp_path):
    path = tmp_path / "macros.json"
    with open(EXAMPLE_PATH, "rb") as f:
        path.write_bytes(b"\xef\xbb\xbf" + f.read())
    assert macro_config.load(str(path), resolve)["profiles"][0]["name"] == "diablo"


@pytest.mark.parametrize("text, hint", [
    # Rejected by CircuitPython's json too, so reported first.
    ('{\n  // note\n  "a": 1\n}', "line 2: comments aren't allowed"),
    ('{\n  "a": 1 # note\n}', "line 2: comments aren't allowed"),
    ('{\n  "a": 1,\n  // tap "1"\n  "b": 2,\n}', "line 3: comments aren't allowed"),
    ("{\n  'a': 1\n}", "line 2: use double quotes"),
    ('{"a": True}', "line 1: write True as true"),
    ('{"a": None}', "line 1: write None as null"),
    ('{\n  tap: "1"\n}', 'line 2: tap needs double quotes ("tap")'),
    ('{\n  "a": "x\n}', "line 2: missing closing quote"),
    ('{"a": "x', "line 1: missing closing quote"),
    ('{\n  "a": [1, 2\n}', "line 3: '}' closes the '[' from line 2"),
    ('{\n  "a": [1, 2]\n', "line 1: '{' is never closed"),
    ('{"a": 1}}', "line 1: extra '}'"),
    ('{"a": 1;}', "line 1: unexpected character ';'"),
    # Only stricter parsers reject these.
    ('{\n  "a": 1,\n  "b": 2,\n}', "line 3: remove the comma before '}'"),
    ('[\n  1,\n]', "line 2: remove the comma before ']'"),
    ('{\r\n  "a": 1,\r\n}', "line 2: remove the comma"),  # Windows line endings
    ('{\r  "a": 1,\r}', "line 2: remove the comma"),  # old Mac line endings
    ('{\n  "a": 1\n  "b": 2\n}', "line 2: missing comma"),
    ('[\n  {"a": 1}\n  {"a": 2}\n]', "line 2: missing comma"),
    ('{\n  "a": true\n  "b": 2\n}', "line 2: missing comma"),
    ('[1]/', "line 1: unexpected character '/'"),  # a lone slash isn't a comment
    ("[" * 3000, "line 1: brackets nested too deep"),  # ran the board out of memory
    # Valid JSON.
    ('{"a": "x\\"y // not a comment",\n "b": 1}', None),
    ('{"a": [1, -2.5e3], "b": {"c": null, "d": false}}', None),
])
def test_json_syntax_hint(text, hint):
    result = macro_config.json_syntax_hint(text)
    if hint is None:
        assert result is None
    else:
        assert hint in result
