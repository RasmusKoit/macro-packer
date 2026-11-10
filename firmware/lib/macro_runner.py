"""Send a parsed profile's macros through adafruit_hid's Keyboard and Mouse."""

import time


def run_profile(keyboard, mouse, profile):
    """Send every macro. Returns (complete, started): complete is False if
    USB failed partway ("USB busy": host asleep or gone), started is True
    once any key press, click or scroll reached the host (the game may have
    reacted)."""
    delay = profile["delay_between_macros_ms"] / 1000
    complete, started = True, False
    mouse_used = False
    try:
        for i, macro in enumerate(profile["macros"]):
            if i and delay:
                time.sleep(delay)
            for step in macro["steps"]:
                action = step[0]
                if action == "wait":
                    time.sleep(step[1] / 1000)
                elif action == "release":
                    keyboard.release(*step[1])
                elif action in ("tap", "press"):
                    keyboard.press(*step[1])
                    started = True
                    if action == "tap":
                        time.sleep(step[2] / 1000)
                        keyboard.release(*step[1])
                else:
                    mouse_used = True  # before sending, so cleanup runs if it fails
                    if action == "scroll":
                        mouse.move(wheel=step[1])
                        started = True
                    elif action == "mouse_release":
                        mouse.release(step[1])
                    else:  # click or mouse_press
                        mouse.press(step[1])
                        started = True
                        if action == "click":
                            time.sleep(step[2] / 1000)
                            mouse.release(step[1])
    except OSError as e:
        print("USB error while sending:", e)
        complete = False
    finally:
        # A macro that pressed without releasing must never leave keys or
        # mouse buttons stuck. Caught here so it can't replace an auto-reload
        # or Ctrl-C in flight; code.py retries the release later.
        try:
            keyboard.release_all()
        except OSError:
            complete = False
        if mouse_used:
            try:
                mouse.release_all()
            except OSError:
                complete = False
    return complete, started
