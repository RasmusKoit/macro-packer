# macro-packer

A one-button macro pad built on a Waveshare **RP2040-Zero** running CircuitPython.

Press the big button and the board sends a list of macros (e.g. your skill rotation) as a USB keyboard and mouse: key presses, mouse clicks and scrolling. A TM1637 4-digit display then counts down your cooldown in `mm:ss`. The button is ignored until the display is back at `00:00`, which tells you everything is ready again.

All configuration lives in `macros.json` on the board's `CIRCUITPY` USB drive. Edit it and save, and the board reloads with the new settings.

> **Use responsibly.** Blizzard's terms for Diablo IV forbid macros that send several actions from one input. Online use is at your own risk. It's safest in single-player or in games that allow macros.

## Hardware

| Part | RP2040-Zero pin |
|---|---|
| Big button (macro) | `GP2` to button to `GND` (internal pull-up, no resistor needed) |
| Profile button | `GP3` to button to `GND` |
| TM1637 `CLK` | `GP4` |
| TM1637 `DIO` | `GP5` |
| TM1637 `VCC` / `GND` | `3V3` / `GND` |

You can change the pins in the `hardware` section of `macros.json`.

## Setup

You need Python 3 on the PC for the tools below. On Windows, if `python` isn't found, try `py` instead.

1. **Flash CircuitPython.** Hold **BOOT** while plugging the board in, and an `RPI-RP2` drive appears. Download the latest stable UF2 for *Waveshare RP2040-Zero* from circuitpython.org and copy it onto that drive. The board reboots and shows up as `CIRCUITPY`.
2. **Install the HID library.**
   ```
   pip install circup
   circup install adafruit_hid
   ```
   Or copy the `adafruit_hid` folder from the Adafruit CircuitPython bundle into `CIRCUITPY/lib/`. If Windows says `circup` isn't recognised, Python's `Scripts` folder isn't on your PATH. Rerun the Python installer with "Add python.exe to PATH" ticked, or copy the folder from the bundle instead.
3. **Deploy the firmware.** Run:
   ```
   python tools/deploy.py
   ```
   This finds the CIRCUITPY drive, downloads the `mpy-cross` compiler that matches the board's CircuitPython version (once, into `tools/.bin/`), compiles `firmware/lib/*.py` to faster-loading `.mpy` files, and copies over whatever changed. It never overwrites the board's `macros.json` unless you add `--config`, and even then it first saves the board's copy in `backups/`. Run the same command again after any code change. If it finds no board or several, name the drive, e.g. `--drive E`.
4. The display shows the starting profile's label (its `display_name`, or `P001`) for a second, then `00:00`, and the button is ready.

## How it works

1. **Ready:** the display shows `00:00` with a solid colon.
2. **Press:** every macro in the active profile is sent in order, and the cooldown starts at the moment of the press.
3. **Cooldown:** the display counts down `mm:ss` with a blinking colon. Presses during this time are ignored.
4. At `00:00` it's ready again.

**If the PC isn't listening** (asleep, rebooting, or switched away on a KVM), a press shows `USb` for two seconds. If nothing got through, the cooldown doesn't start, so you can press again once the PC is back. If the connection dropped partway through, the cooldown starts anyway, because some skills did fire.

**Profile button:** each press switches to the next profile in number order when you let go of the button, and wraps around after the highest number. For a second, the display shows the profile's `display_name`, or its `number` with leading zeros (e.g. `P002`) if it has none. The starting profile's label is also shown briefly at power-up. Each profile has its own cooldown timer. Switching shows that profile's countdown, and the other timers keep running in the background. The macro button is only locked while the current profile is cooling down. After a reboot or a saved config, the board goes back to `active_profile`, and all timers reset to `00:00`. So don't save the config while skills are still on cooldown in the game.

## macros.json reference

