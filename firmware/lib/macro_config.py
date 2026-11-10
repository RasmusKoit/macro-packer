"""Load and validate macros.json.

Key names are resolved through an injected function so this module runs
both on CircuitPython (with adafruit_hid's Keycode) and on desktop Python
for tests.

Parsed result:
    {
        "hide_drive": bool,  # acted on by boot.py at power-up
        "hardware": {"button_pin": str, "profile_button_pin": str,
                     "display_clk": str, "display_dio": str,
                     "display_brightness": int},
        "profiles": [{"number": int, "name": str,
                      "display_name": str or None,  # shown instead of P001
                      "cooldown_ms": int,
                      "delay_between_macros_ms": int,
                      "macros": [{"name": str, "steps": [step, ...]}]}],
                     # sorted by number, the order the profile button cycles in
        "active": int,  # index into profiles
    }
where each step is one of
    ("tap", (keycode, ...), hold_ms)
    ("press", (keycode, ...))
    ("release", (keycode, ...))
    ("wait", ms)
    ("click", buttons, hold_ms)   # buttons: mouse button bitmask
    ("mouse_press", buttons)
    ("mouse_release", buttons)
    ("scroll", clicks)            # positive scrolls up
"""

import json

import segments
import timefmt

SUPPORTED_VERSION = 1
DEFAULT_HOLD_MS = 30
DEFAULT_DELAY_BETWEEN_MACROS_MS = 50
MAX_HELD_KEYS = 6  # USB boot keyboard report limit, not counting modifiers
MODIFIER_FIRST = 0xE0  # LEFT_CONTROL .. RIGHT_GUI live in a separate byte
MODIFIER_LAST = 0xE7
MAX_STEP_MS = 60000
MAX_COOLDOWN_MS = timefmt.MAX_SECONDS * 1000  # 99:59 on the display
MAX_PROFILE_NUMBER = 999  # shown as "P123" on the display
MAX_NAME_LEN = 40  # longest key or pin name looked up on the board
MAX_MESSAGE_LEN = 300  # error messages quote user values; keep them readable
MAX_HINT_DEPTH = 64  # json_syntax_hint gives up beyond this nesting
MAX_SCROLL = 127  # wheel clicks per scroll step (one HID report)

DEFAULT_HARDWARE = {
    "button_pin": "GP2",
    "profile_button_pin": "GP3",
    "display_clk": "GP4",
    "display_dio": "GP5",
    "display_brightness": 4,
}

PIN_FIELDS = ("button_pin", "profile_button_pin", "display_clk", "display_dio")
KEY_ACTIONS = ("tap", "press", "release")
MOUSE_ACTIONS = ("click", "mouse_press", "mouse_release")
ACTIONS = KEY_ACTIONS + ("wait",) + MOUSE_ACTIONS + ("scroll",)
HOLD_ACTIONS = ("tap", "click")  # the ones that take hold_ms

# Bits of the HID mouse report's button byte (CircuitPython's mouse has 5).
MOUSE_BUTTONS = {"LEFT": 1, "RIGHT": 2, "MIDDLE": 4, "BACK": 8, "FORWARD": 16}
MOUSE_BUTTON_NAMES = "LEFT, RIGHT, MIDDLE, BACK or FORWARD"  # dicts are unordered on the board

# Friendly names on top of the adafruit_hid Keycode attribute names.
ALIASES = {
    "0": "ZERO",
    "1": "ONE",
    "2": "TWO",
    "3": "THREE",
    "4": "FOUR",
    "5": "FIVE",
    "6": "SIX",
    "7": "SEVEN",
    "8": "EIGHT",
    "9": "NINE",
    "SHIFT": "LEFT_SHIFT",
    "CTRL": "LEFT_CONTROL",
    "CONTROL": "LEFT_CONTROL",
    "ALT": "LEFT_ALT",
    "WIN": "LEFT_GUI",
    "SPACE": "SPACEBAR",
    "ESC": "ESCAPE",
    "DEL": "DELETE",
    "INS": "INSERT",
    "PGUP": "PAGE_UP",
    "PGDN": "PAGE_DOWN",
    "UP": "UP_ARROW",
    "DOWN": "DOWN_ARROW",
    "LEFT": "LEFT_ARROW",
    "RIGHT": "RIGHT_ARROW",
    "`": "GRAVE_ACCENT",
    "-": "MINUS",
    "=": "EQUALS",
}


