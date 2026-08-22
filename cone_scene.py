import math
import random

from rendering_helpers import PIL_AVAILABLE
from sourcebox.resources import find_resource
from sourcebox.runtime import pygame_font_available
from sourcebox.scenes.cone_entities import GreyCone
from sourcebox.scenes.cone_renderer import ConeRendererMixin

class ConeScene(ConeRendererMixin):
    def __init__(self, sound_manager=None, display_scale=1.0):
        import platform
        self.is_linux = platform.system() == "Linux"

        self.sound_manager = sound_manager
        self._cabin_font_path = find_resource(
            [
                "assets/fonts/Cabin-Regular.ttf",
                "fonts/Cabin-Regular.ttf",
                "Cabin-Regular.ttf",
            ]
        )
        self._text_backend = None
        self._font_cache = {}

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

        # pink triangles floating in the void
        self.pink_triangles = []
        self.generate_pink_triangles()

        # rare red object (small chance of appearing)
        self.red_object_visible = random.random() < 0.15
        self.red_object_position = [
            random.uniform(-300, 300),
            random.uniform(-50, 150),
            random.uniform(-300, 300)
        ]
        self.red_object_rotation = random.uniform(0, 360)
        self.red_object_pulse_timer = 0.0

        # triangle interaction
        self.triangle_flash_red = False
        self.triangle_hovered = False
        self.triangle_scale = 1.0

        # target switching
        self.target_timer = 0.0
        # Give the opening view a brief, consistent hold.
        self.target_switch_interval = 1.0

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

        if pygame_font_available():
            self._text_backend = "pygame"
        elif PIL_AVAILABLE:
            self._text_backend = "pillow"
            print("pygame.font not available; using Pillow for text rendering")
        else:
            self._text_backend = None
            print("Text rendering disabled: pygame.font and Pillow are unavailable")

        self.load_grid_texture()

    @staticmethod
    def _next_teleport_interval():
        """Mix abrupt cuts with occasional multi-second holds."""
        if random.random() < 0.02:
            return random.uniform(0.08, 0.4)
        return random.uniform(0.7, 4.0)




    def generate_grey_cones(self):
        self.grey_cones = []
        num_cones = random.randint(8, 20)

        for _ in range(num_cones):
            position = [
                random.uniform(-400, 400),
                random.uniform(-100, 200),
                random.uniform(-400, 400)
            ]
            self.grey_cones.append(GreyCone(position))

    def generate_pink_triangles(self):
        self.pink_triangles = []
        # rare — 20% chance of appearing
        if random.random() > 0.20:
            return
        # spawn near camera
        yaw_rad = math.radians(self.camera_rotation[1])
        forward_x = math.sin(yaw_rad)
        forward_z = -math.cos(yaw_rad)
        dist = random.uniform(30, 60)
        pos = [
            self.camera_pos[0] + forward_x * dist + random.uniform(-20, 20),
            self.camera_pos[1] + random.uniform(-10, 10),
            self.camera_pos[2] + forward_z * dist + random.uniform(-20, 20)
        ]
        size = random.uniform(2.0, 4.0)
        dx = random.uniform(-1, 1)
        dy = random.uniform(-0.3, 0.3)
        dz = random.uniform(-1, 1)
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length > 0:
            speed = random.uniform(3.0, 6.0)
            vel = [dx/length * speed, dy/length * speed, dz/length * speed]
        else:
            vel = [3.0, 0, 0]
        self.pink_triangles.append({'pos': pos, 'size': size, 'vel': vel})

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
        else:
            self.triangle_hovered = False

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

    def center_target_horizontally(self):
        """Keep the target centered laterally without following vertical dot motion."""
        dx = self.target_position[0] - self.camera_pos[0]
        dz = self.target_position[2] - self.camera_pos[2]
        if abs(dx) > 0.01 or abs(dz) > 0.01:
            self.camera_rotation[1] = math.degrees(math.atan2(dx, -dz))

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

        # pink triangles drift
        for tri in self.pink_triangles:
            tri['pos'][0] += tri['vel'][0] * dt
            tri['pos'][1] += tri['vel'][1] * dt
            tri['pos'][2] += tri['vel'][2] * dt

        # red object pulse
        if self.red_object_visible:
            self.red_object_pulse_timer += dt

        # target switching
        self.target_timer += dt
        if self.target_timer >= self.target_switch_interval:
            self.target_timer = 0.0
            self.target_switch_interval = self._next_teleport_interval()

            self.generate_random_target()
            self.teleport_to_target()

        # strafe camera sideways
        yaw_rad = math.radians(self.camera_rotation[1])
        right_x = math.cos(yaw_rad)
        right_z = math.sin(yaw_rad)

        # Drift camera-left, correcting only horizontal aim to avoid vertical bobbing.
        self.camera_pos[0] -= right_x * self.strafe_speed * dt
        self.camera_pos[2] -= right_z * self.strafe_speed * dt
        self.center_target_horizontally()
