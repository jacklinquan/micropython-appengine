"""A MicroPython app engine.

- Author: Quan Lin
- License: MIT
"""

__version__ = "0.1.0"
__all__ = ["AppEngineException", "InputDevice", "Screen", "Sprite", "Manager"]

import gc
from time import ticks_us, ticks_diff
import uasyncio as asyncio

US_PER_S = 1000000
STR_NEEDS_SUBCLASS = "Needs to be overridden by a subclass."


class AppEngineException(Exception):
    pass


class InputDevice:
    def __init__(self):
        pass

    def update(self):
        raise AppEngineException(STR_NEEDS_SUBCLASS)


class Screen:
    def __init__(self):
        self.display = None
        self.w = 0
        self.h = 0
        self.camera_target = None

    def clear(self):
        self.display.fill(0)
        self.update()

    def blit(self, sprite):
        img = sprite._get_img()
        if img:
            x = sprite.x
            y = sprite.y
            if self.camera_target and not sprite.is_overlay:
                ct = self.camera_target
                x -= ct.x + (ct.w - self.w) / 2
                y -= ct.y + (ct.h - self.h) / 2
            self.display.blit(img, int(x), int(y), sprite.colourkey)

    def flip(self):
        self.update()
        self.display.fill(0)

    def update(self):
        raise AppEngineException(STR_NEEDS_SUBCLASS)


class Sprite:
    UP, LEFT, DOWN, RIGHT = tuple(range(1, 5))

    def __init__(self):
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0
        self.vx = 0
        self.vy = 0
        self.imgs = []
        self.img_idx = 0
        self.img_fpstep_counter = 0
        self._img_start = 0
        self._img_len = 0
        self._img_fpstep = 1
        self.colourkey = -1
        self.is_overlay = False
        self._layer = 0
        self.manager = None
        self.name = ""
        self.killed = False
        self._frames_to_kill = None

    def _frame_routine(self):
        self.x += self.vx
        self.y += self.vy
        if self._frames_to_kill is not None:
            self._frames_to_kill -= 1
            if self._frames_to_kill <= 0:
                self.killed = True
        self.update()

    def _get_img(self):
        if not self.imgs:
            return None
        self.img_idx = (
            (self.img_idx - self._img_start) % self._img_len + self._img_start
            if self._img_len
            else self._img_start
        )
        current_img = self.imgs[self.img_idx]
        self.img_fpstep_counter = (self.img_fpstep_counter + 1) % self._img_fpstep
        if self.img_fpstep_counter == 0:
            self.img_idx += 1
        return current_img

    def get_layer(self):
        return self._layer

    def set_layer(self, layer):
        self._layer = layer
        if self.manager:
            self.manager._sort_sprites_by_layer()

    def setup_animation(self, start, length, fpstep):
        self._img_start = start
        self._img_len = length
        self._img_fpstep = fpstep

    def clamp_position(self, up=None, left=None, down=None, right=None):
        if right is not None and self.x > right - self.w:
            self.x = right - self.w
        if left is not None and self.x < left:
            self.x = left
        if down is not None and self.y > down - self.h:
            self.y = down - self.h
        if up is not None and self.y < up:
            self.y = up

    def clamp_velocity(self, vx_min=None, vx_max=None, vy_min=None, vy_max=None):
        if vx_min is not None and self.vx < vx_min:
            self.vx = vx_min
        if vx_max is not None and self.vx > vx_max:
            self.vx = vx_max
        if vy_min is not None and self.vy < vy_min:
            self.vy = vy_min
        if vy_max is not None and self.vy > vy_max:
            self.vy = vy_max

    def kill(self):
        self.killed = True

    def kill_after_n_frames(self, num):
        self._frames_to_kill = num

    def check_collision(self, other):
        if isinstance(other, Sprite) and other is not self:
            diff_x = self.x + self.w / 2 - (other.x + other.w / 2)
            diff_y = self.y + self.h / 2 - (other.y + other.h / 2)
            margin_dx = abs(diff_x) - (self.w + other.w) / 2
            margin_dy = abs(diff_y) - (self.h + other.h) / 2
            if margin_dx < 0 and margin_dy < 0:
                abs_margin_dy = abs(margin_dy)
                abs_margin_dx = abs(margin_dx)
                is_at_top_or_bottom = abs_margin_dy <= abs_margin_dx
                if diff_y >= 0:
                    if diff_x >= 0:
                        if is_at_top_or_bottom:
                            return self.UP, abs_margin_dy
                        else:
                            return self.LEFT, abs_margin_dx
                    elif is_at_top_or_bottom:
                        return self.UP, abs_margin_dy
                    else:
                        return self.RIGHT, abs_margin_dx
                elif diff_x >= 0:
                    if is_at_top_or_bottom:
                        return self.DOWN, abs_margin_dy
                    else:
                        return self.LEFT, abs_margin_dx
                elif is_at_top_or_bottom:
                    return self.DOWN, abs_margin_dy
                else:
                    return self.RIGHT, abs_margin_dx
        return None

    def update(self):
        pass


class Manager:
    DEFAULT_TARGET_FPS = 20

    def __init__(self):
        self.input_device = None
        self.screen = None
        self.sprite_list = []
        self.target_fps = self.DEFAULT_TARGET_FPS
        self.actual_fps = 0
        self._frame_start_time = ticks_us()
        self.running = True

    def _remove_killed_sprites(self):
        self.sprite_list = [sprite for sprite in self.sprite_list if not sprite.killed]

    def _sort_sprites_by_layer(self):
        self.sprite_list.sort(key=lambda x: x.get_layer())

    def _frame_routine(self):
        if self.input_device:
            self.input_device.update()
        for sprite in self.sprite_list:
            sprite._frame_routine()
        self.update()
        self._remove_killed_sprites()
        if self.screen:
            for sprite in self.sprite_list:
                self.screen.blit(sprite)
            self.screen.flip()
        gc.collect()

    def _frame_tick(self):
        end_time = ticks_us()
        duration = ticks_diff(end_time, self._frame_start_time)
        if duration >= US_PER_S / self.target_fps:
            self.actual_fps = US_PER_S / duration
            self._frame_start_time = end_time
            return True
        return False

    def add_sprite(self, sprite):
        self.sprite_list.append(sprite)
        self._sort_sprites_by_layer()
        sprite.manager = self

    def get_sprites(self, cls=Sprite, name=None):
        return [
            sprite
            for sprite in self.sprite_list
            if isinstance(sprite, cls) and (not name or sprite.name == name)
        ]

    def kill_sprites(self, cls=Sprite, name=None):
        for sprite in self.sprite_list:
            if isinstance(sprite, cls) and (not name or sprite.name == name):
                sprite.kill()

    def exit(self):
        self.running = False

    def run(self):
        if self.screen:
            self.screen.clear()
        while self.running:
            self._frame_routine()
            while not self._frame_tick():
                pass

    async def arun(self):
        if self.screen:
            self.screen.clear()
        while self.running:
            await asyncio.sleep(0)
            self._frame_routine()
            while not self._frame_tick():
                await asyncio.sleep(0)

    def update(self):
        pass
