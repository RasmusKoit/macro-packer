"""Minimal TM1637 4-digit 7-segment driver, bit-banged with digitalio.

The TM1637 speaks an I2C-like 2-wire protocol (CLK/DIO) but without
addresses and LSB first, so busio.I2C can't drive it. CircuitPython's
digitalio is slow enough that no extra delays are needed.
"""

import digitalio

from segments import COLON, DIGITS, encode

_CMD_DATA_AUTO_INCREMENT = 0x40
_CMD_ADDRESS_0 = 0xC0
_CMD_DISPLAY_ON = 0x88


class TM1637:
    def __init__(self, clk, dio, brightness=4):
        self._clk = digitalio.DigitalInOut(clk)
        self._clk.switch_to_output(value=True)
        self._dio = digitalio.DigitalInOut(dio)
        self._dio.switch_to_output(value=True)
        self._brightness = 0
        self.brightness = brightness
        self.show_segments((0, 0, 0, 0))

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        if not 0 <= value <= 7:
            raise ValueError("brightness must be 0-7")
        self._brightness = value
        self._command(_CMD_DISPLAY_ON | value)

    def show_segments(self, segments):
        self._command(_CMD_DATA_AUTO_INCREMENT)
        self._start()
        self._write_byte(_CMD_ADDRESS_0)
        for seg in segments:
            self._write_byte(seg)
        self._stop()
        self._command(_CMD_DISPLAY_ON | self._brightness)

    def show_digits(self, digits, colon=False):
        segments = [DIGITS[d] for d in digits]
        if colon:
            segments[1] |= COLON
        self.show_segments(segments)

    def show_text(self, text):
        self.show_segments(encode(text))

    def deinit(self):
        self._clk.deinit()
        self._dio.deinit()

    def _command(self, cmd):
        self._start()
        self._write_byte(cmd)
        self._stop()

    def _start(self):
        # DIO falls while CLK is high
        self._dio.value = False
        self._clk.value = False

    def _stop(self):
        # DIO rises while CLK is high
        self._clk.value = False
        self._dio.value = False
        self._clk.value = True
        self._dio.value = True

    def _write_byte(self, b):
        for _ in range(8):
            self._dio.value = bool(b & 1)
            self._clk.value = True
            self._clk.value = False
            b >>= 1
        # Ninth clock: the chip pulls DIO low to ACK, so let go of the line.
        self._dio.switch_to_input()
        self._clk.value = True
        self._clk.value = False
        self._dio.switch_to_output(value=False)
