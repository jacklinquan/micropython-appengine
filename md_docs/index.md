# micropython-appengine

A MicroPython app engine.

This module works under MicroPython and it is tested with MicroPython V1.19.1.

## Installation

```python
>>> import upip
>>> upip.install('micropython-appengine')
```

Alternatively just copy `appengine.py` to the MicroPython device.

## Usage

- Subclass `InputDevice` for the input device.
- Subclass `Screen` for the screen.
- Subclass `Sprite` for all the sprites needed in the app.
- Subclass `Manager` for the app main control.
