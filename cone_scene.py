import pygame
import math
import random
import os
from pathlib import Path
import sys
from OpenGL.GL import *
from OpenGL.GLU import *

def find_resource(filenames):
    """find first existing resource from list of filenames"""
    if isinstance(filenames, str):
        filenames = [filenames]

    def get_resource_path(filename):
        if hasattr(sys, '_MEIPASS'):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent if '__file__' in globals() else Path.cwd()
        return str(base_path / filename)

    for filename in filenames:
        path = get_resource_path(filename)
        if os.path.exists(path):
            return path
    return None

class GreyCone:
    """grey cone with axis display and various behaviors"""
    def __init__(self, position):
        self.position = list(position)
        self.velocity = [0, 0, 0]
        self.state = random.choice(['still', 'moving', 'falling'])

        if self.state == 'moving':
            self.velocity = [
                random.uniform(-10, 10),
                random.uniform(-10, 10),
                random.uniform(-10, 10)
            ]
        elif self.state == 'falling':
            self.velocity = [0, -random.uniform(5, 15), 0]

        self.size = random.uniform(0.3, 3.0)
        self.rotation = random.uniform(0, 360)

    def update(self, dt):
        if self.state != 'still':
            self.position[0] += self.velocity[0] * dt
            self.position[1] += self.velocity[1] * dt
            self.position[2] += self.velocity[2] * dt

            if self.state == 'falling':
                self.velocity[1] -= 80.0 * dt

    def draw(self):
        glPushMatrix()
        glTranslatef(*self.position)
        glRotatef(self.rotation, 0, 1, 0)

        glColor3f(0.5, 0.5, 0.5)
        glRotatef(-90, 1, 0, 0)

        quadric = gluNewQuadric()
        if quadric:
            gluCylinder(quadric, self.size * 0.1, 0.0, self.size * 0.3, 16, 4)
            gluDeleteQuadric(quadric)

        glPopMatrix()

        # axis lines (x/y/z)
        axis_length = self.size * 1.5
        glLineWidth(2.0)

        glBegin(GL_LINES)
        glColor3f(0.8, 0.2, 0.2)
        glVertex3f(self.position[0], self.position[1], self.position[2])
        glVertex3f(self.position[0] + axis_length, self.position[1], self.position[2])

        glColor3f(0.2, 0.8, 0.2)
        glVertex3f(self.position[0], self.position[1], self.position[2])
        glVertex3f(self.position[0], self.position[1] + axis_length, self.position[2])

        glColor3f(0.2, 0.2, 0.8)
        glVertex3f(self.position[0], self.position[1], self.position[2])
        glVertex3f(self.position[0], self.position[1], self.position[2] + axis_length)
        glEnd()

        glLineWidth(1.0)

