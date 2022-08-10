"""A demo app made with appengine.

- Author: Quan Lin
- License: MIT
"""

from math import ceil
import random
from machine import Pin, I2C, TouchPad
from framebuf import FrameBuffer, MONO_VLSB
from ssd1306 import SSD1306_I2C
from microbmp import MicroBMP
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

    def print_screen(self, img):
        for y in range(img.DIB_h):
            for x in range(img.DIB_w):
                img[x, y] = self.display.pixel(x, y)

    def update(self):
        self.display.show()

        keyboard = self.manager.input_device
        if (
            GameKeyBoard.ENTER in keyboard.keys_on
            and GameKeyBoard.BACK in keyboard.keys_released
        ):
            print("Printing screen...")
            img_screen = MicroBMP(128, 64, 1)
            self.print_screen(img_screen)
            img_screen.save("screenshot.bmp")
            print("Done.")


class Player(Sprite):
    WIDTH = 8
    HEIGHT = 8

    FB0 = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB0.fill_rect(0, 0, WIDTH, HEIGHT, 1)

    FB1 = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB1.fill_rect(WIDTH // 4, HEIGHT // 4, WIDTH // 2, HEIGHT // 2, 1)

    def __init__(self):
        super().__init__()

        self.x = GameScreen.WIDTH // 2
        self.y = GameScreen.HEIGHT // 2
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [
            self.FB0,
            self.FB1,
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


class Bean(Sprite):
    WIDTH = 4
    HEIGHT = 4

    FB0 = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB0.fill_rect(0, 1, WIDTH, 2, 1)
    FB0.fill_rect(1, 0, 2, HEIGHT, 1)

    def __init__(self):
        super().__init__()

        self.x = random.randrange(GameScreen.WIDTH - self.WIDTH)
        self.y = random.randrange(OverlayText.HEIGHT, GameScreen.HEIGHT - self.HEIGHT)
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [self.FB0]
        self.kill_after_n_frames(100)


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
        self.screen.manager = self

        self.add_sprite(Player())
        self.add_sprite(OverlayText())

    def update(self):
        keyboard = self.input_device
        if (
            GameKeyBoard.ENTER not in keyboard.keys_on
            and GameKeyBoard.BACK in keyboard.keys_released
        ):
            print("`Back` is released. Exiting...")
            self.exit()
            return

        player = self.get_sprites(name="player")[0]
        beans = self.get_sprites(cls=Bean)

        for bean in beans:
            if player.check_collision(bean):
                bean.kill()

        if len(beans) < 5:
            self.add_sprite(Bean())


if __name__ == "__main__":
    GameManager().run()