class ConfigError(Exception):
    pass


def make_resolver(keycodes):
    """Build a name -> keycode function from a Keycode-like class."""

    def resolve(name):
        key = name.strip().upper()
        key = ALIASES.get(key, key)
        # Real names are short; CircuitPython's getattr raises on names of
        # 256+ bytes instead of returning the default.
        if key.startswith("_") or len(key) > MAX_NAME_LEN:
            return None
        code = getattr(keycodes, key, None)
        return code if type(code) is int else None

    return resolve


def load(path, resolve_key):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ConfigError("cannot read %s: %s" % (path, e))
    if raw.startswith(b"\xef\xbb\xbf"):  # Notepad's "UTF-8 with BOM"
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except ValueError:  # UnicodeError
        raise ConfigError("%s is not valid UTF-8 text" % path)
    try:
        data = json.loads(text)
    except Exception as e:  # ValueError; TypeError for a list where a key belongs; deep nesting
        # CircuitPython's json doesn't say where the error is, so guess.
        try:
            hint = json_syntax_hint(text)
        except Exception:  # e.g. MemoryError on a huge file; a hint is optional
            hint = None
        hint = hint or "check for a missing or extra comma, quote or bracket"
        raise ConfigError("%s is not valid JSON (%s): %s" % (path, e, hint))
    try:
        return parse(data, resolve_key)
    except ConfigError:
        raise
    except Exception as e:
        # Anything unforeseen (e.g. MemoryError on a huge file) must still end
        # in a stable "Err" screen, not a crash and restart loop.
        raise ConfigError("%s: unexpected problem (%s: %s)" % (path, type(e).__name__, e))