class ConeScene:
    def __init__(self, sound_manager=None, display_scale=1.0):
        import platform
        self.is_linux = platform.system() == "Linux"

        self.sound_manager = sound_manager
        self.display_scale = display_scale

        # grid settings - fixed for consistent world space
        self.grid_count = 15
        self.grid_spacing = 500.0
        self.grid_texture = None
        self.texture_scale = 10.0

        self.fog_color = [0.0, 0.0, 0.0, 1.0]
        self.fog_start = 10.0
        self.fog_end = 700.0

        self.camera_pos = [-62.78, 28.76, -38.61]
        self.camera_rotation = [17.48, 117.90, 8.88]

        # friend_join sound system
        self.friend_join_timer = 0.0
        self.friend_join_active = True
        self.friend_join_max_duration = 8.0
        self.friend_join_next_play = random.uniform(1.0, 1.5)
        self.friend_join_sound_duration = 0.0

        # get sound duration if available
        if self.sound_manager:
            self.friend_join_sound_duration = self.sound_manager.get_sound_duration('cube_click')
            if self.friend_join_sound_duration == 0:
                self.friend_join_sound_duration = 1.0

        # position initial target in camera view
        yaw_rad = math.radians(117.90)
        pitch_rad = math.radians(17.48)

        distance = 50.0
        target_x = self.camera_pos[0] + math.sin(yaw_rad) * math.cos(pitch_rad) * distance + 10
        target_y = self.camera_pos[1] - 30
        target_z = self.camera_pos[2] - math.cos(yaw_rad) * math.cos(pitch_rad) * distance + 10

        self.target_position = [target_x, target_y, target_z]

        # trace direction
        dx = random.uniform(-1, 1)
        dy = random.uniform(-1, 1)
        dz = random.uniform(-1, 1)
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length > 0:
            self.trace_direction = [dx/length, dy/length, dz/length]
        else:
            self.trace_direction = [0, 1, 0]
        self.trace_length = random.uniform(800, 1500)

        # blue box near target
        box_distance = random.uniform(20, 100)
        box_angle_h = random.uniform(0, 360)
        box_angle_v = random.uniform(-45, 45)

        box_angle_h_rad = math.radians(box_angle_h)
        box_angle_v_rad = math.radians(box_angle_v)

        self.box_position = [
            self.target_position[0] + math.cos(box_angle_h_rad) * math.cos(box_angle_v_rad) * box_distance,
            self.target_position[1] + math.sin(box_angle_v_rad) * box_distance,
            self.target_position[2] + math.sin(box_angle_h_rad) * math.cos(box_angle_v_rad) * box_distance
        ]

        self.box_size = [
            random.uniform(2, 25),
            random.uniform(2, 25),
            random.uniform(2, 25)
        ]

        self.grey_cones = []
        self.generate_grey_cones()

        # triangle interaction
        self.triangle_hovered = False
        self.triangle_scale = 1.0
        self.triangle_target_scale = 1.0
        self.triangle_hover_amount = 0.2

        # target switching
        self.target_timer = 0.0
        self.target_switch_interval = random.uniform(0.5, 1.5)
        self.first_teleport_done = False

        # startup timer - slow down after 9 seconds
        self.startup_timer = 0.0
        self.startup_duration = 9.0
        self.startup_complete = False

        # cone flashing
        self.cone_flash_timer = 0.0
        self.cone_flash_interval = random.uniform(0.3, 0.6)
        self.cone_visible = True

        # camera movement
        self.camera_distance = 80.0
        self.strafe_speed = 5.0
        self.initial_speed = 5.0
        self.slow_speed = 0.8

        # loading text effect
        self.loading_timer = 0.0
        self.loading_duration = 5.0
        self.loading_flash_timer = 0.0
        self.loading_flash_intervals = [0.01, 0.05, 0.09]
        self.loading_flash_index = 0
        self.loading_text_visible = True
        self.loading_effect_active = True
        self.stored_coords = [0, 0, 0]
        self.coords_initialized = False

        # white dot random movement
        self.dot_check_timer = 0.0
        self.dot_check_interval = 0.05
        self.dot_offset = [0, 0, 0]
        self.dot_movement_direction = [0, 0, 0]
        self.dot_is_moving = False
        self.dot_move_distance = 0.0
        self.dot_max_distance = 0.0
        self.dot_move_speed = 50.0
        self.generate_dot_direction()

        # coordinate display system
        self.metal_reg_phrases = ["PLAT", "SETREG", "CPU_POP", "NAN_CREG", "STOPREG_DIRTY", "WAIT", "THINK", "CPU_PUSH"]
        self.metal_reg_index = 0
        self.metal_reg_timer = 0.0
        self.metal_reg_intervals = [0.01, 0.03, 0.09]
        self.metal_reg_interval_index = 0

        try:
            # use find_resource to locate fonts
            cabin_font_path = find_resource([
                'assets/fonts/Cabin-Regular.ttf',
                'fonts/Cabin-Regular.ttf',
                'Cabin-Regular.ttf'
            ])

            if cabin_font_path:
                # this is closest font i could find unless anomi provides font name for it.
                self.coord_font = pygame.font.Font(cabin_font_path, 18)
                self.coord_font_small = pygame.font.Font(cabin_font_path, 16)
                self.coord_font_reg_small = pygame.font.Font(cabin_font_path, 12)
                self.loading_font = pygame.font.SysFont('trebuchetms', 20, bold=True)
            else:
                # fallback if font not found
                raise FileNotFoundError("Cabin font not found")

        except Exception as e:
            # fallback to default fonts
            print(f"Font loading failed: {e}, using defaults")
            self.coord_font = pygame.font.Font(None, 18)
            self.coord_font_small = pygame.font.Font(None, 16)
            self.coord_font_reg_small = pygame.font.Font(None, 12)
            self.loading_font = pygame.font.Font(None, 20)

        self.load_grid_texture()

    def generate_grey_cones(self):
        self.grey_cones = []
        num_cones = random.randint(5, 15)

        for _ in range(num_cones):
            position = [
                random.uniform(-400, 400),
                random.uniform(-100, 200),
                random.uniform(-400, 400)
            ]
            self.grey_cones.append(GreyCone(position))

    def generate_dot_direction(self):
        direction = [
            random.uniform(-1, 1),
            random.uniform(-1, 1),
            random.uniform(-1, 1)
        ]
        length = math.sqrt(direction[0]**2 + direction[1]**2 + direction[2]**2)
        if length > 0:
            self.dot_movement_direction = [d / length for d in direction]
        else:
            self.dot_movement_direction = [0, 1, 0]

    def check_triangle_hover(self, mouse_pos, display_width, display_height):
        """check if mouse is over the cyan triangle"""
        center_x = display_width * 0.85
        center_y = display_height * 0.60
        size = 50 * 0.5

        dx = mouse_pos[0] - center_x
        dy = mouse_pos[1] - center_y
        distance = math.sqrt(dx*dx + dy*dy)

        if distance < size * 2.0:
            if not self.triangle_hovered:
                if self.sound_manager:
                    self.sound_manager.play_sound('hover')
            self.triangle_hovered = True
            self.triangle_target_scale = 1.0 + self.triangle_hover_amount
        else:
            self.triangle_hovered = False
            self.triangle_target_scale = 1.0

    def check_triangle_click(self, mouse_pos, display_width, display_height):
        """check if triangle was clicked, returns True if should return to main"""
        center_x = display_width * 0.85
        center_y = display_height * 0.60
        size = 50 * 0.5 * self.triangle_scale

        dx = mouse_pos[0] - center_x
        dy = mouse_pos[1] - center_y
        distance = math.sqrt(dx*dx + dy*dy)

        if distance < size * 2.0:
            return True
        return False

    def draw_cyan_triangle_sprite(self, display_width, display_height):
        # 2d rendering setup
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # change color when hovered
        if self.triangle_hovered:
            glColor4f(1.0, 0.0, 0.0, 1.0)  # red when hovered
        else:
            glColor4f(0.0, 1.0, 1.0, 1.0)  # cyan normally

        center_x = display_width * 0.85
        center_y = display_height * 0.60
        size = 50 * 0.5 * self.triangle_scale  # apply scale

        # rotate slightly left
        glTranslatef(center_x, center_y, 0)
        glRotatef(10, 0, 0, 1)
        glTranslatef(-center_x, -center_y, 0)

        glBegin(GL_TRIANGLES)
        glVertex2f(center_x, center_y + size)
        glVertex2f(center_x - size, center_y - size)
        glVertex2f(center_x + size, center_y - size)
        glEnd()

        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def draw_loading_text(self, display_width, display_height):
        text_surface = self.loading_font.render("NG CONNECTION...", True, (150, 0, 0))
        text_data = pygame.image.tostring(text_surface, "RGBA", False)
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)

        text_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, text_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_width, text_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)

        x_pos = -12
        y_pos = display_height // 2 - text_height // 2

        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x_pos, y_pos)
        glTexCoord2f(1, 0); glVertex2f(x_pos + text_width, y_pos)
        glTexCoord2f(1, 1); glVertex2f(x_pos + text_width, y_pos + text_height)
        glTexCoord2f(0, 1); glVertex2f(x_pos, y_pos + text_height)
        glEnd()

        glDeleteTextures([text_texture])
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def draw_coordinate_display(self, display_width, display_height):
        if self.loading_effect_active:
            return

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)

        y_pos = 10

        # located text - yellow, spaced
        located_text = "L  O  C  A  T  E  D   W  F  A  3  Y  -  A   [  I  N  T  E  R  L  O  P  E  .  D  M  E  ]"
        text_surface = self.coord_font.render(located_text, True, (255, 255, 0))
        self.render_text_texture(text_surface, 10, y_pos)
        y_pos += 25

        # validators text - yellow, cut off at edge
        validators_text = "V A L I D A T O R S   H A V E   N O T   B E E N   V E R I F I E D,   P L E A S E"
        text_surface = self.coord_font.render(validators_text, True, (255, 255, 0))
        self.render_text_texture(text_surface, 10, y_pos)
        y_pos += 23

        # coordinates - scale from dot position
        dot_pos = [
            self.target_position[0] + self.dot_offset[0],
            self.target_position[1] + self.dot_offset[1],
            self.target_position[2] + self.dot_offset[2]
        ]

        scale_factor = 15000.0
        base_offset = 50000.0

        # coordinates
        if not self.coords_initialized:
            self.update_stored_coords()
            self.coords_initialized = True

        scaled_x = self.stored_coords[0]
        scaled_y = self.stored_coords[1]
        scaled_z = self.stored_coords[2]

        def format_coord(value, decimals=3):
            int_part = int(value)
            dec_part = value - int_part

            int_str = f"{int_part:,}"

            if decimals > 0:
                dec_str = f"{dec_part:.{decimals}f}"[1:]
                full_str = int_str + dec_str
            else:
                full_str = int_str

            spaced_str = '       '.join(full_str)

            return spaced_str

        try:
            cabin_font_path = find_resource([
                'assets/fonts/Cabin-Regular.ttf',
                'fonts/Cabin-Regular.ttf'
            ])

            if cabin_font_path:
                coord_number_font = pygame.font.Font(cabin_font_path, 23)
            else:
                coord_number_font = pygame.font.Font(None, 23)
        except Exception as e:
            coord_number_font = pygame.font.Font(None, 23)

        x_pos_start = 20

        # x coordinate
        x_label_surface = self.coord_font.render("X", True, (255, 255, 0))
        self.render_text_texture(x_label_surface, x_pos_start, y_pos)
        x_num_surface = coord_number_font.render(format_coord(scaled_x, 3), True, (255, 0, 0))
        self.render_text_texture(x_num_surface, x_pos_start + x_label_surface.get_width() + 5, y_pos - 2)
        y_pos += 25

        # y coordinate
        y_label_surface = self.coord_font.render("Y", True, (255, 255, 0))
        self.render_text_texture(y_label_surface, x_pos_start, y_pos)
        y_num_surface = coord_number_font.render(format_coord(scaled_y, 2), True, (255, 0, 0))
        self.render_text_texture(y_num_surface, x_pos_start + y_label_surface.get_width() + 5, y_pos - 2)
        y_pos += 25

        # z coordinate
        z_label_surface = self.coord_font.render("Z", True, (255, 255, 0))
        self.render_text_texture(z_label_surface, x_pos_start, y_pos)
        z_num_surface = coord_number_font.render(format_coord(scaled_z, 2), True, (255, 0, 0))
        self.render_text_texture(z_num_surface, x_pos_start + z_label_surface.get_width() + 5, y_pos - 2)
        y_pos += 28

        # metal_reg phrase cycling
        current_phrase = self.metal_reg_phrases[self.metal_reg_index]
        metal_label_surface = self.coord_font_small.render("METAL_REG-", True, (255, 255, 0))
        self.render_text_texture(metal_label_surface, 10, y_pos)
        metal_phrase_surface = self.coord_font_reg_small.render(current_phrase, True, (255, 140, 0))
        self.render_text_texture(metal_phrase_surface, 10 + metal_label_surface.get_width(), y_pos + 2.5)

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def render_text_texture(self, text_surface, x, y):
        text_data = pygame.image.tostring(text_surface, "RGBA", False)
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()

        text_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, text_texture)

        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_width, text_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        glGenerateMipmap(GL_TEXTURE_2D)

        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + text_width, y)
        glTexCoord2f(1, 1); glVertex2f(x + text_width, y + text_height)
        glTexCoord2f(0, 1); glVertex2f(x, y + text_height)
        glEnd()

        glDeleteTextures([text_texture])

    def draw_black_screen(self, display_width, display_height):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

        glColor3f(0.0, 0.0, 0.0)
        glBegin(GL_QUADS)
        glVertex2f(0, 0)
        glVertex2f(display_width, 0)
        glVertex2f(display_width, display_height)
        glVertex2f(0, display_height)
        glEnd()

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def draw_skybox_sprite(self, display_width, display_height):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glDisable(GL_FOG)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        scale = 2.0
        checker_width = 80 * scale
        checker_height = 60 * scale
        cols = int(display_width / checker_width) + 2
        rows = int(display_height / checker_height) + 2

        color1 = [0.04, 0.01, 0.04, 0.6]
        color2 = [0.01, 0.01, 0.01, 0.6]

        glBegin(GL_QUADS)
        for i in range(rows):
            for j in range(cols):
                checker = (i + j) % 2
                color = color1 if checker else color2
                glColor4f(*color)

                x = j * checker_width
                y = i * checker_height

                glVertex2f(x, y)
                glVertex2f(x + checker_width, y)
                glVertex2f(x + checker_width, y + checker_height)
                glVertex2f(x, y + checker_height)
        glEnd()

        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_FOG)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def load_grid_texture(self):
        try:
            texture_candidates = [
                'img/grid.png',
                'assets/images/grid.png',
                'grid.png'
            ]
            texture_path = find_resource(texture_candidates)

            if texture_path:
                try:
                    grid_img = pygame.image.load(texture_path).convert_alpha()

                    width = grid_img.get_width()
                    height = grid_img.get_height()

                    # make black pixels transparent
                    for x in range(width):
                        for y in range(height):
                            r, g, b, a = grid_img.get_at((x, y))
                            if r == 0 and g == 0 and b == 0:
                                grid_img.set_at((x, y), (0, 0, 0, 0))

                    grid_data = pygame.image.tostring(grid_img, "RGBA", True)

                    self.grid_texture = glGenTextures(1)
                    glBindTexture(GL_TEXTURE_2D, self.grid_texture)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, grid_data)
                except Exception as e:
                    self.grid_texture = None
            else:
                self.grid_texture = None
        except Exception as e:
            self.grid_texture = None

    def generate_random_target(self):
        self.target_position = [
            random.uniform(-500, 500),
            random.uniform(-200, 200),
            random.uniform(-500, 500)
        ]

        dx = random.uniform(-1, 1)
        dy = random.uniform(-1, 1)
        dz = random.uniform(-1, 1)

        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length > 0:
            self.trace_direction = [dx/length, dy/length, dz/length]
        else:
            self.trace_direction = [0, 1, 0]

        self.trace_length = random.uniform(800, 1500)

        # position blue box near target
        box_distance = random.uniform(20, 100)
        box_angle_h = random.uniform(0, 360)
        box_angle_v = random.uniform(-45, 45)

        box_angle_h_rad = math.radians(box_angle_h)
        box_angle_v_rad = math.radians(box_angle_v)

        self.box_position = [
            self.target_position[0] + math.cos(box_angle_h_rad) * math.cos(box_angle_v_rad) * box_distance,
            self.target_position[1] + math.sin(box_angle_v_rad) * box_distance,
            self.target_position[2] + math.sin(box_angle_h_rad) * math.cos(box_angle_v_rad) * box_distance
        ]

        self.box_size = [
            random.uniform(2, 25),
            random.uniform(2, 25),
            random.uniform(2, 25)
        ]

        self.generate_grey_cones()

        self.generate_dot_direction()
        self.dot_offset = [0, 0, 0]
        self.dot_is_moving = False
        self.dot_move_distance = 0.0
        self.update_stored_coords()

    def update_stored_coords(self):
        """update and store coordinates on teleport"""
        dot_pos = [
            self.target_position[0] + self.dot_offset[0],
            self.target_position[1] + self.dot_offset[1],
            self.target_position[2] + self.dot_offset[2]
        ]

        scale_factor = 15000.0
        base_offset = 50000.0

        self.stored_coords = [
            abs(dot_pos[0] * scale_factor) + base_offset,
            abs(dot_pos[1] * scale_factor) + base_offset * 2,
            abs(dot_pos[2] * scale_factor) + base_offset * 1.5
        ]

    def create_display_list(self):
        pass

    def teleport_to_target(self):
        roll = random.uniform(-15, 15)

        angle_around = random.uniform(0, 360)
        angle_around_rad = math.radians(angle_around)

        offset_x = math.sin(angle_around_rad) * self.camera_distance
        offset_z = math.cos(angle_around_rad) * self.camera_distance

        self.camera_pos[0] = self.target_position[0] + offset_x
        self.camera_pos[1] = self.target_position[1]
        self.camera_pos[2] = self.target_position[2] + offset_z

        # calculate rotation to look at target
        dx = self.target_position[0] - self.camera_pos[0]
        dy = self.target_position[1] - self.camera_pos[1]
        dz = self.target_position[2] - self.camera_pos[2]

        yaw = math.degrees(math.atan2(dx, -dz))
        horizontal_dist = math.sqrt(dx*dx + dz*dz)
        pitch = math.degrees(math.atan2(dy, horizontal_dist))

        self.camera_rotation = [pitch, yaw, roll]

    def update_camera_tracking(self):
        dx = self.target_position[0] - self.camera_pos[0]
        dy = self.target_position[1] - self.camera_pos[1]
        dz = self.target_position[2] - self.camera_pos[2]

        distance = math.sqrt(dx*dx + dy*dy + dz*dz)

        if distance > 0.01:
            yaw = math.degrees(math.atan2(dx, -dz))
            horizontal_dist = math.sqrt(dx*dx + dz*dz)
            pitch = math.degrees(math.atan2(dy, horizontal_dist))

            self.camera_rotation[0] = pitch
            self.camera_rotation[1] = yaw

    def handle_event(self, event):
        pass

    def update(self, dt):
        # friend_join random sound
        if self.friend_join_active and self.sound_manager:
            self.friend_join_timer += dt

            if self.friend_join_timer >= self.friend_join_max_duration:
                self.friend_join_active = False
            elif self.friend_join_timer >= self.friend_join_next_play:
                self.sound_manager.play_sound('cube_click')
                delay = random.uniform(3.0, 5.0)
                self.friend_join_next_play = self.friend_join_timer + self.friend_join_sound_duration + delay


        # loading effect
        if self.loading_effect_active:
            self.loading_timer += dt
            if self.loading_timer >= self.loading_duration:
                self.loading_effect_active = False
                if not self.coords_initialized:
                    self.update_stored_coords()
                    self.coords_initialized = True
            else:
                self.loading_flash_timer += dt
                current_interval = self.loading_flash_intervals[self.loading_flash_index]
                if self.loading_flash_timer >= current_interval:
                    self.loading_flash_timer = 0.0
                    self.loading_text_visible = not self.loading_text_visible
                    self.loading_flash_index = (self.loading_flash_index + 1) % len(self.loading_flash_intervals)

        # white dot movement - snap back when reaching max distance
        if self.dot_is_moving:
            move_amount = self.dot_move_speed * dt
            self.dot_offset[0] += self.dot_movement_direction[0] * move_amount
            self.dot_offset[1] += self.dot_movement_direction[1] * move_amount
            self.dot_offset[2] += self.dot_movement_direction[2] * move_amount
            self.dot_move_distance += move_amount

            if self.dot_move_distance >= self.dot_max_distance:
                self.dot_offset = [0, 0, 0]
                self.dot_is_moving = False
                self.dot_move_distance = 0.0
        else:
            self.dot_check_timer += dt
            if self.dot_check_timer >= self.dot_check_interval:
                self.dot_check_timer = 0.0

                action_roll = random.random()

                if action_roll < 0.015:
                    self.dot_is_moving = True
                    self.dot_move_distance = 0.0
                    self.dot_max_distance = random.uniform(2, 15)
                    self.dot_offset = [0, 0, 0]

        # metal_reg phrase cycling
        if not self.loading_effect_active:
            self.metal_reg_timer += dt
            current_interval = self.metal_reg_intervals[self.metal_reg_interval_index]
            if self.metal_reg_timer >= current_interval:
                self.metal_reg_timer = 0.0
                self.metal_reg_index = (self.metal_reg_index + 1) % len(self.metal_reg_phrases)
                self.metal_reg_interval_index = (self.metal_reg_interval_index + 1) % len(self.metal_reg_intervals)

        # startup timer - slow down after duration
        if not self.startup_complete:
            self.startup_timer += dt
            if self.startup_timer >= self.startup_duration:
                self.startup_complete = True
                self.strafe_speed = self.slow_speed

        # cone flashing
        self.cone_flash_timer += dt
        if self.cone_flash_timer >= self.cone_flash_interval:
            self.cone_flash_timer = 0.0
            self.cone_flash_interval = random.uniform(0.3, 0.6)
            self.cone_visible = not self.cone_visible

        for cone in self.grey_cones:
            cone.update(dt)

        # target switching
        self.target_timer += dt
        if self.target_timer >= self.target_switch_interval:
            self.target_timer = 0.0
            self.target_switch_interval = random.uniform(1.5, 2.5)

            self.generate_random_target()
            self.teleport_to_target()
            self.first_teleport_done = True

        # strafe camera sideways
        yaw_rad = math.radians(self.camera_rotation[1])
        right_x = math.cos(yaw_rad)
        right_z = math.sin(yaw_rad)

        self.camera_pos[0] += right_x * self.strafe_speed * dt
        self.camera_pos[2] += right_z * self.strafe_speed * dt

        if self.first_teleport_done:
            self.update_camera_tracking()

    def draw_grey_cones(self):
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)

        for cone in self.grey_cones:
            cone.draw()

        glDisable(GL_LIGHTING)

    def draw_blue_box_and_line(self):
        glDisable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        dot_pos = [
            self.target_position[0] + self.dot_offset[0],
            self.target_position[1] + self.dot_offset[1],
            self.target_position[2] + self.dot_offset[2]
        ]

        # line from dot to box
        glColor4f(0.0, 0.1, 0.6, 0.4)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex3f(*dot_pos)
        glVertex3f(*self.box_position)
        glEnd()
        glLineWidth(1.0)

        # blue box
        glPushMatrix()
        glTranslatef(*self.box_position)

        glColor4f(0.0, 0.15, 0.7, 0.3)

        half_w = self.box_size[0] / 2.0
        half_h = self.box_size[1] / 2.0
        half_d = self.box_size[2] / 2.0

        glBegin(GL_QUADS)
        # front
        glVertex3f(-half_w, -half_h, half_d)
        glVertex3f(half_w, -half_h, half_d)
        glVertex3f(half_w, half_h, half_d)
        glVertex3f(-half_w, half_h, half_d)

        # back
        glVertex3f(half_w, -half_h, -half_d)
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(-half_w, half_h, -half_d)
        glVertex3f(half_w, half_h, -half_d)

        # top
        glVertex3f(-half_w, half_h, half_d)
        glVertex3f(half_w, half_h, half_d)
        glVertex3f(half_w, half_h, -half_d)
        glVertex3f(-half_w, half_h, -half_d)

        # bottom
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(half_w, -half_h, -half_d)
        glVertex3f(half_w, -half_h, half_d)
        glVertex3f(-half_w, -half_h, half_d)

        # right
        glVertex3f(half_w, -half_h, half_d)
        glVertex3f(half_w, -half_h, -half_d)
        glVertex3f(half_w, half_h, -half_d)
        glVertex3f(half_w, half_h, half_d)

        # left
        glVertex3f(-half_w, -half_h, -half_d)
        glVertex3f(-half_w, -half_h, half_d)
        glVertex3f(-half_w, half_h, half_d)
        glVertex3f(-half_w, half_h, -half_d)
        glEnd()

        glPopMatrix()

        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)

    def draw_target(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)

        dot_pos = [
            self.target_position[0] + self.dot_offset[0],
            self.target_position[1] + self.dot_offset[1],
            self.target_position[2] + self.dot_offset[2]
        ]

        # trace line from dot
        glPushMatrix()
        glTranslatef(*dot_pos)

        glColor3f(0.6, 0.3, 0.0)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(
            self.trace_direction[0] * self.trace_length,
            self.trace_direction[1] * self.trace_length,
            self.trace_direction[2] * self.trace_length
        )
        glEnd()
        glPopMatrix()

        # billboard sprites for dot and cone
        glPushMatrix()
        glTranslatef(*dot_pos)

        dx = self.camera_pos[0] - dot_pos[0]
        dy = self.camera_pos[1] - dot_pos[1]
        dz = self.camera_pos[2] - dot_pos[2]

        angle_y = math.degrees(math.atan2(dx, dz))
        horizontal_dist = math.sqrt(dx*dx + dz*dz)
        angle_x = -math.degrees(math.atan2(dy, horizontal_dist))

        glRotatef(angle_y, 0, 1, 0)
        glRotatef(angle_x, 1, 0, 0)

        # white dot
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, 0)
        segments = 12
        for i in range(segments + 1):
            angle = (i / segments) * 2.0 * math.pi
            x = 0.15 * math.cos(angle)
            y = 0.15 * math.sin(angle)
            glVertex3f(x, y, 0)
        glEnd()

        # red cone with circular base
        if self.cone_visible:
            glTranslatef(0, 5.0, 0)
            glColor3f(1.0, 0.0, 0.0)

            glBegin(GL_TRIANGLES)
            glVertex3f(0, -3, 0)
            glVertex3f(-1.3, 0, 0)
            glVertex3f(1.3, 0, 0)
            glEnd()

            glBegin(GL_TRIANGLE_FAN)
            glVertex3f(0, 0, 0)
            segments = 16
            radius = 1.3
            for i in range(segments + 1):
                angle = (i / segments) * 2.0 * math.pi
                x = radius * math.cos(angle)
                y = 0
                glVertex3f(x, y, 0)
            glEnd()

        glPopMatrix()

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def draw_optimized_grids(self):
        """platform-specific grid rendering because grid on linux doesn't work for some reason"""
        if self.is_linux:
            self.draw_optimized_grids_linux()
        else:
            self.draw_optimized_grids_windows()

    def draw_optimized_grids_windows(self):
        half_count = self.grid_count // 2
        spacing = self.grid_spacing
        tex_scale = self.texture_scale
        plane_size = self.grid_count * spacing
        half_plane = plane_size / 2.0
        max_dist = self.fog_end * 1.5

        planes = []

        for i in range(-half_count, half_count + 1):
            z_pos = i * spacing
            if abs(z_pos - self.camera_pos[2]) < max_dist:
                planes.append(('xy', z_pos, abs(z_pos - self.camera_pos[2])))

        for i in range(-half_count, half_count + 1):
            y_pos = i * spacing
            if abs(y_pos - self.camera_pos[1]) < max_dist:
                planes.append(('xz', y_pos, abs(y_pos - self.camera_pos[1])))

        for i in range(-half_count, half_count + 1):
            x_pos = i * spacing
            if abs(x_pos - self.camera_pos[0]) < max_dist:
                planes.append(('yz', x_pos, abs(x_pos - self.camera_pos[0])))

        planes.sort(key=lambda p: p[2], reverse=True)

        if self.grid_texture:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.grid_texture)
            glColor4f(1.0, 1.0, 1.0, 1.0)
        else:
            glColor4f(1.0, 1.0, 1.0, 0.4)

        glBegin(GL_QUADS)
        for plane_type, pos, dist in planes:
            if plane_type == 'xy':
                glNormal3f(0, 0, 1)
                glTexCoord2f(0, 0); glVertex3f(-half_plane, -half_plane, pos)
                glTexCoord2f(tex_scale, 0); glVertex3f(half_plane, -half_plane, pos)
                glTexCoord2f(tex_scale, tex_scale); glVertex3f(half_plane, half_plane, pos)
                glTexCoord2f(0, tex_scale); glVertex3f(-half_plane, half_plane, pos)
            elif plane_type == 'xz':
                glNormal3f(0, 1, 0)
                glTexCoord2f(0, 0); glVertex3f(-half_plane, pos, -half_plane)
                glTexCoord2f(tex_scale, 0); glVertex3f(half_plane, pos, -half_plane)
                glTexCoord2f(tex_scale, tex_scale); glVertex3f(half_plane, pos, half_plane)
                glTexCoord2f(0, tex_scale); glVertex3f(-half_plane, pos, half_plane)
            elif plane_type == 'yz':
                glNormal3f(1, 0, 0)
                glTexCoord2f(0, 0); glVertex3f(pos, -half_plane, -half_plane)
                glTexCoord2f(tex_scale, 0); glVertex3f(pos, half_plane, -half_plane)
                glTexCoord2f(tex_scale, tex_scale); glVertex3f(pos, half_plane, half_plane)
                glTexCoord2f(0, tex_scale); glVertex3f(pos, -half_plane, half_plane)
        glEnd()

        if self.grid_texture:
            glDisable(GL_TEXTURE_2D)

    def draw_optimized_grids_linux(self):
        half_count = self.grid_count // 2
        spacing = self.grid_spacing
        tex_scale = self.texture_scale
        plane_size = self.grid_count * spacing
        half_plane = plane_size / 2.0
        max_dist = self.fog_end * 1.5

        planes = []

        for i in range(-half_count, half_count + 1):
            z_pos = i * spacing
            if abs(z_pos - self.camera_pos[2]) < max_dist:
                planes.append(('xy', z_pos, abs(z_pos - self.camera_pos[2])))

        for i in range(-half_count, half_count + 1):
            y_pos = i * spacing
            if abs(y_pos - self.camera_pos[1]) < max_dist:
                planes.append(('xz', y_pos, abs(y_pos - self.camera_pos[1])))

        for i in range(-half_count, half_count + 1):
            x_pos = i * spacing
            if abs(x_pos - self.camera_pos[0]) < max_dist:
                planes.append(('yz', x_pos, abs(x_pos - self.camera_pos[0])))

        planes.sort(key=lambda p: p[2], reverse=True)

        glDisable(GL_FOG)
        glDisable(GL_LIGHTING)

        if self.grid_texture:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.grid_texture)
            glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

        subdivisions = 8
        step = plane_size / subdivisions

        for plane_type, pos, plane_dist in planes:
            for i in range(subdivisions):
                for j in range(subdivisions):
                    x0 = -half_plane + i * step
                    x1 = -half_plane + (i + 1) * step
                    y0 = -half_plane + j * step
                    y1 = -half_plane + (j + 1) * step

                    u0 = (i / subdivisions) * tex_scale
                    u1 = ((i + 1) / subdivisions) * tex_scale
                    v0 = (j / subdivisions) * tex_scale
                    v1 = ((j + 1) / subdivisions) * tex_scale

                    if plane_type == 'xy':
                        center_x = (x0 + x1) / 2
                        center_y = (y0 + y1) / 2
                        center_z = pos
                    elif plane_type == 'xz':
                        center_x = (x0 + x1) / 2
                        center_y = pos
                        center_z = (y0 + y1) / 2
                    elif plane_type == 'yz':
                        center_x = pos
                        center_y = (x0 + x1) / 2
                        center_z = (y0 + y1) / 2

                    dx = center_x - self.camera_pos[0]
                    dy = center_y - self.camera_pos[1]
                    dz = center_z - self.camera_pos[2]
                    dist = math.sqrt(dx*dx + dy*dy + dz*dz)

                    if dist <= self.fog_start:
                        alpha = 1.0
                    elif dist >= self.fog_end:
                        continue
                    else:
                        t = (dist - self.fog_start) / (self.fog_end - self.fog_start)
                        alpha = 1.0 - t

                    if alpha < 0.01:
                        continue

                    glColor4f(1.0, 1.0, 1.0, alpha)

                    glBegin(GL_QUADS)
                    if plane_type == 'xy':
                        glNormal3f(0, 0, 1)
                        glTexCoord2f(u0, v0); glVertex3f(x0, y0, pos)
                        glTexCoord2f(u1, v0); glVertex3f(x1, y0, pos)
                        glTexCoord2f(u1, v1); glVertex3f(x1, y1, pos)
                        glTexCoord2f(u0, v1); glVertex3f(x0, y1, pos)
                    elif plane_type == 'xz':
                        glNormal3f(0, 1, 0)
                        glTexCoord2f(u0, v0); glVertex3f(x0, pos, y0)
                        glTexCoord2f(u1, v0); glVertex3f(x1, pos, y0)
                        glTexCoord2f(u1, v1); glVertex3f(x1, pos, y1)
                        glTexCoord2f(u0, v1); glVertex3f(x0, pos, y1)
                    elif plane_type == 'yz':
                        glNormal3f(1, 0, 0)
                        glTexCoord2f(u0, v0); glVertex3f(pos, x0, y0)
                        glTexCoord2f(u1, v0); glVertex3f(pos, x1, y0)
                        glTexCoord2f(u1, v1); glVertex3f(pos, x1, y1)
                        glTexCoord2f(u0, v1); glVertex3f(pos, x0, y1)
                    glEnd()

        if self.grid_texture:
            glDisable(GL_TEXTURE_2D)

        glEnable(GL_FOG)
        glEnable(GL_LIGHTING)

    def draw(self, display_width, display_height):
        # loading screen or normal scene
        if self.loading_effect_active and self.loading_text_visible:
            self.draw_black_screen(display_width, display_height)
            self.draw_loading_text(display_width, display_height)
        else:
            glClearColor(*self.fog_color)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glEnable(GL_FOG)
            glFogi(GL_FOG_MODE, GL_LINEAR)
            glFogfv(GL_FOG_COLOR, self.fog_color)
            glFogf(GL_FOG_START, self.fog_start)
            glFogf(GL_FOG_END, self.fog_end)
            glHint(GL_FOG_HINT, GL_NICEST)

            self.draw_skybox_sprite(display_width, display_height)

            # 3d perspective
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            aspect_ratio = display_width / display_height
            gluPerspective(70.0, aspect_ratio, 1.0, 30000.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            # camera transform
            glRotatef(self.camera_rotation[0], 1, 0, 0)
            glRotatef(self.camera_rotation[1], 0, 1, 0)
            glRotatef(self.camera_rotation[2], 0, 0, 1)

            glTranslatef(-self.camera_pos[0], -self.camera_pos[1], -self.camera_pos[2])

            # grids with transparency
            glDisable(GL_LIGHTING)
            glDisable(GL_CULL_FACE)
            glEnable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            self.draw_optimized_grids()

            glDepthMask(GL_TRUE)

            self.draw_grey_cones()
            self.draw_blue_box_and_line()
            self.draw_target()
            self.draw_cyan_triangle_sprite(display_width, display_height)
            self.draw_coordinate_display(display_width, display_height)

            glDisable(GL_FOG)
            glDisable(GL_BLEND)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_LIGHTING)

    def cleanup(self):
        if self.grid_texture:
            try:
                glDeleteTextures([self.grid_texture])
            except:
                pass
            self.grid_texture = None
