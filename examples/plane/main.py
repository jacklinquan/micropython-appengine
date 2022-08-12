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


class Overlay(Sprite):
    H_LEFT, H_CENTER, H_RIGHT = tuple(range(1, 4))
    V_TOP, V_CENTER, V_BOTTOM = tuple(range(1, 4))

    def __init__(self):
        super().__init__()

        self.is_overlay = True
        self.set_layer(255)

        self._lines = []
        self._has_outline = False
        self._invert = False

    def set_text(
        self,
        text=None,
        anchor_h=None,
        anchor_v=None,
        has_outline=None,
        invert=None,
    ):
        if text is not None:
            self._lines = text.splitlines()

        if has_outline is not None:
            self._has_outline = has_outline

        if invert is not None:
            self._invert = invert

        extra_len = 1 if self._has_outline else 0
        self.w = (
            (max(len(line) for line in self._lines) + extra_len) * 8
            if self._lines
            else 0
        )
        self.h = (len(self._lines) + extra_len) * 8

        if anchor_h == self.H_LEFT:
            self.x = 0
        elif anchor_h == self.H_CENTER:
            self.x = (GameScreen.WIDTH - self.w) / 2
        elif anchor_h == self.H_CENTER:
            self.x = GameScreen.WIDTH - self.w

        if anchor_v == self.V_TOP:
            self.y = 0
        elif anchor_v == self.V_CENTER:
            self.y = (GameScreen.HEIGHT - self.h) / 2
        elif anchor_v == self.V_BOTTOM:
            self.y = GameScreen.HEIGHT - self.h

        fb = FrameBuffer(
            bytearray(self.w * ceil(self.h / 8)),
            self.w,
            self.h,
            MONO_VLSB,
        )

        fb.fill(1 if self._invert else 0)
        if self._has_outline:
            fb.rect(2, 2, self.w - 4, self.h - 4, 0 if self._invert else 1)
        margin = 4 if self._has_outline else 0
        for i, line in enumerate(self._lines):
            fb.text(line, margin, i * 8 + margin, 0 if self._invert else 1)

        self.imgs = [fb]


class PopUp(Overlay):
    WIDTH = 15

    def __init__(self, name="", text="", buttons=None):
        super().__init__()

        self.name = name
        self._has_outline = True
        self.buttons = buttons or ["OK"]
        self.result = None

        if len(self.buttons) == 1:
            btn_text = " " * (self.WIDTH - len(self.buttons[0])) + self.buttons[0]
        else:
            btn_text = (
                self.buttons[0]
                + " " * (self.WIDTH - len(self.buttons[0]) - len(self.buttons[1]))
                + self.buttons[1]
            )

        self.set_text(
            text + "\n" + btn_text,
            Overlay.H_CENTER,
            Overlay.V_CENTER,
            True,
            True,
        )

    def update(self):
        keyboard = self.manager.input_device
        if len(self.buttons) == 1:
            if GameKeyBoard.ENTER in keyboard.keys_released:
                self.result = self.buttons[0]
        else:
            if (
                GameKeyBoard.ENTER not in keyboard.keys_on
                and GameKeyBoard.BACK in keyboard.keys_released
            ):
                self.result = self.buttons[0]
            if GameKeyBoard.ENTER in keyboard.keys_released:
                self.result = self.buttons[1]


class TopLabel(Overlay):
    def __init__(self):
        super().__init__()

        self.colourkey = 0

    def update(self):
        fps_objs_text = "FPS:{:3d} OBJs:{:3d}".format(
            int(self.manager.actual_fps + 0.5),
            len(self.manager.get_sprites()),
        )
        time_text = "Time: {:.1f}s".format(self.manager.time_elapsed / 1000)
        # self.set_text(fps_objs_text)
        self.set_text(time_text)


class GameManager(Manager):
    def __init__(self):
        super().__init__()

        self.input_device = GameKeyBoard()
        self.screen = GameScreen()
        self.screen.manager = self

        self._popup_result = {}

        self.init_level()

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
            if self.player.check_collision(m):
                m.kill()
                self.player.set_state(Player.STATE_DEAD)
                break

        if self.player.state == Player.STATE_DEAD:
            for m in self.get_sprites(cls=Missile):
                m.vx = 0

    def get_popup_result(self, k):
        v = self._popup_result.get(k)
        self._popup_result[k] = None
        return v

    def set_popup_result(self, k, v):
        self._popup_result[k] = v

    def popup(self, name="", text="", buttons=None):
        self.add_sprite(PopUp(name, text, buttons))

    def handle_popup(self):
        popups = self.get_sprites(PopUp)
        if popups:
            current_popup = popups[-1]
            if current_popup.result is not None:
                self.set_popup_result(current_popup.name, current_popup.result)
                current_popup.kill()
            return True
        return False

    def init_level(self):
        self.kill_sprites()

        self.player = Player()
        self.add_sprite(self.player)
        self.add_sprite(TopLabel())
        self.set_missile_spawn_interval(1)

        self.start_time = ticks_ms()
        self.time_elapsed = 0

    def update(self):
        if self.handle_popup():
            return

        if self.get_popup_result("Restart") == "YES":
            self.init_level()
            return

        if self.player.state == Player.STATE_DEAD:
            keyboard = self.input_device
            if (
                GameKeyBoard.ENTER not in keyboard.keys_on
                and GameKeyBoard.BACK in keyboard.keys_released
            ):
                self.popup("Restart", "Restart?\n", ["NO", "YES"])
                return
        else:
            self.spawn_missile_routine()
            self.time_elapsed = ticks_diff(ticks_ms(), self.start_time)
            self.check_collisions()


if __name__ == "__main__":
    asyncio.run(GameManager().arun())
