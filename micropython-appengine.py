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
    """A class for `appengine` exception."""

    pass


class InputDevice:
    """A class for the input device.

    Note:
        This class needs to be subclassed to be useful.
        Override `__init__()` to initialise the input device.
        Override `update()` to implement the logic of the input device.
    """

    def __init__(self):
        pass

    def update(self):
        """This method should implement the logic of the input device.

        It is called before every frame by the manager.

        Raises:
            AppEngineException: An error occurred when this class is not subclassed.

        Note:
            This method must be overridden by a subclass.
        """

        raise AppEngineException(STR_NEEDS_SUBCLASS)


class Screen:
    """A class for the screen.

    Attributes:
        display (FrameBuffer):
            A display object whose class is a subclass of `FrameBuffer`.
            For example, an SSD1306 driver object.
        w (int):
            The width of the screen in pixel.
        h (int):
            The height of the screen in pixel.
        camera_target (Sprite):
            If not `None`, the screen camera will follow this sprite.
            The center of this sprite will be placed at the center of the screen.

    Note:
        This class needs to be subclassed to be useful.
        Override `__init__()` to initialise the screen.
        Override `update()` to show the content of the screen from its buffer.
    """

    def __init__(self):
        self.display = None
        self.w = 0
        self.h = 0
        self.camera_target = None

    def clear(self):
        """Clear the screen buffer and update it."""

        self.display.fill(0)
        self.update()

    def blit(self, sprite: Sprite):
        """Blit the sprite at its position in the screen.

        It is called before every frame for each sprite added to the manager.

        Args:
            sprite:
                A sprite to be placed in the screen at its position.
        """

        img = sprite._get_img()
        if img:
            x = sprite.x
            y = sprite.y
            if self.camera_target and not sprite.is_overlay:
                # Camera target exists and this sprite is not overlay.
                # Translate position according to camera target position.
                ct = self.camera_target
                x -= ct.x + (ct.w - self.w) / 2
                y -= ct.y + (ct.h - self.h) / 2

            self.display.blit(img, int(x), int(y), sprite.colourkey)

    def flip(self):
        """Update the screen and clear the screen buffer.

        It is called before every frame by the manager.
        """

        self.update()
        self.display.fill(0)

    def update(self):
        """This method should show the content of the screen from its buffer.

        For example, the `show()` method of an SSD1306 driver can be called here.

        Raises:
            AppEngineException: An error occurred when this class is not subclassed.

        Note:
            This method must be overridden by a subclass.
        """

        raise AppEngineException(STR_NEEDS_SUBCLASS)


