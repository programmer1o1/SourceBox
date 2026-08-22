"""Mouse-to-world ray casting helpers."""

import math

from OpenGL.GL import *
from OpenGL.GLU import *
class RayCaster:
    def __init__(self):
        self.viewport = None
        self.modelview = None
        self.projection = None
        self.last_mouse_pos = None
        self.cached_ray = (None, None)

    def update_matrices(self):
        self.viewport = glGetIntegerv(GL_VIEWPORT)
        self.modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        self.projection = glGetDoublev(GL_PROJECTION_MATRIX)

    def get_ray_from_mouse(self, mouse_x, mouse_y):
        if self.last_mouse_pos == (mouse_x, mouse_y) and self.cached_ray[0] is not None:
            return self.cached_ray

        self.last_mouse_pos = (mouse_x, mouse_y)

        if self.viewport is None:
            self.cached_ray = (None, None)
            return self.cached_ray

        try:
            y = self.viewport[3] - mouse_y

            near_point = gluUnProject(mouse_x, y, 0.0, self.modelview, self.projection, self.viewport)
            far_point = gluUnProject(mouse_x, y, 1.0, self.modelview, self.projection, self.viewport)

            dx = far_point[0] - near_point[0]
            dy = far_point[1] - near_point[1]
            dz = far_point[2] - near_point[2]

            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            if length < 0.0001:
                self.cached_ray = (None, None)
                return self.cached_ray

            inv_length = 1.0 / length
            ray_dir = [dx * inv_length, dy * inv_length, dz * inv_length]

            self.cached_ray = (list(near_point), ray_dir)
            return self.cached_ray
        except:
            self.cached_ray = (None, None)
            return self.cached_ray

    @staticmethod
    def ray_sphere_intersection(ray_origin, ray_dir, sphere_pos, sphere_radius):
        if not ray_origin or not ray_dir or sphere_radius <= 0:
            return False

        oc_x = ray_origin[0] - sphere_pos[0]
        oc_y = ray_origin[1] - sphere_pos[1]
        oc_z = ray_origin[2] - sphere_pos[2]

        a = ray_dir[0]*ray_dir[0] + ray_dir[1]*ray_dir[1] + ray_dir[2]*ray_dir[2]
        if a < 0.0001:
            return False

        b = 2.0 * (oc_x * ray_dir[0] + oc_y * ray_dir[1] + oc_z * ray_dir[2])
        c = oc_x*oc_x + oc_y*oc_y + oc_z*oc_z - sphere_radius * sphere_radius

        discriminant = b*b - 4*a*c
        return discriminant >= 0
