"""Main-menu 3D objects, camera, lighting, and checkerboard."""

import math

from OpenGL.GL import *
from OpenGL.GLU import *

from sourcebox.rendering.shadows import model_matrix, sphere_shadow_on_cube

# The menu is matched to a reference render that used a long lens, so its
# projection differs from the other scenes.
MAIN_FOV = 16.35
MAIN_NEAR = 1.0
MAIN_FAR = 200.0

# World space is laid out on the board: Y is height above the checkerboard and
# the cube sits over the origin. These values were fitted to the reference image.
CAMERA_POSITION = [-1.508, 0.382, -29.669]
CAMERA_ROTATION = [94.79, -13.46, -24.64]
LIGHT_DIRECTION = [0.338, 0.164, -0.927, 0.0]
LIGHT_DIFFUSE = 0.696

# OpenGL's default scene ambient; added to the light's own ambient term.
GLOBAL_AMBIENT = 0.2

BASE_BRIGHTNESS = {"cube": 0.6, "sphere": 0.7, "cone": 0.65}

# Flat colour of the cube while it spins after being clicked.
SPIN_COLOR = (0.376, 0.878, 0.949)


def apply_main_projection(aspect_ratio):
    """Set the main-menu perspective on the current (projection) matrix."""
    gluPerspective(MAIN_FOV, aspect_ratio, MAIN_NEAR, MAIN_FAR)


