"""Turn the pin names from macros.json into board pins. Shared by boot.py
and code.py so both reject exactly the same configs.
"""

import board
import microcontroller

from macro_config import PIN_FIELDS, ConfigError


def board_pin(name, field):
    pin = getattr(board, name, None)
    if not isinstance(pin, microcontroller.Pin):
        raise ConfigError('hardware.%s: unknown pin "%s"' % (field, name))
    return pin


def resolve(hardware):
    """{field: Pin} for every pin field. Different names for the same pin
    (board aliases) are caught here; macro_config can only compare names."""
    pins = {}
    for field in PIN_FIELDS:
        pin = board_pin(hardware[field], field)
        for other in pins:
            if pins[other] is pin:
                raise ConfigError('hardware.%s: "%s" is the same pin as hardware.%s'
                                  % (field, hardware[field], other))
        pins[field] = pin
    return pins