def load_hardware(path):
    """Just the hardware section, best effort, so "Err" can appear on the
    user's own display pins when the rest of the config is broken.
    Falls back to DEFAULT_HARDWARE on any problem."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        return _parse_hardware(json.loads(raw.decode("utf-8")).get("hardware", {}))
    except Exception:
        return dict(DEFAULT_HARDWARE)


def json_syntax_hint(text):
    """Best guess at a hand-editing mistake, or None.

    Mistakes CircuitPython's json rejects are reported first. It skips
    commas and colons like whitespace, so comma mistakes only break
    stricter parsers (like the PC tests) and are the last resort.
    """
    line = 1
    in_string = escaped = False
    stack = []  # (bracket, line) of open containers
    prev, prev_line = "", 1  # end of the last value or punctuation outside strings
    soft = None  # first comma mistake seen
    mismatch = None  # first bracket closed by the wrong kind
    word, word_line = "", 1  # bareword or number being read
    i, n = 0, len(text)
    while i <= n:
        ch = text[i] if i < n else ""
        nxt = text[i + 1] if i + 1 < n else ""
        i += 1
        if in_string:
            if ch in ("\n", "\r", ""):
                return "line %d: missing closing quote" % line
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                prev, prev_line = '"', line
            continue
        if ch and (ch.isalpha() or ch.isdigit() or ch in "+-."):
            if not word:
                if soft is None and _ends_value(prev):
                    soft = "line %d: missing comma (or colon)" % prev_line
                word_line = line
            word += ch
            continue
        if word:
            if word[0].isalpha() and word not in ("true", "false", "null"):
                if word.lower() in ("none", "null"):
                    return "line %d: write %s as null" % (word_line, word)
                if word.lower() in ("true", "false"):
                    return "line %d: write %s as %s" % (word_line, word, word.lower())
                return 'line %d: %s needs double quotes ("%s")' % (word_line, word, word)
            prev, prev_line = word[-1], word_line
            word = ""
        if ch == "":
            break
        if ch == "\n" or (ch == "\r" and nxt != "\n"):
            line += 1
        elif ch in " \t\r":
            pass
        elif ch == "#" or (ch == "/" and nxt and nxt in "/*"):
            return "line %d: comments aren't allowed in JSON" % line
        elif ch == "'":
            return "line %d: use double quotes (\") instead of single quotes" % line
        elif ch in '"{[':
            if soft is None and _ends_value(prev):
                soft = "line %d: missing comma (or colon)" % prev_line
            if ch == '"':
                in_string = True
            elif len(stack) >= MAX_HINT_DEPTH:
                # Real configs nest about 6 deep; don't run the board out of memory.
                return "line %d: brackets nested too deep" % line
            else:
                stack.append((ch, line))
                prev, prev_line = ch, line
        elif ch in "}]":
            if soft is None and prev == ",":
                soft = "line %d: remove the comma before '%s'" % (prev_line, ch)
            if not stack:
                return "line %d: extra '%s'" % (line, ch)
            opener, opened = stack.pop()
            if mismatch is None and (opener == "{") != (ch == "}"):
                mismatch = "line %d: '%s' closes the '%s' from line %d" % (line, ch, opener, opened)
            prev, prev_line = ch, line
        elif ch in ",:":
            prev, prev_line = ch, line
        else:
            return "line %d: unexpected character '%s'" % (line, ch)
    if stack:
        # A wrong closer usually explains why something is left open.
        opener, opened = stack[-1]
        return mismatch or "line %d: '%s' is never closed" % (opened, opener)
    return soft or mismatch


def _ends_value(ch):
    return ch != "" and (ch in '"}]el' or ch.isdigit())


def parse(data, resolve_key):
    _require_dict(data, "config")
    _check_fields(
        data,
        ("version", "hide_drive", "hardware", "active_profile", "profiles"),
        ("version", "profiles"),
        "config",
    )
    version = data["version"]
    if type(version) is not int or version != SUPPORTED_VERSION:
        _fail("version", "expected %d, got %s" % (SUPPORTED_VERSION, _json_repr(version)))

    # Read by boot.py; validated here so typos show up as Err.
    hide_drive = data.get("hide_drive", False)
    if type(hide_drive) is not bool:
        _fail("hide_drive", "must be true or false, got %s" % _json_repr(hide_drive))

    hardware = _parse_hardware(data.get("hardware", {}))

    raw_profiles = data["profiles"]
    if not isinstance(raw_profiles, list) or not raw_profiles:
        _fail("profiles", "must be a non-empty list")
    profiles = []
    for i, raw in enumerate(raw_profiles):
        profile = _parse_profile(raw, "profiles[%d]" % i, resolve_key)
        for other in profiles:
            if other["name"] == profile["name"]:
                _fail("profiles[%d].name" % i, 'duplicate profile name "%s"' % profile["name"])
            if other["number"] == profile["number"]:
                _fail("profiles[%d].number" % i, "duplicate profile number %d" % profile["number"])
        profiles.append(profile)
    profiles.sort(key=lambda p: p["number"])

    active = 0
    if "active_profile" in data:
        name = _string(data["active_profile"], "active_profile")
        for i, profile in enumerate(profiles):
            if profile["name"] == name:
                active = i
                break
        else:
            _fail("active_profile", 'no profile named "%s"' % name)

    return {"hide_drive": hide_drive, "hardware": hardware, "profiles": profiles, "active": active}


def _parse_hardware(raw):
    _require_dict(raw, "hardware")
    _check_fields(raw, tuple(DEFAULT_HARDWARE), (), "hardware")
    hardware = dict(DEFAULT_HARDWARE)
    used = {}
    for field in PIN_FIELDS:
        if field in raw:
            name = _string(raw[field], "hardware." + field).strip().upper()
            if not name or len(name) > MAX_NAME_LEN:
                _fail("hardware." + field, "must be a pin name like GP2")
            hardware[field] = name
        pin = hardware[field]
        if pin in used:
            _fail("hardware." + field, 'pin "%s" is already used by hardware.%s' % (pin, used[pin]))
        used[pin] = field
    if "display_brightness" in raw:
        hardware["display_brightness"] = _int(
            raw["display_brightness"], "hardware.display_brightness", 0, 7
        )
    return hardware


def _parse_profile(raw, where, resolve_key):
    _require_dict(raw, where)
    _check_fields(
        raw,
        ("number", "name", "display_name", "cooldown_ms", "delay_between_macros_ms", "macros"),
        ("number", "name", "cooldown_ms", "macros"),
        where,
    )
    raw_macros = raw["macros"]
    if not isinstance(raw_macros, list) or not raw_macros:
        _fail(where + ".macros", "must be a non-empty list")
    display_name = None
    if "display_name" in raw:
        display_name = _display_name(raw["display_name"], where + ".display_name")
    macros = [
        _parse_macro(m, "%s.macros[%d]" % (where, i), resolve_key)
        for i, m in enumerate(raw_macros)
    ]
    _check_held_keys(macros, where)
    return {
        "number": _int(raw["number"], where + ".number", 0, MAX_PROFILE_NUMBER),
        "name": _string(raw["name"], where + ".name"),
        "display_name": display_name,
        "cooldown_ms": _int(raw["cooldown_ms"], where + ".cooldown_ms", 0, MAX_COOLDOWN_MS),
        "delay_between_macros_ms": _int(
            raw.get("delay_between_macros_ms", DEFAULT_DELAY_BETWEEN_MACROS_MS),
            where + ".delay_between_macros_ms",
            0,
            MAX_STEP_MS,
        ),
        "macros": macros,
    }


def _check_held_keys(macros, where):
    # Pressed keys stay down until released (or the button press ends), even
    # across macros, so the HID 6-key limit applies to the running total.
    held = set()
    for m, macro in enumerate(macros):
        for s, step in enumerate(macro["steps"]):
            action = step[0]
            if action == "release":
                held -= set(step[1])
            elif action in ("press", "tap"):
                down = held | set(c for c in step[1] if not _is_modifier(c))
                if len(down) > MAX_HELD_KEYS:
                    _fail("%s.macros[%d].steps[%d]" % (where, m, s),
                          "this would hold %d keys at once; USB keyboards allow at most %d "
                          "(modifiers like SHIFT don't count)" % (len(down), MAX_HELD_KEYS))
                # A tap releases its keys afterwards, even ones a press held.
                held = down if action == "press" else held - set(step[1])


def _is_modifier(code):
    return MODIFIER_FIRST <= code <= MODIFIER_LAST


def _parse_macro(raw, where, resolve_key):
    _require_dict(raw, where)
    _check_fields(raw, ("name", "steps"), ("name", "steps"), where)
    raw_steps = raw["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        _fail(where + ".steps", "must be a non-empty list")
    return {
        "name": _string(raw["name"], where + ".name"),
        "steps": [
            _parse_step(s, "%s.steps[%d]" % (where, i), resolve_key)
            for i, s in enumerate(raw_steps)
        ],
    }


def _parse_step(raw, where, resolve_key):
    _require_dict(raw, where)
    actions = [a for a in ACTIONS if a in raw]
    if not actions:
        _check_fields(raw, ACTIONS + ("hold_ms",), (), where)  # names a misspelled action
    if len(actions) != 1:
        _fail(where, "needs exactly one of " + ", ".join('"%s"' % a for a in ACTIONS))
    action = actions[0]
    allowed = (action, "hold_ms") if action in HOLD_ACTIONS else (action,)
    _check_fields(raw, allowed, (action,), where)
    value, field = raw[action], where + "." + action

    if action == "wait":
        return ("wait", _int(value, field, 0, MAX_STEP_MS))
    if action == "scroll":
        clicks = _int(value, field, -MAX_SCROLL, MAX_SCROLL)
        if not clicks:
            _fail(field, "must not be 0 (positive scrolls up, negative down)")
        return ("scroll", clicks)
    if action in MOUSE_ACTIONS:
        codes = _mouse_buttons(value, field)
    else:
        codes = _keys(value, field, resolve_key)
    if action in HOLD_ACTIONS:
        hold_ms = _int(raw.get("hold_ms", DEFAULT_HOLD_MS), where + ".hold_ms", 1, MAX_STEP_MS)
        return (action, codes, hold_ms)
    return (action, codes)


def _mouse_buttons(value, where):
    """A button name or list of names -> one bitmask, as adafruit_hid's Mouse takes."""
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names:
        _fail(where, "must be a mouse button name or a non-empty list of them")
    buttons = 0
    for name in names:
        if not isinstance(name, str):
            _fail(where, "mouse button names must be strings, got %s" % _json_repr(name))
        bit = MOUSE_BUTTONS.get(name.strip().upper())
        if bit is None:
            _fail(where, 'unknown mouse button "%s" (use %s)' % (name, MOUSE_BUTTON_NAMES))
        buttons |= bit
    return buttons


