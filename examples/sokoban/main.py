"""Sokoban made with appengine.

- Author: Quan Lin
- License: MIT
"""

import os
from math import ceil
from collections import namedtuple
import uasyncio as asyncio
from machine import Pin, I2C, TouchPad
from framebuf import FrameBuffer, MONO_VLSB
from ssd1306 import SSD1306_I2C
from microbmp import MicroBMP
from appengine import InputDevice, Screen, Sprite, Manager


IMAGES_DIR = "images/"
LEVELS_DIR = "levels/"

Point = namedtuple("Point", ("x", "y"))


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


def mirror_framebuf_h(fb, w, h):
    new_fb = FrameBuffer(bytearray(w * ceil(h / 8)), w, h, MONO_VLSB)
    for y in range(h):
        for x in range(w):
            new_fb.pixel(x, y, fb.pixel(w - x - 1, y))
    return new_fb


class Menu:
    def __init__(self):
        self.levels = os.listdir(LEVELS_DIR)
        self.max_show_num = GameScreen.HEIGHT // 8 + 3

        self.cur_idx = None
        self.cur_level = None
        self.start_idx = None
        self.end_idx = None

        if self.levels:
            self.set_cur_idx(0)

    def set_cur_idx(self, idx):
        levels_len = len(self.levels)
        half_max_show_num = self.max_show_num // 2
        idx %= levels_len
        self.cur_idx = idx
        self.cur_level = self.levels[self.cur_idx]
        self.start_idx = self.cur_idx - half_max_show_num
        self.end_idx = self.cur_idx + half_max_show_num

        if self.start_idx < 0:
            self.end_idx += abs(self.start_idx)
            self.start_idx = 0
        elif self.end_idx >= levels_len:
            self.start_idx -= self.end_idx - (levels_len - 1)
            self.end_idx = levels_len - 1

        if self.start_idx < 0:
            self.start_idx = 0
        if self.end_idx > levels_len - 1:
            self.end_idx = levels_len - 1


class SokobanBoard:
    UP, LEFT, DOWN, RIGHT = tuple(range(1, 5))

    def __init__(self):
        self.clear()

    def __str__(self):
        self._grid = [[" " for c in range(self.nc)] for r in range(self.nr)]

        for wall in self.walls:
            self._grid[wall.y][wall.x] = "#"

        for goal in self.goals:
            self._grid[goal.y][goal.x] = "."

        for box in self.boxes:
            if box in self.goals:
                self._grid[box.y][box.x] = "*"
            else:
                self._grid[box.y][box.x] = "$"

        if self.player in self.goals:
            self._grid[self.player.y][self.player.x] = "+"
        else:
            self._grid[self.player.y][self.player.x] = "@"

        return "\n".join(["".join(line) for line in self._grid])

    def _can_move(self, direction):
        if self.player:
            if direction == self.UP:
                pp = Point(self.player.x, self.player.y - 1)
                bp = Point(self.player.x, self.player.y - 2)
            elif direction == self.LEFT:
                pp = Point(self.player.x - 1, self.player.y)
                bp = Point(self.player.x - 2, self.player.y)
            elif direction == self.DOWN:
                pp = Point(self.player.x, self.player.y + 1)
                bp = Point(self.player.x, self.player.y + 2)
            elif direction == self.RIGHT:
                pp = Point(self.player.x + 1, self.player.y)
                bp = Point(self.player.x + 2, self.player.y)
            else:
                return False

            if pp in self.walls:
                return False
            elif pp in self.boxes:
                if bp in (self.boxes | self.walls):
                    return False
                else:
                    return True
            else:
                return True

        return False

    def clear(self):
        self.player = None
        self.walls = set()
        self.goals = set()
        self.boxes = set()
        self.nr = 0
        self.nc = 0

    def load(self, board_path):
        self.clear()
        with open(board_path) as file:
            self._grid = [[char for char in line.rstrip()] for line in file]

        for y, row in enumerate(self._grid):
            for x, char in enumerate(row):
                if char == "@":
                    self.player = Point(x, y)
                elif char == "#":
                    self.walls.add(Point(x, y))
                elif char == ".":
                    self.goals.add(Point(x, y))
                elif char == "*":
                    self.goals.add(Point(x, y))
                    self.boxes.add(Point(x, y))
                elif char == "+":
                    self.goals.add(Point(x, y))
                    self.player = Point(x, y)
                elif char == "$":
                    self.boxes.add(Point(x, y))

        self.nr = len(self._grid)
        self.nc = max([len(row) for row in self._grid])

    def move(self, direction):
        if self._can_move(direction):
            if direction == self.UP:
                self.player = Point(self.player.x, self.player.y - 1)
                if self.player in self.boxes:
                    self.boxes.discard(self.player)
                    self.boxes.add(Point(self.player.x, self.player.y - 1))
            elif direction == self.LEFT:
                self.player = Point(self.player.x - 1, self.player.y)
                if self.player in self.boxes:
                    self.boxes.discard(self.player)
                    self.boxes.add(Point(self.player.x - 1, self.player.y))
            elif direction == self.DOWN:
                self.player = Point(self.player.x, self.player.y + 1)
                if self.player in self.boxes:
                    self.boxes.discard(self.player)
                    self.boxes.add(Point(self.player.x, self.player.y + 1))
            elif direction == self.RIGHT:
                self.player = Point(self.player.x + 1, self.player.y)
                if self.player in self.boxes:
                    self.boxes.discard(self.player)
                    self.boxes.add(Point(self.player.x + 1, self.player.y))

            return True

        return False

    def is_solved(self):
        return not (self.goals ^ self.boxes)


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

    FB0 = framebuf_from_img(IMAGES_DIR + "bobo00.bmp")
    FB1 = framebuf_from_img(IMAGES_DIR + "bobo01.bmp")
    FB2 = framebuf_from_img(IMAGES_DIR + "bobo02.bmp")

    FB_MH0 = mirror_framebuf_h(FB0, WIDTH, HEIGHT)
    FB_MH1 = mirror_framebuf_h(FB1, WIDTH, HEIGHT)
    FB_MH2 = mirror_framebuf_h(FB2, WIDTH, HEIGHT)

    def __init__(self, x, y):
        super().__init__()

        self.x = x
        self.y = y
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [
            self.FB0,
            self.FB1,
            self.FB2,
            self.FB1,
            self.FB_MH0,
            self.FB_MH1,
            self.FB_MH2,
            self.FB_MH1,
        ]
        self.colourkey = 0
        self.setup_animation(0, 4, 2)
        self.set_layer(1)
        self.name = "player"
        self.is_moving = False

    def update(self):
        target_point = self.manager.board.player
        target_x = target_point.x * self.WIDTH
        target_y = target_point.y * self.HEIGHT
        if self.x < target_x:
            self.vx = 2
            self.is_moving = True
            self.setup_animation(0, 4, 2)
        elif self.x > target_x:
            self.vx = -2
            self.is_moving = True
            self.setup_animation(4, 4, 2)
        elif self.y < target_y:
            self.vy = 2
            self.is_moving = True
        elif self.y > target_y:
            self.vy = -2
            self.is_moving = True
        else:
            self.vx = 0
            self.vy = 0
            self.is_moving = False


