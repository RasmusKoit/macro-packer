"""Runs once at power-up, before USB is set up (not on auto-reload).

When macros.json has "hide_drive": true, the CIRCUITPY drive is hidden so
the board shows up as a plain keyboard. Hold the macro button while
plugging in to get the drive back (GP2 always works too, in case
button_pin points at the wrong pin). The drive is only hidden when the
whole config is valid, pins included, so a typo can't lock you out.

print() output here goes to /boot_out.txt.
"""

import time

import digitalio
import storage

import macro_config
import pins


def any_button_held(button_pins):
    buttons = []
    try:
        for pin in button_pins:
            button = digitalio.DigitalInOut(pin)
            button.switch_to_input(pull=digitalio.Pull.UP)
            buttons.append(button)
        time.sleep(0.05)  # let the pull-ups settle
        return any(not b.value for b in buttons)
    finally:
        for button in buttons:
            button.deinit()


def should_hide_drive():
    try:
        from adafruit_hid.keycode import Keycode

        config = macro_config.load("/macros.json", macro_config.make_resolver(Keycode))
        if not config["hide_drive"]:
            return False
        board_pins = pins.resolve(config["hardware"])  # same checks as code.py
        escape = pins.board_pin(macro_config.DEFAULT_HARDWARE["button_pin"], "button_pin")
        buttons = [board_pins["button_pin"]]
        if escape is not buttons[0]:
            buttons.append(escape)
        if any_button_held(buttons):
            print("Macro button held: showing CIRCUITPY drive")
            return False
        return True
    except Exception as e:
        print("boot.py: showing CIRCUITPY drive because of an error:", e)
        return False


if should_hide_drive():
    storage.disable_usb_drive()
    print("CIRCUITPY drive hidden (hide_drive is true)")