class Sprite:
    """A class for app sprites.

    Attributes:
        UP (int):
            `1`, direction up.
        LEFT (int):
            `2`, direction left.
        DOWN (int):
            `3`, direction down.
        RIGHT (int):
            `4`, direction right.
        x (float):
            The x position of the sprite.
        y (float):
            The y position of the sprite.
        w (int):
            The width of the sprite in pixel.
        h (int):
            The height of the sprite in pixel.
        vx (float):
            The x velocity of the sprite.
        vy (float):
            The y velocity of the sprite.
        imgs (list):
            The list of images to represent the sprite.
            A sequence of images can make animation.
        img_idx (int):
            The index of the image to be shown.
        img_fpstep_counter (int):
            Frames per step counter for animation.
        colourkey (int):
            Transparent colour, `-1` means no transparent colour.
        is_overlay (bool):
            If True, the sprite is ignored by screen camera.
        manager (Manager):
            The manager of the app.
            When a sprite is added to the manager, this attribute is set automatically.
        name (str):
            The name of the sprite.
        killed (bool):
            If True, the sprite will be removed by the manager.

    Note:
        This class needs to be subclassed to be useful.
        Override `__init__()` to initialise the sprite.
        Override `update()` to implement the logic of the sprite.
    """

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
        """Frame routine of the sprite.

        This method is called before every frame by the manager.
        The position of the sprite is updated according to the velocity.
        It maintains the timer to kill the sprite in a delayed manner.
        At last it calls `update()` method for the customised logic.
        """

        self.x += self.vx
        self.y += self.vy

        if self._frames_to_kill is not None:
            self._frames_to_kill -= 1
            if self._frames_to_kill <= 0:
                self.killed = True

        self.update()

    def _get_img(self) -> FrameBuffer:
        """Get the current image of the sprite.

        It is called before every frame.
        It maintains animation for the sprite.

        Returns:
            The current image of the sprite or `None`.
        """

        if not self.imgs:
            return None

        # Keep `self.img_idx` within animation range.
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

    def get_layer(self) -> int:
        """Get the layer in which the sprite is located.

        A larger number means the sprite is in a more upper layer.

        Returns:
            The layer in which the sprite is located.
        """

        return self._layer

    def set_layer(self, layer: int):
        """Set the layer in which the sprite is located.

        A larger number means the sprite is in a more upper layer.

        Args:
            layer:
                The layer in which the sprite is located.
        """

        self._layer = layer
        if self.manager:
            self.manager._sort_sprites_by_layer()

    def setup_animation(self, start: int, length: int, fpstep: int):
        """Setup animation for the sprite.

        Args:
            start:
                The start index of the images for animation.
            length:
                The length of the images for animation.
            fpstep:
                Frames per step for animation speed.
        """

        self._img_start = start
        self._img_len = length
        self._img_fpstep = fpstep

    def clamp_position(
        self,
        up: float = None,
        left: float = None,
        down: float = None,
        right: float = None,
    ):
        """Clamp the position of the sprite.

        This method clamps the position of the sprite.
        The size of the sprite is taken into account.
        The up and left limits are inclusive.
        The down and right limits are exclusive.
        When there is conflict in left and right limits, the left limit overrides.
        When there is conflict in up and down limits, the up limit overrides.

        Args:
            up:
                Up limit of the up side of the sprite.
            left:
                Left limit of the left side of the sprite.
            down:
                Down limit of the down side of the sprite.
            right:
                Right limit of the right side of the sprite.
        """

        if (right is not None) and (self.x > right - self.w):
            self.x = right - self.w
        if (left is not None) and (self.x < left):
            self.x = left
        if (down is not None) and (self.y > down - self.h):
            self.y = down - self.h
        if (up is not None) and (self.y < up):
            self.y = up

    def clamp_velocity(
        self,
        vx_min: float = None,
        vx_max: float = None,
        vy_min: float = None,
        vy_max: float = None,
    ):
        """Clamp the velocity of the sprite.

        Args:
            vx_min:
                Min limit of x velocity of the sprite.
            vx_max:
                Max limit of x velocity of the sprite.
            vy_min:
                Min limit of y velocity of the sprite.
            vy_max:
                Max limit of y velocity of the sprite.
        """

        if (vx_min is not None) and (self.vx < vx_min):
            self.vx = vx_min
        if (vx_max is not None) and (self.vx > vx_max):
            self.vx = vx_max
        if (vy_min is not None) and (self.vy < vy_min):
            self.vy = vy_min
        if (vy_max is not None) and (self.vy > vy_max):
            self.vy = vy_max

    def kill(self):
        """Kill the sprite, so it will be removed by the manager."""

        self.killed = True

    def kill_after_n_frames(self, num: int):
        """Kill the sprite in a delayed manner.

        Args:
            num:
                The number of frames after which the sprite will be killed.
                For example, given 20 FPS,
                setting 40 will kill the sprite after 2 seconds.
        """

        self._frames_to_kill = num

    def check_collision(self, other: Sprite) -> tuple[int, int]:
        """Check collision with the other sprite.

        This is a simple example of collision detection.
        It can be overridden with other implementation.
        When there is no collision detected, it returns `None`.
        When collision is detected, a 2-tuple is returned.
        The first element indicates where the collision happened.
        It could be `Sprite.UP`, `Sprite.LEFT`, `Sprite.DOWN` or `Sprite.RIGHT`.
        The second element indicates how deep the collision is in pixel.

        Args:
            other:
                The other sprite to check collision with.

        Returns:
            A 2-tuple or `None`.
        """

        if isinstance(other, Sprite) and (other is not self):
            diff_x = (self.x + self.w / 2) - (other.x + other.w / 2)
            diff_y = (self.y + self.h / 2) - (other.y + other.h / 2)
            margin_dx = abs(diff_x) - ((self.w + other.w) / 2)
            margin_dy = abs(diff_y) - ((self.h + other.h) / 2)

            if margin_dx < 0 and margin_dy < 0:
                # Collision happened.
                abs_margin_dy = abs(margin_dy)
                abs_margin_dx = abs(margin_dx)
                is_at_top_or_bottom = abs_margin_dy <= abs_margin_dx
                if diff_y >= 0:
                    if diff_x >= 0:
                        # `other` is top-left to `self`.
                        if is_at_top_or_bottom:
                            return (self.UP, abs_margin_dy)
                        else:
                            return (self.LEFT, abs_margin_dx)
                    else:
                        # `other` is top-right to `self`.
                        if is_at_top_or_bottom:
                            return (self.UP, abs_margin_dy)
                        else:
                            return (self.RIGHT, abs_margin_dx)
                else:
                    if diff_x >= 0:
                        # `other` is bottom-left to `self`.
                        if is_at_top_or_bottom:
                            return (self.DOWN, abs_margin_dy)
                        else:
                            return (self.LEFT, abs_margin_dx)
                    else:
                        # `other` is bottom-right to `self`.
                        if is_at_top_or_bottom:
                            return (self.DOWN, abs_margin_dy)
                        else:
                            return (self.RIGHT, abs_margin_dx)

        return None

    def update(self):
        """This method may implement the logic of the sprite.

        It is called before every frame.
        A passive sprite may not override it.
        """

        pass