class Wall(Sprite):
    WIDTH = 8
    HEIGHT = 8

    FB0 = framebuf_from_img(IMAGES_DIR + "wall00.bmp")

    def __init__(self, x, y):
        super().__init__()

        self.x = x
        self.y = y
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [self.FB0]


class Goal(Sprite):
    WIDTH = 8
    HEIGHT = 8

    FB0 = framebuf_from_img(IMAGES_DIR + "goal00.bmp")
    FB1 = framebuf_from_img(IMAGES_DIR + "goal01.bmp")
    FB2 = framebuf_from_img(IMAGES_DIR + "goal02.bmp")

    def __init__(self, x, y):
        super().__init__()

        self.x = x
        self.y = y
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [
            self.FB0,
            self.FB1,
            self.FB2,
        ]
        self.setup_animation(0, 3, 5)


class Box(Sprite):
    WIDTH = 8
    HEIGHT = 8

    FB0 = framebuf_from_img(IMAGES_DIR + "box00.bmp")

    def __init__(self, x, y):
        super().__init__()

        self.x = x
        self.y = y
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.imgs = [self.FB0]
        self.colourkey = 0
        self.set_layer(1)

    def update(self):
        player = self.manager.player
        collision = self.check_collision(player)
        if collision:
            if collision[0] == self.UP:
                self.clamp_position(up=player.y + player.HEIGHT)
            elif collision[0] == self.LEFT:
                self.clamp_position(left=player.x + player.WIDTH)
            elif collision[0] == self.DOWN:
                self.clamp_position(down=player.y)
            elif collision[0] == self.RIGHT:
                self.clamp_position(right=player.x)


class CameraTarget(Sprite):
    def __init__(self, following=None, boundary=None):
        super().__init__()

        self.w = GameScreen.WIDTH
        self.h = GameScreen.HEIGHT

        self.following = following
        self.boundary = boundary

    def update(self):
        if self.following:
            self.x = self.following.x - (self.w - self.following.w) / 2
            self.y = self.following.y - (self.h - self.following.h) / 2
            if self.boundary:
                self.clamp_position(
                    self.boundary.up,
                    self.boundary.left,
                    self.boundary.down,
                    self.boundary.right,
                )


class CameraTargetBoundary:
    def __init__(self, up=None, left=None, down=None, right=None):
        self.up = up
        self.left = left
        self.down = down
        self.right = right


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

    def __init__(self, text="", buttons=None):
        super().__init__()

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


