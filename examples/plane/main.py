"""An example app `plane` made with appengine.

- Author: Quan Lin
- License: MIT
"""

from math import ceil
import random
from machine import Pin, I2C, TouchPad
from framebuf import FrameBuffer, MONO_VLSB
import uasyncio as asyncio
from time import ticks_ms, ticks_diff
from ssd1306 import SSD1306_I2C
from microbmp import MicroBMP
from appengine import InputDevice, Screen, Sprite, Manager


IMAGES_DIR = "images/"


def framebuf_from_img(img_path):
    img = MicroBMP().load(img_path)
    fb = FrameBuffer(
        bytearray(img.DIB_w * ceil(img.DIB_h / 8)),
        img.DIB_w,
        img.DIB_h,
        MONO_VLSB,
    )

    for y in range(img.DIB_h):
        for x in range(img.DIB_w):
            fb.pixel(x, y, img[x, y])

    return fb


def mirror_framebuf_v(fb, w, h):
    new_fb = FrameBuffer(bytearray(w * ceil(h / 8)), w, h, MONO_VLSB)
    for y in range(h):
        for x in range(w):
            new_fb.pixel(x, y, fb.pixel(x, h - y - 1))
    return new_fb


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
    STATE_IDLE, STATE_UP, STATE_DOWN, STATE_DEAD = tuple(range(1, 5))

    WIDTH = 8
    HEIGHT = 8

    FB_IDLE = framebuf_from_img(IMAGES_DIR + "idle.bmp")
    FB_UP = framebuf_from_img(IMAGES_DIR + "up.bmp")
    FB_DOWN = mirror_framebuf_v(FB_UP, WIDTH, HEIGHT)
    FB_DEAD = framebuf_from_img(IMAGES_DIR + "dead.bmp")

    def __init__(self):
        super().__init__()

        self.x = self.WIDTH
        self.y = GameScreen.HEIGHT // 2
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [
            self.FB_IDLE,
            self.FB_UP,
            self.FB_DOWN,
            self.FB_DEAD,
        ]
        self.set_state(self.STATE_IDLE)
        self.name = "player"

    def set_state(self, state):
        self.state = state
        if self.state == self.STATE_IDLE:
            self.setup_animation(0, 1, 1)
        elif self.state == self.STATE_UP:
            self.setup_animation(1, 1, 1)
        elif self.state == self.STATE_DOWN:
            self.setup_animation(2, 1, 1)
        elif self.state == self.STATE_DEAD:
            self.setup_animation(3, 1, 1)

    def update(self):
        if self.state != self.STATE_DEAD:
            if GameKeyBoard.UP in self.manager.input_device.keys_on:
                self.set_state(self.STATE_UP)
                self.vy -= 0.5
            elif GameKeyBoard.DOWN in self.manager.input_device.keys_on:
                self.set_state(self.STATE_DOWN)
                self.vy += 0.5
            else:
                self.set_state(self.STATE_IDLE)
                self.vy /= 2

            if GameKeyBoard.LEFT in self.manager.input_device.keys_on:
                self.vx -= 0.5
            elif GameKeyBoard.RIGHT in self.manager.input_device.keys_on:
                self.vx += 0.5
            else:
                self.vx /= 2
        else:
            self.vy = 0
            self.vx = 0

        self.clamp_velocity(-3, 3, -3, 3)
        self.clamp_position(0, 0, GameScreen.HEIGHT, GameScreen.WIDTH)


class Missile(Sprite):
    WIDTH = 4
    HEIGHT = 2

    FB = FrameBuffer(
        bytearray(WIDTH * ceil(HEIGHT / 8)),
        WIDTH,
        HEIGHT,
        MONO_VLSB,
    )
    FB.fill(1)

    def __init__(self):
        super().__init__()

        self.x = GameScreen.WIDTH
        self.y = random.randrange(GameScreen.HEIGHT)
        self.w = self.WIDTH
        self.h = self.HEIGHT

        self.vx = random.uniform(-4, -1)
        self.imgs = [self.FB]

    def update(self):
        if self.x < -self.w:
            self.kill()


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
        time_text = "Time: {:.1f}s".format(self.manager.time_elapsed / 1000)
        self.FB.text(
            time_text,  # fps_objs_text
            0,
            0,
        )


class GameManager(Manager):
    def __init__(self):
        super().__init__()

        self.input_device = GameKeyBoard()
        self.screen = GameScreen()
        self.screen.manager = self

        self.player = Player()
        self.add_sprite(self.player)
        self.add_sprite(OverlayText())
        self.set_missile_spawn_interval(1)

        self.start_time = ticks_ms()
        self.time_elapsed = 0

    def set_missile_spawn_interval(self, spawn_interval):
        self.spawn_interval = spawn_interval
        self.spawn_timer = 0

    def spawn_missile_routine(self):
        if self.spawn_timer < self.spawn_interval:
            self.spawn_timer += 1
        else:
            self.add_sprite(Missile())
            self.set_missile_spawn_interval(random.randrange(5, 10))

    def check_collisions(self):
        for m in self.get_sprites(cls=Missile):
            collision = self.player.check_collision(m)
            if collision:
                m.kill()
                self.player.set_state(Player.STATE_DEAD)
                break

    def update(self):
        keyboard = self.input_device
        if (
            GameKeyBoard.ENTER not in keyboard.keys_on
            and GameKeyBoard.BACK in keyboard.keys_released
        ):
            print("`Back` is released. Exiting...")
            self.exit()
            return

        self.check_collisions()
        if self.player.state == Player.STATE_DEAD:
            self.exit()
            return

        self.spawn_missile_routine()

        self.time_elapsed = ticks_diff(ticks_ms(), self.start_time)


if __name__ == "__main__":
    asyncio.run(GameManager().arun())
