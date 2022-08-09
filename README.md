# micropython-appengine

[![PayPal Donate][paypal_img]][paypal_link]
[![PyPI version][pypi_img]][pypi_link]
[![Downloads][downloads_img]][downloads_link]

  [paypal_img]: https://github.com/jacklinquan/images/blob/master/paypal_donate_badge.svg
  [paypal_link]: https://www.paypal.me/jacklinquan
  [pypi_img]: https://badge.fury.io/py/micropython-appengine.svg
  [pypi_link]: https://badge.fury.io/py/micropython-appengine
  [downloads_img]: https://pepy.tech/badge/micropython-appengine
  [downloads_link]: https://pepy.tech/project/micropython-appengine

[Documentation](https://jacklinquan.github.io/micropython-appengine) is under construction.

A MicroPython app engine.

This module works under MicroPython and it is tested with MicroPython V1.19.1.

## Installation

```python
>>> import upip
>>> upip.install('micropython-appengine')
```

Alternatively just copy `appengine.py` to the MicroPython device.

## Simple Demo

### Hardware

- ESP32 DevKitC
- SSD1306 128x64 OLED with I2C interface
    - `SCL` on pin 16
    - `SDA` on pin 17
- Touchpads
    - `BACK` on pin 32
    - `UP` on pin 15
    - `ENTER` on pin 4
    - `LEFT` on pin 27
    - `DOWN` on pin 12
    - `RIGHT` on pin 2

### Firmware

- MicroPython V1.19.1.

### Software

```python
"""An appengine simple demo.

- Author: Quan Lin
- License: MIT
"""

from math import ceil
from machine import Pin, I2C, TouchPad
from framebuf import FrameBuffer, MONO_VLSB
from ssd1306 import SSD1306_I2C
from appengine import InputDevice, Screen, Sprite, Manager


class GameKeyBoard(InputDevice):
    NUM_OF_KEYS = 6
    BACK, UP, ENTER, LEFT, DOWN, RIGHT = tuple(range(NUM_OF_KEYS))

    PIN_BACK = 32
    PIN_UP = 15
    PIN_ENTER = 4
    PIN_LEFT = 27
    PIN_DOWN = 12
    PIN_RIGHT = 2

    THRE_BACK = 690
    THRE_UP = 620
    THRE_ENTER = 570
    THRE_LEFT = 570
    THRE_DOWN = 590
    THRE_RIGHT = 520

    def __init__(self):
        super().__init__()

        self.keys = [
            TouchPad(Pin(self.PIN_BACK)),
            TouchPad(Pin(self.PIN_UP)),
            TouchPad(Pin(self.PIN_ENTER)),
            TouchPad(Pin(self.PIN_LEFT)),
            TouchPad(Pin(self.PIN_DOWN)),
            TouchPad(Pin(self.PIN_RIGHT)),
        ]
        self._thresholds = [
            self.THRE_BACK,
            self.THRE_UP,
            self.THRE_ENTER,
            self.THRE_LEFT,
            self.THRE_DOWN,
            self.THRE_RIGHT,
        ]
        self.keys_all = set(range(self.NUM_OF_KEYS))

        self.keys_on = set()
        self.keys_off = self.keys_all - self.keys_on
        self.keys_pressed = set()
        self.keys_released = set()

    def update(self):
        old_keys_on = self.keys_on
        old_keys_off = self.keys_off

        self.keys_on = set()
        for i in range(len(self.keys)):
            if self.keys[i].read() < self._thresholds[i]:
                self.keys_on.add(i)
        self.keys_off = self.keys_all - self.keys_on
        self.keys_pressed = self.keys_on - old_keys_on
        self.keys_released = self.keys_off - old_keys_off


class GameScreen(Screen):
    WIDTH = 128
    HEIGHT = 64

    I2C_SCL = 16
    I2C_SDA = 17

    def __init__(self):
        super().__init__()

        i2c = I2C(1, scl=Pin(self.I2C_SCL), sda=Pin(self.I2C_SDA))
        self.display = SSD1306_I2C(self.WIDTH, self.HEIGHT, i2c)
        self.w = self.WIDTH
        self.h = self.HEIGHT

    def update(self):
        self.display.show()


class Player(Sprite):
    WIDTH = 8
    HEIGHT = 8

    FB_ALIVE0 = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB_ALIVE0.fill_rect(0, 0, WIDTH, HEIGHT, 1)

    FB_ALIVE1 = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB_ALIVE1.fill_rect(WIDTH // 4, HEIGHT // 4, WIDTH // 2, HEIGHT // 2, 1)

    def __init__(self):
        super().__init__()

        self.x = GameScreen.WIDTH // 2
        self.y = GameScreen.HEIGHT // 2
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [
            self.FB_ALIVE0,
            self.FB_ALIVE1,
        ]
        self.setup_animation(0, 2, 5)
        self.name = "player"

    def update(self):
        keyboard = self.manager.input_device

        if GameKeyBoard.UP in keyboard.keys_on:
            self.vy = -3
        elif GameKeyBoard.DOWN in keyboard.keys_on:
            self.vy = 3
        else:
            self.vy = 0

        if GameKeyBoard.LEFT in keyboard.keys_on:
            self.vx = -3
        elif GameKeyBoard.RIGHT in keyboard.keys_on:
            self.vx = 3
        else:
            self.vx = 0

        self.clamp_position(0, 0, GameScreen.HEIGHT, GameScreen.WIDTH)

        if GameKeyBoard.ENTER in keyboard.keys_pressed:
            print("`Enter` is pressed.")


class OverlayText(Sprite):
    WIDTH = 128
    HEIGHT = 8

    FB = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )

    def __init__(self):
        super().__init__()

        self.x = 0
        self.y = 0
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [self.FB]
        self.colourkey = 0
        self.is_overlay = True
        self.set_layer(255)

    def update(self):
        self.FB.fill(0)

        fps_objs_text = "FPS:{:3d} OBJs:{:3d}".format(
            int(self.manager.actual_fps + 0.5),
            len(self.manager.get_sprites()),
        )
        self.FB.text(fps_objs_text, 0, 0)


class GameManager(Manager):
    def __init__(self):
        super().__init__()

        self.input_device = GameKeyBoard()
        self.screen = GameScreen()

        self.add_sprite(Player())
        self.add_sprite(OverlayText())

    def update(self):
        if GameKeyBoard.BACK in self.input_device.keys_released:
            print("`Back` is released. Exiting...")
            self.exit()
            return


if __name__ == "__main__":
    GameManager().run()
```