class GameManager(Manager):
    SPLASH, MENU, LEVEL = tuple(range(1, 4))

    def __init__(self):
        super().__init__()

        self.input_device = GameKeyBoard()
        self.screen = GameScreen()
        self.screen.manager = self
        self.menu = Menu()
        self.board = SokobanBoard()

        self._popup_result = None
        self.state = None

        self.init_splash()

    def set_camera(self, following=None, boundary=None):
        if following:
            camera_target = CameraTarget(following, boundary)
            self.add_sprite(camera_target)
            self.screen.camera_target = camera_target
            camera_target.update()
        else:
            self.screen.camera_target = None
            self.kill_sprites(CameraTarget)

    def get_popup_result(self):
        res = self._popup_result
        self._popup_result = None
        return res

    def set_popup_result(self, res):
        self._popup_result = res

    def popup(self, text="", buttons=None):
        self.add_sprite(PopUp(text, buttons))

    def handle_popup(self):
        popups = self.get_sprites(PopUp)
        if popups:
            res = popups[0].result
            if res is not None:
                self.set_popup_result(res)
                popups[0].kill()
            return True
        return False

    def init_splash(self):
        self.state = self.SPLASH
        self.kill_sprites()

        self.popup(f"{'Sokoban':^{PopUp.WIDTH}s}\n", ["START"])

    def handle_splash(self):
        if self.handle_popup():
            return

        if self.get_popup_result() == "START":
            self.init_menu()

    def init_menu(self):
        self.state = self.MENU
        self.kill_sprites()

        self.update_menu()

    def update_menu(self):
        self.kill_sprites()
        for i in range(self.menu.start_idx, self.menu.end_idx + 1):
            text = f"{self.menu.levels[i].split('.')[0]:^12s}"
            menu_item = Overlay()
            y = GameScreen.HEIGHT // 2 - 4 + (i - self.menu.cur_idx) * 8
            menu_item.y = y
            menu_item.set_text(
                text=text,
                anchor_h=Overlay.H_CENTER,
                invert=True if i == self.menu.cur_idx else False,
            )
            self.add_sprite(menu_item)

    def handle_menu(self):
        keyboard = self.input_device
        if GameKeyBoard.UP in keyboard.keys_pressed:
            self.menu.set_cur_idx(self.menu.cur_idx - 1)
            self.update_menu()
        elif GameKeyBoard.DOWN in keyboard.keys_pressed:
            self.menu.set_cur_idx(self.menu.cur_idx + 1)
            self.update_menu()
        elif GameKeyBoard.ENTER in keyboard.keys_released:
            self.init_level()

    def init_level(self):
        self.state = self.LEVEL
        self.kill_sprites()

        self.board.load(LEVELS_DIR + self.menu.cur_level)

        self.player = Player(
            self.board.player.x * Player.WIDTH,
            self.board.player.y * Player.HEIGHT,
        )
        self.add_sprite(self.player)

        bw = self.board.nc * Player.WIDTH
        bh = self.board.nr * Player.HEIGHT
        up = 0 if bh >= GameScreen.HEIGHT else (bh - GameScreen.HEIGHT) // 2
        left = 0 if bw >= GameScreen.WIDTH else (bw - GameScreen.WIDTH) // 2
        down = bh
        right = bw
        self.set_camera(self.player, CameraTargetBoundary(up, left, down, right))

        for wall in self.board.walls:
            self.add_sprite(Wall(wall.x * Wall.WIDTH, wall.y * Wall.HEIGHT))
        for goal in self.board.goals:
            self.add_sprite(Goal(goal.x * Goal.WIDTH, goal.y * Goal.HEIGHT))
        for box in self.board.boxes:
            self.add_sprite(Box(box.x * Box.WIDTH, box.y * Box.HEIGHT))

    def handle_level(self):
        if self.handle_popup():
            return

        if self.board.is_solved():
            if self.get_popup_result() == "OK":
                self.set_camera(None)
                self.init_menu()
            else:
                self.popup("Solved", ["OK"])
            return

        if self.get_popup_result() == "YES":
            self.set_camera(None)
            self.init_menu()
            return

        keyboard = self.input_device

        if (
            GameKeyBoard.ENTER not in keyboard.keys_on
            and GameKeyBoard.BACK in keyboard.keys_released
        ):
            self.popup("Back to menu?\n", ["NO", "YES"])
            return

        if not self.player.is_moving:
            if GameKeyBoard.UP in keyboard.keys_on:
                self.board.move(SokobanBoard.UP)
            elif GameKeyBoard.LEFT in keyboard.keys_on:
                self.board.move(SokobanBoard.LEFT)
            elif GameKeyBoard.DOWN in keyboard.keys_on:
                self.board.move(SokobanBoard.DOWN)
            elif GameKeyBoard.RIGHT in keyboard.keys_on:
                self.board.move(SokobanBoard.RIGHT)

    def update(self):
        if self.state == self.SPLASH:
            self.handle_splash()
        elif self.state == self.MENU:
            self.handle_menu()
        elif self.state == self.LEVEL:
            self.handle_level()


if __name__ == "__main__":
    asyncio.run(GameManager().arun())