```json
{
  "version": 1,
  "hardware": { "button_pin": "GP2", "profile_button_pin": "GP3", "display_clk": "GP4", "display_dio": "GP5", "display_brightness": 4 },
  "active_profile": "diablo",
  "profiles": [
    {
      "number": 1,
      "name": "diablo",
      "cooldown_ms": 30000,
      "delay_between_macros_ms": 60,
      "macros": [
        { "name": "Skill 1", "steps": [ { "tap": "1" } ] },
        { "name": "Shift skill", "steps": [ { "press": "SHIFT" }, { "tap": "E", "hold_ms": 50 }, { "release": "SHIFT" } ] },
        { "name": "Combo", "steps": [ { "tap": ["CTRL", "Q"] } ] }
      ]
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `version` | yes | Always `1`. |
| `hide_drive` | no | `true` hides the CIRCUITPY drive so the board shows up as a plain keyboard and mouse. Default `false`. See [Hiding the drive](#hiding-the-drive). |
| `hardware` | no | Board pin names such as `GP7` (each pin used once) and `display_brightness` from 0 to 7. Defaults are shown above. |
| `active_profile` | no | The name of the profile used at startup. Defaults to the profile with the lowest `number`. The profile button cycles through the others. |
| `profiles[].number` | yes | A unique number from 0 to 999. It's shown as `P001` when switching, and the profile button cycles in number order. |
| `profiles[].name` | yes | A unique name. |
| `profiles[].display_name` | no | Up to 4 characters shown instead of `P001` when switching, e.g. `"nEcr"`. See [Display names](#display-names). |
| `profiles[].cooldown_ms` | yes | Countdown length in milliseconds, at most `5999000` (99:59). |
| `profiles[].delay_between_macros_ms` | no | Pause between macros in milliseconds. Default `50`, max 60000. |
| `profiles[].macros[]` | yes | Macros sent in order on each press. Each has a `name` and `steps`. |

### Steps

Each step is an object with exactly one action:

| Step | Effect |
|---|---|
| `{ "tap": "1" }` | Press and release a key. Add `"hold_ms": 50` to hold it longer (default 30 ms). |
| `{ "tap": ["CTRL", "Q"] }` | Tap several keys at once, like a shortcut. |
| `{ "press": "SHIFT" }` | Press and keep holding. Works with a list too. |
| `{ "release": "SHIFT" }` | Release held keys. Works with a list too. |
| `{ "wait": 40 }` | Pause in milliseconds (max 60000). |
| `{ "click": "LEFT" }` | Click a mouse button. Add `"hold_ms": 50` to hold it longer (default 30 ms). A list like `["LEFT", "RIGHT"]` clicks both at once. |
| `{ "mouse_press": "RIGHT" }` | Press a mouse button and keep holding (e.g. for a channelled skill). Works with a list too. |
| `{ "mouse_release": "RIGHT" }` | Release held mouse buttons. Works with a list too. |
| `{ "scroll": 3 }` | Turn the scroll wheel by that many notches: positive scrolls up, negative down (-127 to 127, not 0). |

All keys and mouse buttons are released automatically after each button press, even if a macro forgets to. Until then, keys from `press` stay down through later steps and later macros. A `tap` of a key that's being held releases it too.

A USB keyboard can hold at most **6 keys at once, not counting modifiers** (`SHIFT`, `CTRL`, `ALT`, `WIN`). A config that would ever hold more, for example by pressing keys and never releasing them, is rejected with `Err`, and the console names the step.

### Mouse

Mouse button names are `LEFT`, `RIGHT`, `MIDDLE`, `BACK` and `FORWARD` (the two side buttons), case-insensitive. In a `click` step, `LEFT` means the left mouse button; in a `tap` step it means the left arrow key.

Clicks land wherever the mouse cursor already is. The board can't move the cursor to a spot on the screen, so aim with your real mouse and let the macro click. Keys and clicks mix freely, e.g. a shift-click:

```json
{ "name": "Force attack", "steps": [ { "press": "SHIFT" }, { "click": "LEFT" }, { "release": "SHIFT" } ] }
```

Mouse buttons don't count towards the 6-key limit.

### Key names

Key names follow adafruit_hid `Keycode` names and are case-insensitive: `A` to `Z`, `F1` to `F12`, `ENTER`, `TAB`, `BACKSPACE`, `LEFT_SHIFT`, `KEYPAD_ONE` and so on. Shortcuts that also work: `0` to `9`, `SHIFT`, `CTRL`, `ALT`, `WIN`, `SPACE`, `ESC`, `DEL`, `INS`, `PGUP`, `PGDN`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `` ` ``, `-`, `=`.