def _keys(value, where, resolve_key):
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names:
        _fail(where, "must be a key name or a non-empty list of key names")
    codes = []
    for name in names:
        if not isinstance(name, str):
            _fail(where, "key names must be strings, got %s" % _json_repr(name))
        code = resolve_key(name)
        if code is None:
            upper = name.upper()
            if "CLICK" in upper or "MOUSE" in upper:
                _fail(where, 'unknown key "%s"; for mouse buttons use a "click" step, '
                      'e.g. {"click": "LEFT"}' % name)
            _fail(where, 'unknown key "%s"' % name)
        codes.append(code)
    return tuple(codes)


def _fail(where, message):
    message = "%s: %s" % (where, message)
    if len(message) > MAX_MESSAGE_LEN:
        message = message[:MAX_MESSAGE_LEN - 3] + "..."
    raise ConfigError(message)


def _require_dict(value, where):
    if not isinstance(value, dict):
        _fail(where, "must be an object {...}")


def _check_fields(obj, allowed, required, where):
    for field in obj:
        if field not in allowed:
            _fail(where, 'unknown field "%s"' % field)
    for field in required:
        if field not in obj:
            _fail(where, 'missing field "%s"' % field)


def _int(value, where, minimum, maximum):
    # type() check rather than isinstance(): rejects true/false and 30.0
    if type(value) is not int:
        _fail(where, "must be a whole number, got %s" % _json_repr(value))
    if value < minimum or value > maximum:
        _fail(where, "must be between %d and %d, got %d" % (minimum, maximum, value))
    return value


def _display_name(value, where):
    _string(value, where)
    if not value.strip():
        _fail(where, "must not be only spaces")
    if len(value) > segments.WIDTH:
        _fail(where, '"%s" is longer than %d characters' % (value, segments.WIDTH))
    for ch in value:
        if not segments.can_show(ch):
            _fail(where, '"%s" can\'t be shown on a 7-segment display (use digits, '
                  '"-", "_", space or: %s)' % (ch, segments.LETTERS))
    return value


def _string(value, where):
    if not isinstance(value, str) or not value:
        _fail(where, "must be a non-empty string")
    return value


def _json_repr(value):
    # Show values the way they are written in JSON (null, true, "text").
    if isinstance(value, (list, dict)):
        # dumps would recurse into deeply nested input and can overflow.
        return "a list" if isinstance(value, list) else "an object"
    try:
        text = json.dumps(value)
    except Exception:
        return type(value).__name__
    return text if len(text) <= 40 else text[:37] + "..."
