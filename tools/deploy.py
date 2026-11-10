"""Compile the firmware modules to .mpy and copy everything to CIRCUITPY.

    python tools/deploy.py              # auto-detect the board
    python tools/deploy.py --drive E    # or name the drive
    python tools/deploy.py --config     # also overwrite macros.json on the board

mpy-cross must match the board's CircuitPython version, so it is read from
boot_out.txt and the matching official build is downloaded once into
tools/.bin/. Files that are already identical on the board are skipped.
macros.json on the board is left alone unless --config is given, and even
then the board's copy is backed up into backups/ first.
"""

import argparse
import os
import re
import shutil
import string
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE = os.path.join(ROOT, "firmware")
BUILD = os.path.join(ROOT, "build")
BIN = os.path.join(ROOT, "tools", ".bin")
BACKUPS = os.path.join(ROOT, "backups")
BOARD_ID = "waveshare_rp2040_zero"
MPY_CROSS_URL = ("https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross/"
                 "windows/mpy-cross-windows-%s.static.exe")
DRIVE_REMOVABLE = 2  # GetDriveTypeW
SEM_FAILCRITICALERRORS = 0x0001


def board_info(drive):
    """(version, board_id) from boot_out.txt, or None if it isn't a CircuitPython drive."""
    try:
        with open(os.path.join(drive, "boot_out.txt"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    version = re.search(r"CircuitPython (\S+)", text)
    board = re.search(r"Board ID:(\S+)", text)
    if not version:
        return None
    return version.group(1), board.group(1) if board else None


def removable_drives():
    # Only removable drives: probing an offline network drive can stall for ages.
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.SetErrorMode(SEM_FAILCRITICALERRORS)  # no "insert a disk" popups
    mask = kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        root = letter + ":\\"
        if mask & (1 << i) and kernel32.GetDriveTypeW(root) == DRIVE_REMOVABLE:
            yield root


def find_drive():
    found = [(d, board_info(d)) for d in removable_drives()]
    found = [(d, info) for d, info in found if info]
    matches = [d for d, info in found if info[1] == BOARD_ID]
    if not matches:
        others = ", ".join("%s (%s)" % (d, info[1] or "unknown board") for d, info in found)
        if others:
            sys.exit("No %s found, but these CircuitPython drives are: %s. If one of them is "
                     "your board (e.g. flashed with a different UF2), pick it with --drive."
                     % (BOARD_ID, others))
        sys.exit("No CIRCUITPY drive found. Is the board plugged in? If hide_drive is on, "
                 "hold the macro button while plugging it in.")
    if len(matches) > 1:
        sys.exit("Several matching boards found (%s); pick one with --drive." % ", ".join(matches))
    return matches[0]


def normalize_drive(arg):
    match = re.match(r"^([A-Za-z]):?[\\/]?$", arg)
    return match.group(1).upper() + ":\\" if match else arg


def get_mpy_cross(version):
    if sys.platform != "win32":
        sys.exit("Automatic mpy-cross download is Windows-only; pass --mpy-cross PATH.")
    # Local builds report e.g. "10.3.1-dirty"; any build of the same release
    # produces compatible .mpy files, so fall back to the plain x.y.z.
    candidates = [version]
    plain = re.match(r"\d+\.\d+\.\d+", version)
    if plain and plain.group(0) != version:
        candidates.append(plain.group(0))

    paths = {v: os.path.join(BIN, "mpy-cross-%s.exe" % v) for v in candidates}
    for v in candidates:
        if os.path.exists(paths[v]):
            return paths[v]
    os.makedirs(BIN, exist_ok=True)
    for v in candidates:
        url = MPY_CROSS_URL % v
        print("Downloading", url)
        try:
            urllib.request.urlretrieve(url, paths[v] + ".part")
        except OSError as e:
            print("  failed:", e)
            continue
        os.replace(paths[v] + ".part", paths[v])
        return paths[v]
    sys.exit("Could not download mpy-cross for CircuitPython %s. Download one for the same "
             "CircuitPython version and pass --mpy-cross PATH." % version)


def compile_modules(mpy_cross):
    src_dir = os.path.join(FIRMWARE, "lib")
    out_dir = os.path.join(BUILD, "lib")
    os.makedirs(out_dir, exist_ok=True)
    built = []
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".py"):
            continue
        out = os.path.join(out_dir, name[:-3] + ".mpy")
        # -s: tracebacks on the board show "macro_config.py", not the PC path.
        cmd = [mpy_cross, "-s", name, "-o", out, os.path.join(src_dir, name)]
        try:
            subprocess.run(cmd, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            sys.exit("Compiling %s failed (%s); nothing was copied to the board." % (name, e))
        built.append(out)
    return built


def same_file(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def install(src, drive, rel):
    """Copy src to drive/rel unless identical. Returns True if written."""
    dst = os.path.join(drive, rel)
    if os.path.exists(dst) and same_file(src, dst):
        return False
    # Write to a temp name first so a failed copy never leaves a truncated file.
    tmp = dst + ".tmp"
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:  # also on Ctrl-C
        if os.path.exists(tmp):
            os.remove(tmp)
    print("  " + rel.replace("\\", "/"))
    return True


def check_board(drive, modules):
    """Print problems that stop the firmware from working; True if any."""
    problems = False
    for name in modules:
        for ext in (".py", ".mpy"):
            if os.path.exists(os.path.join(drive, name + ext)):
                print("PROBLEM: %s%s in the drive's root shadows lib/%s.mpy; delete it."
                      % (name, ext, name))
                problems = True
    if not os.path.isdir(os.path.join(drive, "lib", "adafruit_hid")):
        print("PROBLEM: lib/adafruit_hid is missing; run: circup install adafruit_hid")
        problems = True
    return problems


def backup_board_config(board_config):
    os.makedirs(BACKUPS, exist_ok=True)
    backup = os.path.join(BACKUPS, time.strftime("macros-%Y%m%d-%H%M%S.json"))
    try:
        shutil.copyfile(board_config, backup)
    except OSError as e:
        sys.exit("Couldn't back up the board's macros.json to %s (%s); nothing was "
                 "overwritten." % (backup, e))
    print("  board's macros.json backed up to", backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--drive", help="CIRCUITPY drive, e.g. E or E:")
    parser.add_argument("--config", action="store_true",
                        help="overwrite macros.json on the board (its copy is backed up to backups/)")
    parser.add_argument("--mpy-cross", help="path to an mpy-cross matching the board")
    args = parser.parse_args()

    if args.drive:
        drive = normalize_drive(args.drive)
    elif sys.platform == "win32":
        drive = find_drive()
    else:
        sys.exit("Pass --drive with the CIRCUITPY mount point.")
    info = board_info(drive)
    if not info:
        sys.exit("%s has no readable boot_out.txt; is it the CIRCUITPY drive?" % drive)
    version, board = info
    print("CircuitPython %s on %s (%s)" % (version, drive, board or "unknown board"))
    if board != BOARD_ID:
        print("WARNING: expected a %s; deploying anyway because --drive was given." % BOARD_ID)

    # Everything is compiled before the board is touched.
    mpy_cross = args.mpy_cross or get_mpy_cross(version)
    built = compile_modules(mpy_cross)
    modules = [os.path.basename(p)[:-4] for p in built]

    try:
        os.makedirs(os.path.join(drive, "lib"), exist_ok=True)
        changed = False
        for mpy, name in zip(built, modules):
            changed |= install(mpy, drive, os.path.join("lib", name + ".mpy"))
            # A leftover .py would be imported instead of the .mpy.
            stale = os.path.join(drive, "lib", name + ".py")
            if os.path.exists(stale):
                os.remove(stale)
                print("  removed lib/%s.py" % name)
                changed = True
        boot_changed = install(os.path.join(FIRMWARE, "boot.py"), drive, "boot.py")
        changed |= boot_changed

        local_config = os.path.join(FIRMWARE, "macros.json")
        board_config = os.path.join(drive, "macros.json")
        if not os.path.exists(board_config):
            changed |= install(local_config, drive, "macros.json")
        elif not same_file(local_config, board_config):
            if args.config:
                backup_board_config(board_config)
                changed |= install(local_config, drive, "macros.json")
            else:
                print("  macros.json skipped: the board's copy differs (use --config to overwrite)")

        # Last: CircuitPython reloads ~0.75 s after the final write, so writing
        # code.py at the end makes it very likely that reload sees every file.
        changed |= install(os.path.join(FIRMWARE, "code.py"), drive, "code.py")
    except OSError as e:
        sys.exit("Copying to the board failed: %s\nThe drive may be full or was unplugged. "
                 "Fix that and run deploy again." % e)

    problems = check_board(drive, modules)
    print("Done; the board reloads by itself." if changed else "Board already up to date.")
    if boot_changed:
        print("boot.py changed: it only runs at power-up, so replug the board to apply it.")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
