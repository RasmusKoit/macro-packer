"""Macro button: one press sends the active profile's macros (keys, mouse
clicks and scrolling), then the TM1637 display counts down the cooldown
(mm:ss) and the button is ignored until it reaches 00:00. A second button
cycles through the profiles (on release), showing each profile's
display_name, or its number (e.g. "P002") if it has none. Every profile
has its own cooldown timer.

Edit /macros.json on the CIRCUITPY drive; saving it reloads this program.
"""

import time
import traceback

import keypad
import supervisor
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

import macro_config
import macro_runner
import pins
import timefmt
from tm1637 import TM1637

CONFIG_PATH = "/macros.json"
NS_PER_MS = 1000000
LABEL_NS = 1000 * NS_PER_MS
USB_ERROR_LABEL_NS = 2000 * NS_PER_MS
RELEASE_RETRY_NS = 2000 * NS_PER_MS
MACRO_BUTTON = 0  # key_number order in keypad.Keys
PROFILE_BUTTON = 1

display = None  # module-level so the last-resort handler can show "Err"


def halt_with_error(message):
    global display
    print("CONFIG ERROR:", message)
    print("Fix macros.json and save it; the board reloads automatically.")
    if display is None:
        # Use the configured display pins if that part of the file is usable,
        # otherwise the defaults.
        for hw in (macro_config.load_hardware(CONFIG_PATH), macro_config.DEFAULT_HARDWARE):
            try:
                board_pins = pins.resolve(hw)
                display = TM1637(board_pins["display_clk"], board_pins["display_dio"])
                break
            except Exception:
                pass
    if display is not None:
        display.show_text("Err ")
    while True:
        time.sleep(1)


def profile_label(profile):
    return profile["display_name"] or "P%03d" % profile["number"]


def current_view(now, cooldown_end, label_until, label):
    """What the display should show: a text label or (digits, colon)."""
    if now < label_until:
        return label
    remaining = cooldown_end - now
    # Solid colon when ready; blinking while counting down.
    colon = remaining <= 0 or remaining % timefmt.NS_PER_S >= timefmt.NS_PER_S // 2
    return (timefmt.remaining_to_mmss(remaining), colon)


def show(view):
    if isinstance(view, str):
        display.show_text(view)
    else:
        display.show_digits(view[0], view[1])


def connect_hid():
    """(keyboard, mouse) once a USB host is listening."""
    # Keyboard() waits silently for a host, so say why we're waiting.
    while not supervisor.runtime.usb_connected:
        display.show_text("USb ")
        time.sleep(0.2)
    while True:
        try:
            return Keyboard(usb_hid.devices), Mouse(usb_hid.devices)
        except OSError as e:
            print("Waiting for the USB host:", e)
            display.show_text("USb ")
            time.sleep(1)


def send_macros(keyboard, mouse, profile):
    """Returns (complete, started); see macro_runner.run_profile."""
    if not supervisor.runtime.usb_connected:
        print("Not sent: no USB host")
        return False, False
    return macro_runner.run_profile(keyboard, mouse, profile)


def run(buttons, profiles, active):
    keyboard, mouse = connect_hid()
    events = buttons.events
    # Drop presses made during startup, including the button still being held
    # from boot.py's "hold to show the drive", so they don't fire a macro.
    events.clear()

    cooldown_ends = [0] * len(profiles)  # per profile: monotonic_ns when it unlocks
    label, label_until = "", 0  # text shown instead of the timer until label_until
    release_pending = False  # a failed send may have left keys or buttons down on the host
    next_release_try = 0
    profile_pressed = False  # saw the profile button go down; switch when it comes up
    shown = None
    while True:
        event = events.get()
        if event and event.key_number == PROFILE_BUTTON:
            # Switch on release, and only for a press we saw: not one held
            # through startup or made while a macro was sending (cleared).
            if event.pressed:
                profile_pressed = True
            elif profile_pressed:
                profile_pressed = False
                # Every profile's countdown keeps running in the background.
                active = (active + 1) % len(profiles)
                label, label_until = profile_label(profiles[active]), time.monotonic_ns() + LABEL_NS
                print('Profile %s "%s"' % (label, profiles[active]["name"]))
        elif event and event.pressed:
            now = time.monotonic_ns()
            if event.key_number == MACRO_BUTTON and now >= cooldown_ends[active]:
                cooldown_ns = profiles[active]["cooldown_ms"] * NS_PER_MS
                # The display can't update while sending, so show the full
                # countdown now rather than a misleading "ready" 00:00.
                show((timefmt.remaining_to_mmss(cooldown_ns), True))
                shown = None
                complete, started = send_macros(keyboard, mouse, profiles[active])
                if started:
                    # Timed from the press, not from when sending finishes.
                    cooldown_ends[active] = now + cooldown_ns
                if not complete:
                    after = time.monotonic_ns()
                    label, label_until = "USb ", after + USB_ERROR_LABEL_NS
                    release_pending, next_release_try = True, after + RELEASE_RETRY_NS
                events.clear()  # drop presses made while sending
                profile_pressed = False
            # Macro presses during this profile's cooldown fall through and are ignored.

        now = time.monotonic_ns()
        if release_pending and now >= next_release_try and supervisor.runtime.usb_connected:
            try:
                keyboard.release_all()
                mouse.release_all()
                release_pending = False
            except OSError:
                # Measured after the call: a failed send_report blocks for a while.
                next_release_try = time.monotonic_ns() + RELEASE_RETRY_NS
            now = time.monotonic_ns()

        view = current_view(now, cooldown_ends[active], label_until, label)
        if view != shown:
            show(view)
            shown = view
        time.sleep(0.01)


def main():
    global display
    try:
        config = macro_config.load(CONFIG_PATH, macro_config.make_resolver(Keycode))
        hw = config["hardware"]
        board_pins = pins.resolve(hw)
        display = TM1637(board_pins["display_clk"], board_pins["display_dio"],
                         hw["display_brightness"])
        buttons = keypad.Keys((board_pins["button_pin"], board_pins["profile_button_pin"]),
                              value_when_pressed=False, pull=True)
    except (macro_config.ConfigError, ValueError) as e:
        halt_with_error(e)

    profiles = config["profiles"]
    active = config["active"]
    for i, profile in enumerate(profiles):
        print('%s%s "%s": %d macro(s), cooldown %d ms'
              % ("* " if i == active else "  ", profile_label(profile), profile["name"],
                 len(profile["macros"]), profile["cooldown_ms"]))

    display.show_text(profile_label(profiles[active]))  # startup profile
    time.sleep(1)  # also gives the host a moment to enumerate the HID device
    run(buttons, profiles, active)


try:
    main()
except Exception as e:
    # Last resort: never sit dead with a frozen display. Restart cleanly.
    # (Auto-reload and Ctrl-C aren't Exceptions, so they pass straight through.)
    try:
        traceback.print_exception(e)
        print("Unexpected error; restarting in 5 s.")
        if display is not None:
            display.show_text("Err ")
    except Exception:
        pass
    time.sleep(5)
    supervisor.reload()
