"""Missing-texture error scene."""

import math
import platform as system_platform
import random

import pygame
from OpenGL.GL import *

from rendering_helpers import PIL_AVAILABLE, pil_render_text_rgba
from sourcebox.resources import find_resource
from sourcebox.runtime import pygame_font_available

PLATFORM = system_platform.system()
class MissingTextureScene:
    def __init__(self, sound_manager=None, display_scale=1.0):
        self.display_list = None
        self.text = "WARNING: NO GRAPHICS DRIVER DETECTED. PLEASE ENABLE A VALID GRAPHICS DRIVER."
        self.text_visible = True
        self.flash_timer = 0.0
        self.next_flash_interval = random.choice([0.1, 0.3, 0.5])
        self.text_texture = None
        self.text_width = 0
        self.text_height = 0
        self.sound_manager = sound_manager
        self.create_text_texture()

    def create_text_texture(self):
        font_size = 36
        char_spacing = 2

        # Pygame path (fastest when available)
        if pygame_font_available():
            try:
                if PLATFORM == "Windows":
                    font_candidates = ["Trebuchet MS", "Arial", "Verdana"]
                else:
                    font_candidates = ["DejaVu Sans", "Liberation Sans", "FreeSans", "Arial"]

                font = None
                for font_candidate in font_candidates:
                    try:
                        font = pygame.font.SysFont(font_candidate, font_size)
                        break
                    except Exception:
                        continue

                if font is None:
                    font = pygame.font.Font(None, font_size)

                total_width = 0
                char_surfaces = []
                for char in self.text:
                    char_surf = font.render(char, True, (255, 0, 0))
                    char_surfaces.append(char_surf)
                    total_width += char_surf.get_width() + char_spacing

                total_width = max(1, total_width - char_spacing)
                max_height = max(1, max(surf.get_height() for surf in char_surfaces))

                text_surface = pygame.Surface((total_width, max_height), pygame.SRCALPHA)
                text_surface.fill((0, 0, 0, 0))

                x_offset = 0
                for char_surf in char_surfaces:
                    text_surface.blit(char_surf, (x_offset, 0))
                    x_offset += char_surf.get_width() + char_spacing

                text_data = pygame.image.tostring(text_surface, "RGBA", True)

                self.text_width = text_surface.get_width()
                self.text_height = text_surface.get_height()

                self.text_texture = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, self.text_texture)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexImage2D(
                    GL_TEXTURE_2D,
                    0,
                    GL_RGBA,
                    self.text_width,
                    self.text_height,
                    0,
                    GL_RGBA,
                    GL_UNSIGNED_BYTE,
                    text_data,
                )
                return
            except Exception:
                pass

        # Pillow path (works when pygame.font is not built)
        if PIL_AVAILABLE:
            cabin_font_path = find_resource(
                [
                    "assets/fonts/Cabin-Regular.ttf",
                    "fonts/Cabin-Regular.ttf",
                    "Cabin-Regular.ttf",
                ]
            )

            rendered = pil_render_text_rgba(
                self.text,
                font_path=cabin_font_path,
                font_size=font_size,
                color=(255, 0, 0, 255),
                letter_spacing=char_spacing,
                bold=False,
                flip_y=True,
            )
            if rendered:
                text_data, self.text_width, self.text_height = rendered

                self.text_texture = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, self.text_texture)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexImage2D(
                    GL_TEXTURE_2D,
                    0,
                    GL_RGBA,
                    self.text_width,
                    self.text_height,
                    0,
                    GL_RGBA,
                    GL_UNSIGNED_BYTE,
                    text_data,
                )
                return

        self.text_texture = None

    def create_display_list(self):
        if self.display_list is not None:
            return

        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return

            glNewList(self.display_list, GL_COMPILE)

            size = 50
            block_width = 0.7
            block_height = 0.5

            glBegin(GL_QUADS)
            for x in range(-size, size):
                for z in range(-size, size):
                    if (x + z) & 1:
                        glColor3f(1.0, 0.0, 1.0)
                    else:
                        glColor3f(0.0, 0.0, 0.0)

                    center_x = 0
                    center_z = 0

                    corners = [
                        (x, z),
                        (x, z+1),
                        (x+1, z+1),
                        (x+1, z)
                    ]

                    vertices = []
                    for cx, cz in corners:
                        dx = cx - center_x
                        dz = cz - center_z
                        dist = math.sqrt(dx*dx + dz*dz)

                        push_amount = dist * 0.03

                        if dist > 0:
                            push_x = (dx / dist) * push_amount
                            push_z = (dz / dist) * push_amount
                        else:
                            push_x = 0
                            push_z = 0

                        x_pos = cx * block_width + push_x
                        z_pos = cz * block_height + push_z

                        vertices.append((x_pos, z_pos))

                    glVertex3f(vertices[0][0], vertices[0][1], 0)
                    glVertex3f(vertices[1][0], vertices[1][1], 0)
                    glVertex3f(vertices[2][0], vertices[2][1], 0)
                    glVertex3f(vertices[3][0], vertices[3][1], 0)
            glEnd()

            glEndList()
        except Exception as e:
            print(f"Error creating missing texture display list: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None

    def update(self, dt):
        self.flash_timer += dt
        if self.flash_timer >= self.next_flash_interval:
            self.text_visible = not self.text_visible
            self.flash_timer = 0.0
            self.next_flash_interval = random.choice([0.01, 0.05, 0.09])

    def draw(self, display_width, display_height):
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-display_width/200.0, display_width/200.0, -display_height/200.0, display_height/200.0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        if self.display_list:
            glCallList(self.display_list)

        if self.text_visible and self.text_texture:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.text_texture)
            glColor4f(1.0, 1.0, 1.0, 1.0)

            target_width_percentage = 0.8
            ortho_width = display_width / 100.0
            target_width = ortho_width * target_width_percentage

            scale_factor = target_width / self.text_width

            w = self.text_width * scale_factor
            h = self.text_height * scale_factor

            x = -w / 2.0
            y = -h / 24.0

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
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None
        if self.text_texture:
            try:
                glDeleteTextures([self.text_texture])
            except:
                pass
            self.text_texture = None