class Object3D:
    def __init__(self, obj_type, position=(0, 0, 0), rotation=(0, 0, 0), scale=1.0, scale_xyz=[1.0, 1.0, 1.0], brightness=0.6):
        self.type = obj_type
        self.position = list(position)
        self.rotation = list(rotation)
        self.base_rotation = list(rotation)
        self.base_scale = max(0.01, abs(scale))
        self.scale = self.base_scale
        self.target_scale = self.base_scale
        self.scale_xyz = [max(0.01, abs(s)) for s in scale_xyz]
        self.brightness = max(0.0, min(1.0, brightness))
        self.base_brightness = self.brightness
        self.is_hovered = False
        self.is_rotating = False
        self.rotation_angle = 0.0
        self.hover_timer = 0.0
        self.hover_animation_duration = 0.1
        self.hover_scale_amount = 0.05
        self.was_hovered = False
        self.display_list = None

        # precalculate bounding sphere radius
        if self.type == "sphere":
            self.bounding_radius = 0.5 * self.scale * max(self.scale_xyz)
        elif self.type == "cube":
            self.bounding_radius = 0.866 * self.scale * max(self.scale_xyz)
        elif self.type == "cone":
            self.bounding_radius = 0.6 * self.scale * max(self.scale_xyz)
        else:
            self.bounding_radius = 0.5 * self.scale * max(self.scale_xyz)

    def shade(self):
        """Grey level the object is drawn with before lighting."""
        return BASE_BRIGHTNESS.get(self.type, 0.6) * self.brightness

    def model_matrix(self):
        """Current model transform, matching what draw_object() applies."""
        scale = [self.scale * s for s in self.scale_xyz]
        spin = self.rotation_angle if self.is_rotating else 0.0
        return model_matrix(self.position, self.base_rotation, scale, spin)

    def create_display_list(self):
        if self.display_list is not None:
            return

        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return

            glNewList(self.display_list, GL_COMPILE)

            if self.type == "cube":
                self._draw_cube_geometry()
            elif self.type == "sphere":
                quadric = gluNewQuadric()
                if quadric:
                    gluQuadricNormals(quadric, GLU_SMOOTH)
                    gluSphere(quadric, 0.5, 32, 32)
                    gluDeleteQuadric(quadric)
            elif self.type == "cone":
                quadric = gluNewQuadric()
                if quadric:
                    gluQuadricNormals(quadric, GLU_SMOOTH)
                    gluCylinder(quadric, 0.5, 0.0, 1.0, 32, 4)
                    gluDeleteQuadric(quadric)

                    glBegin(GL_TRIANGLE_FAN)
                    glNormal3f(0, 0, -1)
                    glVertex3f(0, 0, 0)
                    for i in range(33):
                        angle = (i / 32.0) * 2.0 * math.pi
                        x = 0.5 * math.cos(angle)
                        y = 0.5 * math.sin(angle)
                        glVertex3f(x, y, 0)
                    glEnd()

            glEndList()
        except Exception as e:
            print(f"Error creating display list for {self.type}: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None

    def _draw_cube_geometry(self):
        glBegin(GL_QUADS)
        # top
        glNormal3f(0, 1, 0)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        # bottom
        glNormal3f(0, -1, 0)
        glVertex3f(0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        # right
        glNormal3f(1, 0, 0)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        glVertex3f(0.5, -0.5, -0.5)
        # left
        glNormal3f(-1, 0, 0)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        # front
        glNormal3f(0, 0, -1)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        glVertex3f(0.5, -0.5, -0.5)
        # back
        glNormal3f(0, 0, 1)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glEnd()

    def cleanup(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None

class Camera:
    def __init__(self):
        self.position = list(CAMERA_POSITION)
        self.rotation = list(CAMERA_ROTATION)
        self.fov = MAIN_FOV
        self.matrices_dirty = True

    def apply(self):
        glLoadIdentity()
        glTranslatef(*self.position)
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glRotatef(self.rotation[2], 0, 0, 1)

class Light:
    """Main-menu key light.

    The menu owns GL_LIGHT1. GL_LIGHT0 is left exactly as the menu has always
    left it (position included), because the Voidside scene's grey cones are lit
    by whatever GL_LIGHT0 state they inherit.
    """

    # GL_LIGHT0 as inherited by Voidside: do not retune.
    SHARED_POSITION = [107.10, 2.85, -185.15, 1.0]
    SHARED_CAMERA_POSITION = [0.0, -1.0, -10.0]
    SHARED_CAMERA_ROTATION = [92.97, -9.00, -10.38]
    SHARED_AMBIENT = [0.1, 0.1, 0.1, 1.0]
    SHARED_DIFFUSE = [1.0, 1.0, 1.0, 1.0]
    SHARED_SPECULAR = [1.0, 1.0, 1.0, 1.0]

    def __init__(self):
        # w = 0: directional, pointing from the scene towards the light
        self.position = list(LIGHT_DIRECTION)
        self.ambient = [0.1, 0.1, 0.1, 1.0]
        self.diffuse = [LIGHT_DIFFUSE, LIGHT_DIFFUSE, LIGHT_DIFFUSE, 1.0]
        self.specular = [0.0, 0.0, 0.0, 1.0]
        self.setup_done = False

    def ambient_level(self):
        """Fraction of an object's colour that survives with no direct light."""
        return self.ambient[0] + GLOBAL_AMBIENT

    def apply(self):
        """Light the menu; call with the menu camera applied, then release()."""
        if not self.setup_done:
            glLightfv(GL_LIGHT0, GL_AMBIENT, self.SHARED_AMBIENT)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, self.SHARED_DIFFUSE)
            glLightfv(GL_LIGHT0, GL_SPECULAR, self.SHARED_SPECULAR)
            self.setup_done = True

        glPushMatrix()
        glLoadIdentity()
        glTranslatef(*self.SHARED_CAMERA_POSITION)
        glRotatef(self.SHARED_CAMERA_ROTATION[0], 1, 0, 0)
        glRotatef(self.SHARED_CAMERA_ROTATION[1], 0, 1, 0)
        glRotatef(self.SHARED_CAMERA_ROTATION[2], 0, 0, 1)
        glLightfv(GL_LIGHT0, GL_POSITION, self.SHARED_POSITION)
        glPopMatrix()

        glLightfv(GL_LIGHT1, GL_AMBIENT, self.ambient)
        glLightfv(GL_LIGHT1, GL_DIFFUSE, self.diffuse)
        glLightfv(GL_LIGHT1, GL_SPECULAR, self.specular)
        glLightfv(GL_LIGHT1, GL_POSITION, self.position)
        glDisable(GL_LIGHT0)
        glEnable(GL_LIGHT1)

    def release(self):
        """Hand lighting back to GL_LIGHT0 for the other scenes."""
        glDisable(GL_LIGHT1)
        glEnable(GL_LIGHT0)


def draw_sphere_shadow(objects, light):
    """Darken the part of the cube that sits in the sphere's shadow."""
    cube = next((o for o in objects if o.type == "cube"), None)
    sphere = next((o for o in objects if o.type == "sphere"), None)
    if cube is None or sphere is None:
        return
    if cube.is_hovered or cube.is_rotating:
        # highlighted objects are drawn unlit, so they show no shadow
        return

    polygons = sphere_shadow_on_cube(light.position, sphere.model_matrix(), cube.model_matrix())
    if not polygons:
        return

    shade = cube.shade() * light.ambient_level()

    glPushMatrix()
    glMultMatrixf([value for column in zip(*cube.model_matrix()) for value in column])
    glDisable(GL_LIGHTING)
    glEnable(GL_POLYGON_OFFSET_FILL)
    glPolygonOffset(-1.0, -1.0)
    glDepthMask(GL_FALSE)
    glColor3f(shade, shade, shade)
    for _normal, points in polygons:
        glBegin(GL_POLYGON)
        for point in points:
            glVertex3f(*point)
        glEnd()
    glDepthMask(GL_TRUE)
    glDisable(GL_POLYGON_OFFSET_FILL)
    glEnable(GL_LIGHTING)
    glPopMatrix()


class Checkerboard:
    def __init__(self):
        # 32 tiles across a 1024px texture: whole texels per tile keeps edges exact
        self.size = 16
        self.position = [-0.168, 0.0, 0.804]
        self.rotation = [0, 0, 0]
        self.scale = [1.574, 1.0, 1.169]
        self.dark_color = [0.147, 0.147, 0.147]
        self.light_color = [0.0, 0.0, 0.0]
        self.brightness = 2
        # 0 = crisp tile edges, 1 = fully box-blurred; matched to the reference
        self.edge_blur = 0.53
        self.display_list = None
        self.texture = None

    def create_display_list(self):
        if self.display_list is not None:
            return

        self._create_blurred_texture()

        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return

            glNewList(self.display_list, GL_COMPILE)

            size = self.size

            if self.texture:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, self.texture)
                glNormal3f(0, 1, 0)
                glColor3f(1, 1, 1)
                glBegin(GL_QUADS)
                glTexCoord2f(0, 0); glVertex3f(-size, 0, -size)
                glTexCoord2f(1, 0); glVertex3f(size, 0, -size)
                glTexCoord2f(1, 1); glVertex3f(size, 0, size)
                glTexCoord2f(0, 1); glVertex3f(-size, 0, size)
                glEnd()
                glDisable(GL_TEXTURE_2D)
            else:
                dark_r = self.dark_color[0] * self.brightness
                dark_g = self.dark_color[1] * self.brightness
                dark_b = self.dark_color[2] * self.brightness
                light_r = self.light_color[0] * self.brightness
                light_g = self.light_color[1] * self.brightness
                light_b = self.light_color[2] * self.brightness

                glNormal3f(0, 1, 0)
                glBegin(GL_QUADS)
                for x in range(-size, size):
                    for z in range(-size, size):
                        if (x + z) & 1:
                            glColor3f(light_r, light_g, light_b)
                        else:
                            glColor3f(dark_r, dark_g, dark_b)

                        glVertex3f(x, 0, z)
                        glVertex3f(x, 0, z+1)
                        glVertex3f(x+1, 0, z+1)
                        glVertex3f(x+1, 0, z)
                glEnd()

            glEndList()
        except Exception as e:
            print(f"Error creating checkerboard display list: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None

    def _create_blurred_texture(self):
        """generate a pre-blurred checkerboard texture"""
        try:
            tex_size = 1024
            tile_count = self.size * 2
            pixels_per_tile = tex_size / tile_count

            dark_val = int(self.dark_color[0] * self.brightness * 255)
            light_val = int(self.light_color[0] * self.brightness * 255)

            # generate sharp checkerboard
            data = bytearray(tex_size * tex_size * 3)
            for y in range(tex_size):
                for x in range(tex_size):
                    tx = int(x / pixels_per_tile)
                    ty = int(y / pixels_per_tile)
                    val = light_val if (tx + ty) & 1 else dark_val
                    idx = (y * tex_size + x) * 3
                    data[idx] = val
                    data[idx + 1] = val
                    data[idx + 2] = val

            # soften tile edges: blend the sharp texture with a 3x3 box blur
            sharp = bytes(data)
            blurred = bytearray(tex_size * tex_size * 3)
            radius = 1
            for y in range(tex_size):
                for x in range(tex_size):
                    r_sum = 0
                    count = 0
                    for dy in range(-radius, radius + 1):
                        for dx in range(-radius, radius + 1):
                            nx = min(max(x + dx, 0), tex_size - 1)
                            ny = min(max(y + dy, 0), tex_size - 1)
                            r_sum += sharp[(ny * tex_size + nx) * 3]
                            count += 1
                    idx = (y * tex_size + x) * 3
                    blur_val = r_sum // count
                    sharp_val = sharp[idx]
                    val = int(sharp_val * (1.0 - self.edge_blur) + blur_val * self.edge_blur)
                    blurred[idx] = val
                    blurred[idx + 1] = val
                    blurred[idx + 2] = val
            data = blurred

            self.texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, tex_size, tex_size, 0,
                         GL_RGB, GL_UNSIGNED_BYTE, bytes(data))
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)
        except Exception as e:
            print(f"Blur texture creation failed ({e}), using sharp checkerboard")
            self.texture = None

    def draw(self, display_width=None, display_height=None):
        if self.display_list is None:
            return

        glPushMatrix()
        glTranslatef(*self.position)
        if self.rotation[0] or self.rotation[1] or self.rotation[2]:
            glRotatef(self.rotation[0], 1, 0, 0)
            glRotatef(self.rotation[1], 0, 1, 0)
            glRotatef(self.rotation[2], 0, 0, 1)
        glScalef(self.scale[0], self.scale[1], self.scale[2])
        glCallList(self.display_list)
        glPopMatrix()

    def cleanup(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None
        if self.texture:
            try:
                glDeleteTextures([self.texture])
            except:
                pass
            self.texture = None
