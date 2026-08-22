"""OpenGL cursor loading and rendering."""

import pygame
from OpenGL.GL import *

from rendering_helpers import PIL_AVAILABLE, pil_load_image_rgba
from sourcebox.resources import find_resource
class CursorRenderer:
    def __init__(self, cursor_file):
        self.texture_id = None
        self.width = 0
        self.height = 0
        self.enabled = False
        self.scale = 1.0
        self.load_cursor(cursor_file)

    def load_cursor(self, cursor_file):
        try:
            cursor_candidates = [
                'assets/images/cursor.png',
                cursor_file,
                'cursor.png'
            ]
            cursor_path = find_resource(cursor_candidates)

            if cursor_path:
                try:
                    cursor_img = pygame.image.load(cursor_path).convert_alpha()
                    cursor_img = pygame.transform.flip(cursor_img, False, True)
                    self._create_texture(cursor_img)
                    self.enabled = True
                    print(f"Cursor loaded: {cursor_path}")
                    return True
                except Exception as e:
                    if PIL_AVAILABLE:
                        pil_result = pil_load_image_rgba(cursor_path, flip_y=False)
                        if pil_result:
                            cursor_data, width, height = pil_result
                            self._create_texture_rgba(cursor_data, width, height)
                            if self.texture_id:
                                self.enabled = True
                                print(f"Cursor loaded: {cursor_path}")
                                return True

                    print(f"Error loading cursor from {cursor_path}: {e}")

            print("No cursor loaded, using system cursor")
            return False
        except Exception as e:
            print(f"Cursor loading error: {e}")
            return False

    def _create_texture(self, cursor_img):
        try:
            cursor_data = pygame.image.tostring(cursor_img, "RGBA", True)
            self.width = cursor_img.get_width()
            self.height = cursor_img.get_height()

            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width, self.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, cursor_data)
        except Exception as e:
            print(f"Error creating cursor texture: {e}")
            self.texture_id = None

    def _create_texture_rgba(self, rgba_data: bytes, width: int, height: int):
        try:
            self.width = int(width)
            self.height = int(height)

            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                self.width,
                self.height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                rgba_data,
            )
        except Exception as e:
            print(f"Error creating cursor texture: {e}")
            self.texture_id = None

    def set_scale(self, scale):
        """set cursor scale factor"""
        self.scale = max(1.0, min(2.0, scale))

    def draw(self, mouse_pos, display_width, display_height):
        if not self.enabled or self.texture_id is None:
            return

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)

        glColor4f(1.0, 1.0, 1.0, 1.0)
        x, y = mouse_pos
        w = self.width * self.scale
        h = self.height * self.scale

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 1); glVertex2f(x, y + h)
        glEnd()

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def cleanup(self):
        if self.texture_id:
            try:
                glDeleteTextures([self.texture_id])
            except:
                pass
            self.texture_id = None