These are physical key positions, so your PC's keyboard layout doesn't affect them.

## Display names

A 7-segment display can only draw some letters, and case matters, because many letters exist in only one form:

```
A b C c d E F G H h I J L n O o P q r S t U u y   digits   -   _   space
```

`K M V W X Z` can't be drawn at all. Examples: Barbarian `bArb`, Necromancer `nEcr`, Sorcerer `SorC`, Rogue `roGu`, Druid `druI`.

A name with a letter that can't be drawn, or with more than 4 characters, is a config error. The display shows `Err`, and the serial console names the bad character and lists the ones you can use.

## Hiding the drive

Set `"hide_drive": true` in `macros.json` and replug the board. From then on it appears only as a keyboard and mouse; no drive and no AutoPlay window.

- **Edit the config again:** hold the macro button while plugging the board in, and the drive appears. GP2 always works for this too, even if `button_pin` points somewhere else. Holding the button for this doesn't fire a macro.
- **Turn hiding off:** hold the macro button while plugging in, set `"hide_drive": false`, save, and replug.
- **When changes apply:** the flag is read by `boot.py`, which only runs at power-up, so changes take effect on the next replug, not on save.
- **If `macros.json` has any error or is missing:** the drive is always shown, so a typo can't lock you out. `boot.py` checks the whole config including the pins, not just this flag, and writes what it decided to `boot_out.txt`.
- **Deploying:** `tools/deploy.py` needs the drive, so hold the button while plugging in first.
- **Last resort:** CircuitPython's safe mode skips `boot.py`. Tap reset while the status LED blinks right after power-up.

## Troubleshooting

- **Display shows `Err`:** `macros.json` has a problem. Open the serial console (Mu, PuTTY, or `tio` on the board's COM port) to see the error, e.g. `profiles[0].macros[2].steps[1].tap: unknown key "SHFT"`. Fix it and save. For JSON syntax mistakes, CircuitPython can't report a position, so the board guesses the most common ones, e.g. `line 12: comments aren't allowed in JSON` or `line 4: use double quotes (") instead of single quotes`. `Err` appears on your configured display pins. If the `hardware` section itself is broken, it appears on the default pins GP4/GP5 instead, so check the console if your display stays blank.
- **`Err` while running, then a restart:** an unexpected error happened. The board restarts by itself after 5 seconds, and the console shows the details.
- **Display shows `USb`:** the PC didn't accept the keys (see [How it works](#how-it-works)). At startup, it means the board is waiting for a PC, e.g. when it's plugged into a charger.
- **Changes don't apply on Windows:** make sure the editor actually saved the file, or eject the drive. Don't edit the config mid-game, because every save reloads the board.
- **Blank display:** check that CLK/DIO aren't swapped and that the module is powered from 3V3. If the console shows `ImportError: no module named 'adafruit_hid'`, run `circup install adafruit_hid`.
- **`Incompatible .mpy file` after upgrading CircuitPython:** run `python tools/deploy.py` (it downloads the matching compiler) and `circup update`.
- **deploy can't find the board:** if `hide_drive` is on, hold the macro button while plugging in. If the board was flashed with a different CircuitPython UF2 (e.g. the Raspberry Pi Pico one), deploy lists it, and you can pick it with `--drive`. If the compiler download fails (offline, proxy), download `mpy-cross` for your CircuitPython version from the Adafruit S3 bucket and pass `--mpy-cross PATH`.

## Development

Edit the sources in `firmware/`, then run `python tools/deploy.py` to put them on the board. Changes to `boot.py` only take effect after a replug, because it only runs at power-up; deploy reminds you. On the board, `lib/` holds only compiled `.mpy` files. Don't copy `.py` versions of the modules there by hand; if both exist, the board loads the `.py`.

The compiled modules are committed in `build/lib/`, built for the CircuitPython version in `build/CIRCUITPY_VERSION`, so you can copy them to a board without installing anything. After changing anything in `firmware/lib/`, refresh them before committing, with or without the board plugged in:

```
python tools/deploy.py --build-only
```

Add `--cp-version 10.4.0` (for example) to build for a different CircuitPython release.

The config parser, display text and time formatting are plain Python and are tested on the PC:

```
pip install pytest
python -m pytest tests
```