class Manager:
    """A class for app manager.

    Attributes:
        DEFAULT_TARGET_FPS (int):
            `20`, default target FPS (frames per second).
        input_device (InputDevice):
            The input device.
        screen (Screen):
            The screen.
        sprite_list (list):
            The list holding all the available sprites.
        target_fps (float):
            The target FPS.
        actual_fps (float):
            The actual FPS.
        running (bool):
            The flag indicating the app is running or not.

    Note:
        This class needs to be subclassed to be useful.
        Override `__init__()` to initialise the manager.
        Override `update()` to implement the logic of the manager.
    """

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
        """Remove all the killed sprites from the manager."""

        self.sprite_list = [sprite for sprite in self.sprite_list if not sprite.killed]

    def _sort_sprites_by_layer(self):
        """Sort all the sprites added to the manager by their layer."""

        self.sprite_list.sort(key=lambda x: x.get_layer())

    def _frame_routine(self):
        """Frame routine.

        It is called before every frame by the manager.
        In turn it calls the frame routines of all the components added to the manager.
        """

        # Input device frame routine.
        if self.input_device:
            self.input_device.update()

        # Sprites frame routines.
        for sprite in self.sprite_list:
            sprite._frame_routine()

        self.update()
        self._remove_killed_sprites()

        # Screen frame routine.
        if self.screen:
            for sprite in self.sprite_list:
                self.screen.blit(sprite)
            self.screen.flip()

        gc.collect()

    def _frame_tick(self) -> bool:
        """Frame tick.

        By polling this method, the manager can try to achieve the target FPS.
        It also calculates the actual FPS.

        Returns:
            The time for the next frame is reached or not.
        """

        end_time = ticks_us()
        duration = ticks_diff(end_time, self._frame_start_time)
        if duration >= US_PER_S / self.target_fps:
            self.actual_fps = US_PER_S / duration
            self._frame_start_time = end_time
            return True
        return False

    def add_sprite(self, sprite: Sprite):
        """Add a sprite to the manager.

        Args:
            sprite:
                The sprite to be added to the manager.
        """

        self.sprite_list.append(sprite)
        self._sort_sprites_by_layer()
        sprite.manager = self

    def get_sprites(self, cls: type = Sprite, name: str = None) -> list[Sprite, ...]:
        """Get a filtered list of sprites.

        Args:
            cls:
                The class of the sprites that should be returned.
            name:
                The name of the sprites that should be returned.

        Returns:
            A list of selected sprites.
        """

        return [
            sprite
            for sprite in self.sprite_list
            if isinstance(sprite, cls) and ((not name) or (sprite.name == name))
        ]

    def kill_sprites(self, cls: type = Sprite, name: str = None):
        """Kill a filtered list of sprites.

        Args:
            cls:
                The class of the sprites that should be killed.
            name:
                The name of the sprites that should be killed.
        """

        for sprite in self.sprite_list:
            if isinstance(sprite, cls) and ((not name) or (sprite.name == name)):
                sprite.kill()

    def exit(self):
        """Exit the app."""

        self.running = False

    def run(self):
        """Run the app."""

        if self.screen:
            self.screen.clear()

        while self.running:
            # Manager frame routine.
            self._frame_routine()

            # Try to achieve the target FPS.
            while not self._frame_tick():
                pass

    async def arun(self):
        """Run the app asynchronously with `uasyncio`."""

        if self.screen:
            self.screen.clear()

        while self.running:
            await asyncio.sleep(0)
            # Manager frame routine.
            self._frame_routine()

            # Try to achieve the target FPS.
            while not self._frame_tick():
                await asyncio.sleep(0)

    def update(self):
        """This method may implement the logic of the manager.

        It is called before every frame.
        A very simple app may not override it.
        """

        pass
